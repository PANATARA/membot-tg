"""
Spaced repetition calculation engine with Sleep-Aware scheduling.
"""
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

from memoplan.models import Topic, UserSettings
from memoplan.presets import Preset, get_preset


def now_utc() -> datetime:
    """Return current UTC datetime with timezone info."""
    return datetime.now(timezone.utc)


def to_user_tz(dt_utc: datetime, timezone_offset: int) -> datetime:
    """Convert UTC datetime to user's timezone."""
    if dt_utc.tzinfo is None:
        dt_utc = dt_utc.replace(tzinfo=timezone.utc)
    user_tz = timezone(timedelta(hours=timezone_offset))
    return dt_utc.astimezone(user_tz)


def adjust_for_sleep(dt_utc: datetime, settings: UserSettings) -> datetime:
    """
    Sleep-aware scheduling (Дневной батчинг).
    If target time falls inside sleep hours (e.g. 23:00 - 09:00),
    bump it to the morning slot (09:00).
    """
    if dt_utc.tzinfo is None:
        dt_utc = dt_utc.replace(tzinfo=timezone.utc)

    user_tz = timezone(timedelta(hours=settings.timezone_offset))
    local_dt = dt_utc.astimezone(user_tz)
    hour = local_dt.hour
    sleep_start = settings.sleep_start_hour
    sleep_end = settings.sleep_end_hour

    is_sleeping = False
    if sleep_start > sleep_end:
        # Crosses midnight (e.g., 23:00 to 09:00)
        if hour >= sleep_start or hour < sleep_end:
            is_sleeping = True
    elif sleep_start < sleep_end:
        # Does not cross midnight
        if sleep_start <= hour < sleep_end:
            is_sleeping = True

    if not is_sleeping:
        return dt_utc

    # Bump to morning slot
    if sleep_start > sleep_end and hour >= sleep_start:
        target_date = local_dt.date() + timedelta(days=1)
    else:
        target_date = local_dt.date()

    adjusted_local = datetime(
        year=target_date.year,
        month=target_date.month,
        day=target_date.day,
        hour=sleep_end,
        minute=0,
        second=0,
        tzinfo=user_tz,
    )
    return adjusted_local.astimezone(timezone.utc)


def calculate_initial_review(preset: Preset, settings: UserSettings, base_time: Optional[datetime] = None) -> datetime:
    """
    Calculate next review for a brand new topic (step 0 -> 1).
    Default initial step is +20 minutes.
    """
    if base_time is None:
        base_time = now_utc()
    interval = preset.get_interval(0)
    target = base_time + interval
    return adjust_for_sleep(target, settings)


def calculate_review_outcome(
    topic: Topic,
    rating: str,
    settings: UserSettings,
    base_time: Optional[datetime] = None,
) -> Tuple[int, Optional[datetime], str]:
    """
    Calculate new stage and next_review_at based on rating:
    - 'easy' (Помню отлично): stage + 1
    - 'hard' (Вспомнил с трудом): stage remains the same, scheduled for tomorrow or +12h
    - 'again' (Забыл напрочь): reset to stage 1 (+20m or +12h)

    Returns:
        (new_stage, next_review_at, new_status)
    """
    if base_time is None:
        base_time = now_utc()

    preset = get_preset(topic.preset_name)

    if rating == "easy":
        new_stage = topic.stage + 1
        if new_stage >= preset.total_steps:
            # Topic mastered! Completed all intervals
            return new_stage, None, "mastered"
        # Next interval from preset
        interval = preset.get_interval(new_stage)
        next_dt = adjust_for_sleep(base_time + interval, settings)
        return new_stage, next_dt, "active"

    elif rating == "hard":
        # Keep same stage, schedule shorter interval to reinforce
        new_stage = max(1, topic.stage)
        if topic.stage == 0:
            interval = timedelta(minutes=20)
        elif topic.stage == 1:
            interval = timedelta(hours=6)
        else:
            # 1 day reinforcement
            interval = timedelta(days=1)
        next_dt = adjust_for_sleep(base_time + interval, settings)
        return new_stage, next_dt, "active"

    elif rating == "again":
        # Neural connection broken: reset to stage 1 with +20 minutes
        new_stage = 1
        interval = timedelta(minutes=20)
        next_dt = adjust_for_sleep(base_time + interval, settings)
        return new_stage, next_dt, "active"

    else:
        raise ValueError(f"Unknown rating: {rating}")


