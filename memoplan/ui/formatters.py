"""
Formatters module producing beautiful HTML messages for Telegram.
"""
from datetime import datetime, timezone
import html
from typing import Any, Dict, List, Optional

from memoplan.models import ReviewLog, Topic, UserSettings
from memoplan.presets import get_preset
from memoplan.scheduler import (
    format_time_diff_due,
    format_time_diff_future,
    now_utc,
    to_user_tz,
)


def format_queue_message(
    queue: Dict[str, List[Topic]],
    settings: UserSettings,
    now_dt: Optional[datetime] = None,
) -> str:
    """Format the 3-block Queue view."""
    if now_dt is None:
        now_dt = now_utc()

    due = queue.get("due", [])
    soon = queue.get("soon", [])
    future = queue.get("future", [])
    paused = queue.get("paused", [])
    mastered = queue.get("mastered", [])

    lines = []
    lines.append("📥 <b>ОЧЕРЕДЬ НА СЕГОДНЯ (INBOX)</b>\n")

    # Block 1: Due now
    if due:
        lines.append(f"🔴 <b>ГОТОВО К ПОВТОРЕНИЮ ({len(due)}):</b>")
        for t in due[:7]:  # show up to 7
            preset = get_preset(t.preset_name)
            overdue_str = format_time_diff_due(t.next_review_at, now_dt)
            escaped_title = html.escape(t.title)
            lines.append(f"  • <b>{escaped_title}</b> — <i>Этап {t.stage}/{preset.total_steps}</i> ({overdue_str})")
        if len(due) > 7:
            lines.append(f"  <i>...и еще {len(due) - 7} тем</i>")
    else:
        lines.append("🟢 <b>ГОТОВО К ПОВТОРЕНИЮ:</b>")
        lines.append("  <i>Все темы на данный момент повторены! Отличная работа.</i>")

    lines.append("")

    # Block 2: Soon (today)
    if soon:
        lines.append(f"🟡 <b>СКОРО В ТЕЧЕНИЕ ДНЯ ({len(soon)}):</b>")
        for t in soon[:5]:
            time_str = format_time_diff_future(t.next_review_at, settings.timezone_offset, now_dt)
            preset = get_preset(t.preset_name)
            escaped_title = html.escape(t.title)
            lines.append(f"  • <b>{escaped_title}</b> — <code>{time_str}</code> (эт. {t.stage}/{preset.total_steps})")
        if len(soon) > 5:
            lines.append(f"  <i>...и еще {len(soon) - 5} тем</i>")
    else:
        lines.append("🟡 <b>СКОРО:</b>")
        lines.append("  <i>На ближайшие часы новых повторений не запланировано.</i>")

    lines.append("")

    # Block 3: Future & Paused
    total_future = len(future)
    if future:
        lines.append(f"🔵 <b>БУДУЩИЕ ТЕМЫ ({total_future}):</b>")
        for t in future[:4]:
            time_str = format_time_diff_future(t.next_review_at, settings.timezone_offset, now_dt)
            preset = get_preset(t.preset_name)
            escaped_title = html.escape(t.title)
            lines.append(f"  • <b>{escaped_title}</b> — {time_str} (эт. {t.stage}/{preset.total_steps})")
        if total_future > 4:
            lines.append(f"  <i>...всего в расписании {total_future} тем</i>")
    else:
        lines.append("🔵 <b>БУДУЩИЕ ТЕМЫ:</b> <i>Пока пусто</i>")

    if paused:
        lines.append(f"\n⏸ <i>На паузе: {len(paused)} тем</i>")

    if mastered:
        lines.append(f"🏆 <i>В долговременной памяти: {len(mastered)} тем</i>")

    lines.append("\n💡 <i>Нажмите «Начать повторение» или выберите действие ниже.</i>")
    return "\n".join(lines)


