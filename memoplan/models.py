"""
Domain models for MemoPlan.
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class Topic:
    id: Optional[int]
    user_id: int
    title: str
    notes: Optional[str]
    stage: int  # Current stage: 0 to N
    preset_name: str  # standard, exam, long_term
    created_at: datetime
    next_review_at: datetime
    status: str = "active"  # 'active', 'paused', 'mastered'
    last_notified_at: Optional[datetime] = None

    @property
    def is_active(self) -> bool:
        return self.status == "active"

    @property
    def is_mastered(self) -> bool:
        return self.status == "mastered"

    @property
    def is_paused(self) -> bool:
        return self.status == "paused"


@dataclass
class ReviewLog:
    id: Optional[int]
    topic_id: int
    user_id: int
    reviewed_at: datetime
    rating: str  # 'easy', 'hard', 'again'
    old_stage: int
    new_stage: int


@dataclass
class UserSettings:
    user_id: int
    sleep_start_hour: int = 23
    sleep_end_hour: int = 9
    timezone_offset: int = 3
    default_preset: str = "standard"
    notifications_enabled: bool = True
    created_at: Optional[datetime] = None