def format_time_diff_due(dt_utc: datetime, now_dt: Optional[datetime] = None) -> str:
    """Format overdue time diff in Russian (e.g. 'просрочено на 15 мин')."""
    if now_dt is None:
        now_dt = now_utc()

    diff = now_dt - dt_utc
    total_seconds = int(diff.total_seconds())

    if total_seconds < 60:
        return "созрело только что"
    minutes = total_seconds // 60
    if minutes < 60:
        return f"{minutes} мин назад"
    hours = minutes // 60
    rem_minutes = minutes % 60
    if hours < 24:
        if rem_minutes > 10:
            return f"{hours} ч {rem_minutes} мин назад"
        return f"{hours} ч назад"
    days = hours // 24
    return f"{days} дн назад"


def format_time_diff_future(
    dt_utc: datetime,
    timezone_offset: int,
    now_dt: Optional[datetime] = None,
) -> str:
    """Format future time diff in Russian (e.g. 'через 14 мин' or 'завтра в 09:00')."""
    if now_dt is None:
        now_dt = now_utc()

    diff = dt_utc - now_dt
    total_seconds = int(diff.total_seconds())
    user_local = to_user_tz(dt_utc, timezone_offset)
    now_local = to_user_tz(now_dt, timezone_offset)

    if total_seconds <= 0:
        return "прямо сейчас"

    minutes = total_seconds // 60
    if minutes < 60:
        return f"через {minutes} мин ({user_local.strftime('%H:%M')})"

    hours = minutes // 60
    if hours < 8:
        rem_min = minutes % 60
        if rem_min > 5:
            return f"через {hours} ч {rem_min} мин ({user_local.strftime('%H:%M')})"
        return f"через {hours} ч ({user_local.strftime('%H:%M')})"

    # Check if today, tomorrow, or later
    if user_local.date() == now_local.date():
        return f"сегодня в {user_local.strftime('%H:%M')}"
    elif user_local.date() == (now_local.date() + timedelta(days=1)):
        return f"завтра в {user_local.strftime('%H:%M')}"
    else:
        months_ru = ["янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"]
        month_name = months_ru[user_local.month - 1]
        return f"{user_local.day} {month_name} в {user_local.strftime('%H:%M')}"


def split_topics_queue(
    topics: List[Topic],
    threshold_hours: int = 24,
    now_dt: Optional[datetime] = None,
) -> Dict[str, List[Topic]]:
    """
    Split topics into 3 primary blocks:
    - 'due': next_review_at <= now
    - 'soon': now < next_review_at <= now + threshold_hours
    - 'future': next_review_at > now + threshold_hours
    - 'paused': status == 'paused'
    - 'mastered': status == 'mastered'
    """
    if now_dt is None:
        now_dt = now_utc()

    soon_limit = now_dt + timedelta(hours=threshold_hours)

    due: List[Topic] = []
    soon: List[Topic] = []
    future: List[Topic] = []
    paused: List[Topic] = []
    mastered: List[Topic] = []

    for t in topics:
        if t.status == "mastered":
            mastered.append(t)
        elif t.status == "paused":
            paused.append(t)
        elif t.status == "active":
            if t.next_review_at <= now_dt:
                due.append(t)
            elif t.next_review_at <= soon_limit:
                soon.append(t)
            else:
                future.append(t)

    # Sort topics
    due.sort(key=lambda x: x.next_review_at)
    soon.sort(key=lambda x: x.next_review_at)
    future.sort(key=lambda x: x.next_review_at)

    return {
        "due": due,
        "soon": soon,
        "future": future,
        "paused": paused,
        "mastered": mastered,
    }