def format_review_card(
    topic: Topic,
    queue_index: int,
    queue_total: int,
    revealed: bool = False,
) -> str:
    """Format active topic review card."""
    preset = get_preset(topic.preset_name)
    escaped_title = html.escape(topic.title)

    lines = [
        f"📖 <b>ПОВТОРЕНИЕ ТЕМЫ ({queue_index} из {queue_total})</b>",
        "────────────────────────",
        f"📌 <b>Тема:</b> <code>{escaped_title}</code>",
        f"📊 <b>Этап:</b> {topic.stage} из {preset.total_steps} [<i>{preset.title}</i>]",
    ]

    current_step = preset.get_step(topic.stage)
    if current_step:
        lines.append(f"⏱ <b>Интервал шага:</b> {current_step.label}")

    lines.append("")
    lines.append("🧠 <i>Попробуйте мысленно воспроизвести материал, ключевые моменты и контекст.</i>")

    if revealed:
        lines.append("")
        lines.append("📝 <b>ШПАРГАЛКА / ЗАМЕТКИ:</b>")
        if topic.notes:
            escaped_notes = html.escape(topic.notes)
            lines.append(f"<pre>{escaped_notes}</pre>")
        else:
            lines.append("<i>Заметки к этой теме не были добавлены.</i>")

        lines.append("")
        lines.append("Оцените результат:")
        lines.append("• 🟢 <b>Помню отлично:</b> переход на следующий шаг")
        lines.append("• 🟡 <b>С трудом:</b> повторить ещё раз на том же шаге")
        lines.append("• 🔴 <b>Забыл напрочь:</b> сброс на шаг 1 для закрепления")
    else:
        lines.append("")
        if topic.notes:
            lines.append("<i>Шпаргалка скрыта. Нажмите кнопку ниже, чтобы проверить себя!</i>")
        else:
            lines.append("<i>(Заметок нет)</i> Оцените, насколько хорошо вы помните тему:")

    return "\n".join(lines)


def format_review_result(
    topic: Topic,
    rating: str,
    new_stage: int,
    next_review_at: Optional[datetime],
    status: str,
    settings: UserSettings,
) -> str:
    """Format verdict after user grades a topic."""
    escaped_title = html.escape(topic.title)
    preset = get_preset(topic.preset_name)

    if status == "mastered":
        return (
            f"🎉 <b>ПОЗДРАВЛЯЕМ! ТЕМА ОСВОЕНА!</b>\n"
            f"────────────────────────\n"
            f"📌 <b>{escaped_title}</b> успешно прошла все {preset.total_steps} этапов сетки!\n\n"
            f"🏆 Тема навсегда перенесена в <b>«Долговременную память»</b>."
        )

    rating_titles = {
        "easy": "🟢 <b>Помню отлично!</b>",
        "hard": "🟡 <b>Вспомнил с трудом</b>",
        "again": "🔴 <b>Забыл напрочь (сброс на шаг 1)</b>",
    }

    rating_str = rating_titles.get(rating, rating)

    lines = [
        f"{rating_str}",
        f"📌 <b>{escaped_title}</b>",
        f"📊 Новый этап: <b>{new_stage} из {preset.total_steps}</b>",
    ]

    if next_review_at:
        time_str = format_time_diff_future(next_review_at, settings.timezone_offset)
        local_next = to_user_tz(next_review_at, settings.timezone_offset)
        lines.append(f"⏱ Следующее повторение: <b>{time_str}</b> (<code>{local_next.strftime('%d.%m.%Y %H:%M')}</code>)")

    return "\n".join(lines)


def format_topic_detail(
    topic: Topic,
    settings: UserSettings,
    history: List[ReviewLog],
) -> str:
    """Format single topic details and history logs."""
    preset = get_preset(topic.preset_name)
    escaped_title = html.escape(topic.title)

    status_badge = {
        "active": "🟢 Активна",
        "paused": "⏸ На паузе",
        "mastered": "🏆 В долговременной памяти",
    }.get(topic.status, topic.status)

    created_local = to_user_tz(topic.created_at, settings.timezone_offset)

    lines = [
        f"📌 <b>ТЕМА: {escaped_title}</b>",
        "────────────────────────",
        f"🏷 <b>Статус:</b> {status_badge}",
        f"📊 <b>Этап:</b> {topic.stage} из {preset.total_steps} ({preset.emoji} {preset.title})",
        f"📅 <b>Создана:</b> {created_local.strftime('%d.%m.%Y %H:%M')}",
    ]

    if topic.is_active and topic.next_review_at:
        time_str = format_time_diff_future(topic.next_review_at, settings.timezone_offset)
        local_next = to_user_tz(topic.next_review_at, settings.timezone_offset)
        lines.append(f"⏳ <b>Следующее повторение:</b> {time_str} (<code>{local_next.strftime('%d.%m %H:%M')}</code>)")

    lines.append("")
    lines.append("📝 <b>Заметки / Шпаргалка:</b>")
    if topic.notes:
        escaped_notes = html.escape(topic.notes)
        lines.append(f"<pre>{escaped_notes}</pre>")
    else:
        lines.append("<i>Заметки отсутствуют</i>")

    lines.append("")
    lines.append("📜 <b>История повторений:</b>")
    if history:
        for h in history[:5]:
            h_local = to_user_tz(h.reviewed_at, settings.timezone_offset)
            icon = {"easy": "🟢", "hard": "🟡", "again": "🔴"}.get(h.rating, "⚪️")
            lines.append(f"  {icon} {h_local.strftime('%d.%m %H:%M')}: эт. {h.old_stage} → {h.new_stage}")
    else:
        lines.append("  <i>Пока нет истории повторений</i>")

    return "\n".join(lines)


