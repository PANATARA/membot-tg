"""
Unit and integration tests for MemoPlan core modules.
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest

from memoplan.database import Database
from memoplan.models import Topic, UserSettings
from memoplan.presets import PRESETS, get_preset
from memoplan.scheduler import (
    adjust_for_sleep,
    calculate_initial_review,
    calculate_review_outcome,
    format_time_diff_due,
    format_time_diff_future,
    split_topics_queue,
    to_user_tz,
)
from memoplan.ui.formatters import (
    format_batch_notification,
    format_queue_message,
    format_review_card,
    format_review_result,
    format_stats,
    format_topic_detail,
)


class TestPresets(unittest.TestCase):
    def test_standard_preset_steps(self):
        p = get_preset("standard")
        self.assertEqual(p.total_steps, 7)
        self.assertEqual(p.steps[0].delta, timedelta(minutes=20))
        self.assertEqual(p.steps[1].delta, timedelta(hours=12))
        self.assertEqual(p.steps[2].delta, timedelta(days=1))
        self.assertEqual(p.steps[3].delta, timedelta(days=3))
        self.assertEqual(p.steps[4].delta, timedelta(days=7))
        self.assertEqual(p.steps[5].delta, timedelta(days=14))
        self.assertEqual(p.steps[6].delta, timedelta(days=30))

    def test_exam_preset(self):
        p = get_preset("exam")
        self.assertEqual(p.total_steps, 4)
        self.assertEqual(p.steps[0].delta, timedelta(minutes=20))
        self.assertEqual(p.steps[1].delta, timedelta(hours=2))
        self.assertEqual(p.steps[2].delta, timedelta(hours=12))
        self.assertEqual(p.steps[3].delta, timedelta(days=1))

    def test_long_term_preset(self):
        p = get_preset("long_term")
        self.assertEqual(p.total_steps, 5)


class TestScheduler(unittest.TestCase):
    def setUp(self):
        self.settings = UserSettings(
            user_id=123,
            sleep_start_hour=23,
            sleep_end_hour=9,
            timezone_offset=3,  # UTC+3
        )
        self.tz = timezone(timedelta(hours=3))

    def test_adjust_for_sleep_daytime_untouched(self):
        # 14:00 local time (11:00 UTC)
        base_local = datetime(2026, 10, 9, 14, 0, 0, tzinfo=self.tz)
        base_utc = base_local.astimezone(timezone.utc)

        adjusted_utc = adjust_for_sleep(base_utc, self.settings)
        adjusted_local = to_user_tz(adjusted_utc, 3)

        self.assertEqual(adjusted_local.hour, 14)
        self.assertEqual(adjusted_local.minute, 0)

    def test_adjust_for_sleep_late_night_shifted_to_next_morning(self):
        # 23:30 local time (sleep is 23:00 - 09:00) -> should bump to next day at 09:00
        base_local = datetime(2026, 10, 9, 23, 30, 0, tzinfo=self.tz)
        base_utc = base_local.astimezone(timezone.utc)

        adjusted_utc = adjust_for_sleep(base_utc, self.settings)
        adjusted_local = to_user_tz(adjusted_utc, 3)

        self.assertEqual(adjusted_local.day, 10)
        self.assertEqual(adjusted_local.hour, 9)
        self.assertEqual(adjusted_local.minute, 0)

    def test_adjust_for_sleep_early_morning_shifted_to_same_morning(self):
        # 03:00 local time -> should bump to same day at 09:00
        base_local = datetime(2026, 10, 10, 3, 0, 0, tzinfo=self.tz)
        base_utc = base_local.astimezone(timezone.utc)

        adjusted_utc = adjust_for_sleep(base_utc, self.settings)
        adjusted_local = to_user_tz(adjusted_utc, 3)

        self.assertEqual(adjusted_local.day, 10)
        self.assertEqual(adjusted_local.hour, 9)
        self.assertEqual(adjusted_local.minute, 0)

    def test_calculate_review_outcome_easy(self):
        now = datetime(2026, 10, 9, 12, 0, 0, tzinfo=timezone.utc)
        topic = Topic(
            id=1,
            user_id=123,
            title="Grep command",
            notes="notes",
            stage=1,
            preset_name="standard",
            created_at=now,
            next_review_at=now,
            status="active",
        )

        new_stage, next_dt, status = calculate_review_outcome(topic, "easy", self.settings, base_time=now)
        self.assertEqual(new_stage, 2)
        self.assertEqual(status, "active")
        self.assertIsNotNone(next_dt)

    def test_calculate_review_outcome_mastered(self):
        now = datetime(2026, 10, 9, 12, 0, 0, tzinfo=timezone.utc)
        topic = Topic(
            id=1,
            user_id=123,
            title="Grep command",
            notes="notes",
            stage=6,
            preset_name="standard",  # total steps = 7, stage 6 -> 7 is mastered!
            created_at=now,
            next_review_at=now,
            status="active",
        )

        new_stage, next_dt, status = calculate_review_outcome(topic, "easy", self.settings, base_time=now)
        self.assertEqual(new_stage, 7)
        self.assertEqual(status, "mastered")
        self.assertIsNone(next_dt)

    def test_calculate_review_outcome_again(self):
        now = datetime(2026, 10, 9, 12, 0, 0, tzinfo=timezone.utc)
        topic = Topic(
            id=1,
            user_id=123,
            title="Grep command",
            notes="notes",
            stage=4,
            preset_name="standard",
            created_at=now,
            next_review_at=now,
            status="active",
        )

        new_stage, next_dt, status = calculate_review_outcome(topic, "again", self.settings, base_time=now)
        self.assertEqual(new_stage, 1)  # reset to step 1
        self.assertEqual(status, "active")
        self.assertIsNotNone(next_dt)


class TestDatabaseAndQueue(unittest.TestCase):
    def setUp(self):
        self.temp_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_file.close()
        self.db = Database(Path(self.temp_file.name))

    def tearDown(self):
        Path(self.temp_file.name).unlink(missing_ok=True)

    def test_crud_and_queue_split(self):
        user_id = 999
        self.db.get_or_create_user(user_id)

        now = datetime.now(timezone.utc)

        # Topic 1: Due
        t1 = self.db.create_topic(
            user_id=user_id,
            title="Grep",
            notes="flags",
            stage=2,
            preset_name="standard",
            next_review_at=now - timedelta(minutes=10),
        )

        # Topic 2: Soon (in 30 min)
        t2 = self.db.create_topic(
            user_id=user_id,
            title="Sed",
            notes="stream editor",
            stage=1,
            preset_name="standard",
            next_review_at=now + timedelta(minutes=30),
        )

        # Topic 3: Future (in 3 days)
        t3 = self.db.create_topic(
            user_id=user_id,
            title="Awk",
            notes="patterns",
            stage=3,
            preset_name="standard",
            next_review_at=now + timedelta(days=3),
        )

        all_topics = self.db.get_user_topics(user_id)
        self.assertEqual(len(all_topics), 3)

        queue = split_topics_queue(all_topics, threshold_hours=24, now_dt=now)
        self.assertEqual(len(queue["due"]), 1)
        self.assertEqual(queue["due"][0].id, t1.id)
        self.assertEqual(len(queue["soon"]), 1)
        self.assertEqual(queue["soon"][0].id, t2.id)
        self.assertEqual(len(queue["future"]), 1)
        self.assertEqual(queue["future"][0].id, t3.id)

    def test_demo_topics_creation(self):
        user_id = 888
        demo_topics = self.db.create_demo_topics(user_id)
        self.assertGreaterEqual(len(demo_topics), 4)

        stats = self.db.get_user_stats(user_id)
        self.assertEqual(stats["total_topics"], len(demo_topics))
        self.assertGreater(stats["mastered_topics"], 0)


class TestFormatters(unittest.TestCase):
    def test_format_queue_message(self):
        settings = UserSettings(user_id=123)
        now = datetime.now(timezone.utc)
        t = Topic(
            id=1,
            user_id=123,
            title="Команда grep <test>",
            notes="flags",
            stage=2,
            preset_name="standard",
            created_at=now,
            next_review_at=now - timedelta(minutes=5),
            status="active",
        )
        queue = split_topics_queue([t], now_dt=now)
        msg = format_queue_message(queue, settings, now_dt=now)
        self.assertIn("ОЧЕРЕДЬ НА СЕГОДНЯ", msg)
        self.assertIn("Команда grep &lt;test&gt;", msg)
        self.assertIn("ГОТОВО К ПОВТОРЕНИЮ (1)", msg)


if __name__ == "__main__":
    unittest.main()
