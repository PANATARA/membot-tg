"""
Notification background service with anti-spam grouping and sleep awareness.
"""
import asyncio
from datetime import datetime, timedelta, timezone
import logging
from typing import Dict, List

from telegram import Bot
from telegram.constants import ParseMode

from memoplan.config import config
from memoplan.database import db
from memoplan.models import Topic, UserSettings
from memoplan.scheduler import now_utc, to_user_tz
from memoplan.ui.formatters import format_batch_notification
from memoplan.ui.keyboards import get_notification_push_keyboard

logger = logging.getLogger(__name__)


class NotifierService:
    def __init__(self, bot: Bot):
        self.bot = bot
        self._running = False
        self._task: asyncio.Task = None

    def start(self) -> None:
        """Start background polling loop."""
        if not self._running:
            self._running = True
            self._task = asyncio.create_task(self._run_loop())
            logger.info("NotifierService background task started.")

    def stop(self) -> None:
        """Stop background polling loop."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            logger.info("NotifierService stopped.")

    async def _run_loop(self) -> None:
        """Periodic loop checking for due topics."""
        # Wait a few seconds after bot startup
        await asyncio.sleep(5)

        while self._running:
            try:
                await self.check_and_notify()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in NotifierService check_and_notify: {e}", exc_info=True)

            await asyncio.sleep(config.NOTIFICATION_CHECK_INTERVAL_SECONDS)

    async def check_and_notify(self) -> None:
        """Scan database for users with due topics and send batch notifications."""
        current_time = now_utc()
        due_by_user: Dict[int, List[Topic]] = db.get_due_topics_for_notifications(current_time)

        for user_id, topics in due_by_user.items():
            if not topics:
                continue

            settings = db.get_or_create_user(user_id)
            if not settings.notifications_enabled:
                continue

            # Check if user is currently in sleep hours
            if self._is_user_sleeping(settings, current_time):
                # Don't disturb during quiet hours!
                continue

            # Anti-spam check: find topics that haven't been notified yet,
            # or where notification cooldown has passed
            topics_to_notify = []
            for t in topics:
                if t.last_notified_at is None:
                    topics_to_notify.append(t)
                else:
                    elapsed = current_time - t.last_notified_at
                    if elapsed >= timedelta(hours=config.NOTIFICATION_COOLDOWN_HOURS):
                        topics_to_notify.append(t)

            if not topics_to_notify:
                # User was already notified about all of these topics recently
                continue

            # Send single grouped notification
            msg_text = format_batch_notification(topics)
            try:
                await self.bot.send_message(
                    chat_id=user_id,
                    text=msg_text,
                    parse_mode=ParseMode.HTML,
                    reply_markup=get_notification_push_keyboard(),
                )
                logger.info(f"Sent batch notification to user {user_id} for {len(topics)} topics.")

                # Mark all due topics as notified
                topic_ids = [t.id for t in topics]
                db.mark_topics_notified(topic_ids, current_time)

            except Exception as e:
                logger.warning(f"Could not send notification to user {user_id}: {e}")

    @staticmethod
    def _is_user_sleeping(settings: UserSettings, current_utc: datetime) -> bool:
        """Check if current time is within user's configured sleep window."""
        local_time = to_user_tz(current_utc, settings.timezone_offset)
        hour = local_time.hour
        s_start = settings.sleep_start_hour
        s_end = settings.sleep_end_hour

        if s_start > s_end:
            # Crosses midnight (e.g. 23 to 9)
            return hour >= s_start or hour < s_end
        elif s_start < s_end:
            return s_start <= hour < s_end
        return False
