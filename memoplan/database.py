"""
Database layer for MemoPlan using SQLite.
"""
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from typing import Any, Dict, List, Optional, Tuple

from memoplan.config import config
from memoplan.models import ReviewLog, Topic, UserSettings
from memoplan.presets import PRESETS


from contextlib import contextmanager

class Database:
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = str(db_path or config.DATABASE_PATH)
        self._init_db()

    @contextmanager
    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self) -> None:
        """Create database tables and indexes if they do not exist."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    sleep_start_hour INTEGER NOT NULL DEFAULT 23,
                    sleep_end_hour INTEGER NOT NULL DEFAULT 9,
                    timezone_offset INTEGER NOT NULL DEFAULT 3,
                    default_preset TEXT NOT NULL DEFAULT 'standard',
                    notifications_enabled INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS topics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    notes TEXT,
                    stage INTEGER NOT NULL DEFAULT 0,
                    preset_name TEXT NOT NULL DEFAULT 'standard',
                    created_at TEXT NOT NULL,
                    next_review_at TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    last_notified_at TEXT,
                    FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS review_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    topic_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    reviewed_at TEXT NOT NULL,
                    rating TEXT NOT NULL,
                    old_stage INTEGER NOT NULL,
                    new_stage INTEGER NOT NULL,
                    FOREIGN KEY (topic_id) REFERENCES topics (id) ON DELETE CASCADE,
                    FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
                )
            """)

            cursor.execute("CREATE INDEX IF NOT EXISTS idx_topics_user_status ON topics(user_id, status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_topics_next_review ON topics(next_review_at)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_history_user ON review_history(user_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_history_topic ON review_history(topic_id)")
            conn.commit()

    @staticmethod
    def _parse_dt(iso_str: Optional[str]) -> Optional[datetime]:
        if not iso_str:
            return None
        dt = datetime.fromisoformat(iso_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt

    @staticmethod
    def _format_dt(dt: Optional[datetime]) -> Optional[str]:
        if not dt:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat()

    # --- Users ---

    def get_or_create_user(self, user_id: int) -> UserSettings:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            if row:
                return UserSettings(
                    user_id=row["user_id"],
                    sleep_start_hour=row["sleep_start_hour"],
                    sleep_end_hour=row["sleep_end_hour"],
                    timezone_offset=row["timezone_offset"],
                    default_preset=row["default_preset"],
                    notifications_enabled=bool(row["notifications_enabled"]),
                    created_at=self._parse_dt(row["created_at"]),
                )

            now_str = datetime.now(timezone.utc).isoformat()
            cursor.execute(
                """
                INSERT INTO users (user_id, sleep_start_hour, sleep_end_hour, timezone_offset, default_preset, notifications_enabled, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    config.DEFAULT_SLEEP_START_HOUR,
                    config.DEFAULT_SLEEP_END_HOUR,
                    config.DEFAULT_TIMEZONE_OFFSET,
                    "standard",
                    1,
                    now_str,
                ),
            )
            conn.commit()
            return UserSettings(
                user_id=user_id,
                sleep_start_hour=config.DEFAULT_SLEEP_START_HOUR,
                sleep_end_hour=config.DEFAULT_SLEEP_END_HOUR,
                timezone_offset=config.DEFAULT_TIMEZONE_OFFSET,
                default_preset="standard",
                notifications_enabled=True,
                created_at=datetime.now(timezone.utc),
            )

    def update_user_settings(self, settings: UserSettings) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                UPDATE users
                SET sleep_start_hour = ?, sleep_end_hour = ?, timezone_offset = ?,
                    default_preset = ?, notifications_enabled = ?
                WHERE user_id = ?
                """,
                (
                    settings.sleep_start_hour,
                    settings.sleep_end_hour,
                    settings.timezone_offset,
                    settings.default_preset,
                    1 if settings.notifications_enabled else 0,
                    settings.user_id,
                ),
            )
            conn.commit()

    # --- Topics ---

    def create_topic(
        self,
        user_id: int,
        title: str,
        notes: Optional[str],
        stage: int,
        preset_name: str,
        next_review_at: datetime,
        created_at: Optional[datetime] = None,
        status: str = "active",
    ) -> Topic:
        if created_at is None:
            created_at = datetime.now(timezone.utc)

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO topics (user_id, title, notes, stage, preset_name, created_at, next_review_at, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    title.strip(),
                    notes.strip() if notes else None,
                    stage,
                    preset_name,
                    self._format_dt(created_at),
                    self._format_dt(next_review_at),
                    status,
                ),
            )
            conn.commit()
            topic_id = cursor.lastrowid

            return Topic(
                id=topic_id,
                user_id=user_id,
                title=title.strip(),
                notes=notes.strip() if notes else None,
                stage=stage,
                preset_name=preset_name,
                created_at=created_at,
                next_review_at=next_review_at,
                status=status,
                last_notified_at=None,
            )

    def get_topic(self, topic_id: int) -> Optional[Topic]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM topics WHERE id = ?", (topic_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_topic(row)

    def _row_to_topic(self, row: sqlite3.Row) -> Topic:
        return Topic(
            id=row["id"],
            user_id=row["user_id"],
            title=row["title"],
            notes=row["notes"],
            stage=row["stage"],
            preset_name=row["preset_name"],
            created_at=self._parse_dt(row["created_at"]),
            next_review_at=self._parse_dt(row["next_review_at"]),
            status=row["status"],
            last_notified_at=self._parse_dt(row["last_notified_at"]),
        )

    def get_user_topics(self, user_id: int, status: Optional[str] = None) -> List[Topic]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if status:
                cursor.execute(
                    "SELECT * FROM topics WHERE user_id = ? AND status = ? ORDER BY next_review_at ASC",
                    (user_id, status),
                )
            else:
                cursor.execute(
                    "SELECT * FROM topics WHERE user_id = ? ORDER BY next_review_at ASC",
                    (user_id,),
                )
            return [self._row_to_topic(r) for r in cursor.fetchall()]

    def get_due_topics(self, user_id: int, now_dt: Optional[datetime] = None) -> List[Topic]:
        if now_dt is None:
            now_dt = datetime.now(timezone.utc)
        now_str = self._format_dt(now_dt)

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM topics
                WHERE user_id = ? AND status = 'active' AND next_review_at <= ?
                ORDER BY next_review_at ASC
                """,
                (user_id, now_str),
            )
            return [self._row_to_topic(r) for r in cursor.fetchall()]

    def update_topic(self, topic: Topic) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                UPDATE topics
                SET title = ?, notes = ?, stage = ?, preset_name = ?,
                    next_review_at = ?, status = ?, last_notified_at = ?
                WHERE id = ?
                """,
                (
                    topic.title,
                    topic.notes,
                    topic.stage,
                    topic.preset_name,
                    self._format_dt(topic.next_review_at),
                    topic.status,
                    self._format_dt(topic.last_notified_at),
                    topic.id,
                ),
            )
            conn.commit()

    def update_topic_status(self, topic_id: int, user_id: int, new_status: str) -> bool:
        with self._get_connection() as conn:
            cursor = conn.execute(
                "UPDATE topics SET status = ? WHERE id = ? AND user_id = ?",
                (new_status, topic_id, user_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    def update_topic_notes(self, topic_id: int, user_id: int, notes: str) -> bool:
        with self._get_connection() as conn:
            cursor = conn.execute(
                "UPDATE topics SET notes = ? WHERE id = ? AND user_id = ?",
                (notes, topic_id, user_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    def delete_topic(self, topic_id: int, user_id: int) -> bool:
        with self._get_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM topics WHERE id = ? AND user_id = ?",
                (topic_id, user_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    # --- Review History ---

    def add_review_log(self, log: ReviewLog) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO review_history (topic_id, user_id, reviewed_at, rating, old_stage, new_stage)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    log.topic_id,
                    log.user_id,
                    self._format_dt(log.reviewed_at),
                    log.rating,
                    log.old_stage,
                    log.new_stage,
                ),
            )
            conn.commit()

    def get_topic_history(self, topic_id: int) -> List[ReviewLog]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM review_history WHERE topic_id = ? ORDER BY reviewed_at DESC LIMIT 10",
                (topic_id,),
            )
            rows = cursor.fetchall()
            return [
                ReviewLog(
                    id=r["id"],
                    topic_id=r["topic_id"],
                    user_id=r["user_id"],
                    reviewed_at=self._parse_dt(r["reviewed_at"]),
                    rating=r["rating"],
                    old_stage=r["old_stage"],
                    new_stage=r["new_stage"],
                )
                for r in rows
            ]

    def get_user_stats(self, user_id: int) -> Dict[str, Any]:
        """Aggregate stats for dashboard."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Count by status
            cursor.execute(
                """
                SELECT status, COUNT(*) as cnt
                FROM topics WHERE user_id = ?
                GROUP BY status
                """,
                (user_id,),
            )
            status_counts = {r["status"]: r["cnt"] for r in cursor.fetchall()}

            # Stage distribution for active topics
            cursor.execute(
                """
                SELECT stage, COUNT(*) as cnt
                FROM topics WHERE user_id = ? AND status = 'active'
                GROUP BY stage
                ORDER BY stage ASC
                """,
                (user_id,),
            )
            stage_counts = {r["stage"]: r["cnt"] for r in cursor.fetchall()}

            # History ratings breakdown
            cursor.execute(
                """
                SELECT rating, COUNT(*) as cnt
                FROM review_history WHERE user_id = ?
                GROUP BY rating
                """,
                (user_id,),
            )
            rating_counts = {r["rating"]: r["cnt"] for r in cursor.fetchall()}

            # Total reviews
            total_reviews = sum(rating_counts.values())

            return {
                "total_topics": sum(status_counts.values()),
                "active_topics": status_counts.get("active", 0),
                "mastered_topics": status_counts.get("mastered", 0),
                "paused_topics": status_counts.get("paused", 0),
                "stage_distribution": stage_counts,
                "rating_counts": rating_counts,
                "total_reviews": total_reviews,
            }

    # --- Notifications helper ---

    def get_due_topics_for_notifications(self, now_dt: datetime) -> Dict[int, List[Topic]]:
        """
        Find all active topics that are due, grouped by user_id,
        for users who have notifications_enabled = 1.
        """
        now_str = self._format_dt(now_dt)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT t.* FROM topics t
                JOIN users u ON t.user_id = u.user_id
                WHERE t.status = 'active'
                  AND t.next_review_at <= ?
                  AND u.notifications_enabled = 1
                ORDER BY t.next_review_at ASC
                """,
                (now_str,),
            )
            rows = cursor.fetchall()

            grouped: Dict[int, List[Topic]] = {}
            for r in rows:
                t = self._row_to_topic(r)
                grouped.setdefault(t.user_id, []).append(t)
            return grouped

    def mark_topics_notified(self, topic_ids: List[int], notified_at: datetime) -> None:
        if not topic_ids:
            return
        notified_str = self._format_dt(notified_at)
        placeholders = ",".join("?" * len(topic_ids))
        with self._get_connection() as conn:
            conn.execute(
                f"UPDATE topics SET last_notified_at = ? WHERE id IN ({placeholders})",
                [notified_str] + topic_ids,
            )
            conn.commit()

    # --- Seed Demo Data ---

    def create_demo_topics(self, user_id: int) -> List[Topic]:
        """Create sample topics for test and demonstration."""
        from datetime import timedelta
        now = datetime.now(timezone.utc)
        self.get_or_create_user(user_id)

        samples = [
            (
                "Команда grep",
                "grep -rn 'pattern' . (поиск в файлах)\ngrep -v (инвертировать)\ngrep -E 'reg1|reg2' (regex)",
                2,
                "standard",
                now - timedelta(minutes=25),  # Due now! Overdue by 25 mins
            ),
            (
                "Docker Compose: volumes vs bind mounts",
                "Named volumes управляются Docker (/var/lib/docker/volumes).\nBind mounts монтируют точный хостовый путь.",
                1,
                "standard",
                now + timedelta(minutes=15),  # Soon! In 15 minutes
            ),
            (
                "Git rebase vs merge",
                "rebase: переносит коммиты поверх новой ветки, делая историю линейной.\nmerge: создаёт merge-коммит и сохраняет топологию ветвления.",
                3,
                "standard",
                now + timedelta(hours=14),  # Later today / tomorrow
            ),
            (
                "SQL: Оконные функции ROW_NUMBER()",
                "SELECT id, ROW_NUMBER() OVER (PARTITION BY dept_id ORDER BY salary DESC) as rank FROM employees;",
                7,
                "standard",
                now,  # Mastered sample
            ),
        ]

        created = []
        for i, (title, notes, stage, preset, next_dt) in enumerate(samples):
            status = "mastered" if stage >= 7 else "active"
            t = self.create_topic(
                user_id=user_id,
                title=title,
                notes=notes,
                stage=stage,
                preset_name=preset,
                next_review_at=next_dt,
                status=status,
            )
            # Add some sample history
            self.add_review_log(
                ReviewLog(
                    id=None,
                    topic_id=t.id,
                    user_id=user_id,
                    reviewed_at=now - timedelta(days=stage),
                    rating="easy",
                    old_stage=max(0, stage - 1),
                    new_stage=stage,
                )
            )
            created.append(t)
        return created


db = Database()