def format_stats(stats: Dict[str, Any]) -> str:
    """Format statistics view."""
    total = stats.get("total_topics", 0)
    active = stats.get("active_topics", 0)
    mastered = stats.get("mastered_topics", 0)
    paused = stats.get("paused_topics", 0)
    total_reviews = stats.get("total_reviews", 0)
    ratings = stats.get("rating_counts", {})
    stages = stats.get("stage_distribution", {})

    lines = [
        "📊 <b>ВАША СТАТИСТИКА MEMOPLAN</b>",
        "────────────────────────",
        f"📚 Всего тем в системе: <b>{total}</b>",
        f"  • 🟢 Активных: <b>{active}</b>",
        f"  • 🏆 В долговременной памяти: <b>{mastered}</b>",
        f"  • ⏸ На паузе: <b>{paused}</b>",
        "",
        f"🔁 Всего сессий повторения: <b>{total_reviews}</b>",
    ]

    if total_reviews > 0:
        easy_cnt = ratings.get("easy", 0)
        hard_cnt = ratings.get("hard", 0)
        again_cnt = ratings.get("again", 0)

        easy_pct = int(easy_cnt * 100 / total_reviews)
        hard_pct = int(hard_cnt * 100 / total_reviews)
        again_pct = int(again_cnt * 100 / total_reviews)

        lines.append("")
        lines.append("🎯 <b>Качество воспроизведения:</b>")
        lines.append(f"  🟢 Отлично: <b>{easy_cnt}</b> ({easy_pct}%)")
        lines.append(f"  🟡 С трудом: <b>{hard_cnt}</b> ({hard_pct}%)")
        lines.append(f"  🔴 Забыл: <b>{again_cnt}</b> ({again_pct}%)")

    if stages:
        lines.append("")
        lines.append("📈 <b>Распределение активных по этапам:</b>")
        for stage_num, cnt in sorted(stages.items()):
            bar = "▰" * min(10, cnt)
            lines.append(f"  Этап {stage_num}: <code>{bar}</code> {cnt}")

    return "\n".join(lines)


def format_settings(settings: UserSettings) -> str:
    """Format settings description."""
    notif_text = "Включены (умные батчи без спама)" if settings.notifications_enabled else "Выключены"
    sign = "+" if settings.timezone_offset >= 0 else ""

    lines = [
        "⚙️ <b>НАСТРОЙКИ MEMOPLAN</b>",
        "────────────────────────",
        f"🌙 <b>Режим сна (Sleep-aware):</b> {settings.sleep_start_hour:02d}:00 — {settings.sleep_end_hour:02d}:00",
        "<i>Темы, выпадающие на ночь, автоматически сдвигаются на утренний слот, чтобы не будить вас!</i>",
        "",
        f"🌍 <b>Часовой пояс:</b> UTC{sign}{settings.timezone_offset}",
        f"🎯 <b>Пресет по умолчанию:</b> <code>{settings.default_preset}</code>",
        f"🔔 <b>Уведомления:</b> {notif_text}",
    ]
    return "\n".join(lines)


def format_batch_notification(topics: List[Topic]) -> str:
    """Format grouped push notification message."""
    count = len(topics)
    topic_titles = ", ".join(f"<b>{html.escape(t.title)}</b>" for t in topics[:4])
    if count > 4:
        topic_titles += f" и ещё {count - 4}"

    return (
        f"🔔 <b>Пора повторить ({count}):</b>\n\n"
        f"• {topic_titles}\n\n"
        f"🧠 <i>Уделите пару минут, чтобы закрепить материал в памяти!</i>"
    )
