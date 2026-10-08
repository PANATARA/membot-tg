"""
Presets module defining spaced repetition interval schedules.
"""
from dataclasses import dataclass
from datetime import timedelta
from typing import Dict, List, Optional


@dataclass(frozen=True)
class StepInterval:
    from_stage: int
    to_stage: int
    delta: timedelta
    label: str
    description: str


@dataclass(frozen=True)
class Preset:
    id: str
    title: str
    emoji: str
    description: str
    steps: List[StepInterval]

    @property
    def total_steps(self) -> int:
        """Maximum stage number when the topic is considered fully mastered."""
        return len(self.steps)

    def get_step(self, stage: int) -> Optional[StepInterval]:
        """Get interval for advancing from current stage to stage + 1."""
        if 0 <= stage < len(self.steps):
            return self.steps[stage]
        return None

    def get_interval(self, stage: int) -> timedelta:
        """Returns delta for given stage, or fallback to last interval."""
        step = self.get_step(stage)
        if step:
            return step.delta
        return self.steps[-1].delta if self.steps else timedelta(days=30)


PRESETS: Dict[str, Preset] = {
    "standard": Preset(
        id="standard",
        title="Стандартный",
        emoji="⏱",
        description="20м → 12ч → 1д → 3д → 7д → 14д → 30д (7 шагов)",
        steps=[
            StepInterval(0, 1, timedelta(minutes=20), "20 минут", "Сразу после создания (первичное закрепление)"),
            StepInterval(1, 2, timedelta(hours=12), "12 часов", "Вечером того же дня / на следующее утро"),
            StepInterval(2, 3, timedelta(days=1), "24 часа (1 день)", "На следующий день"),
            StepInterval(3, 4, timedelta(days=3), "3 дня", "Через пару дней"),
            StepInterval(4, 5, timedelta(days=7), "7 дней (неделя)", "Спустя неделю"),
            StepInterval(5, 6, timedelta(days=14), "14 дней (2 недели)", "Через две недели"),
            StepInterval(6, 7, timedelta(days=30), "30 дней (месяц)", "Через месяц"),
        ],
    ),
    "exam": Preset(
        id="exam",
        title="Экзамен (Интенсив)",
        emoji="⚡️",
        description="20м → 2ч → 12ч → 24ч (4 шага)",
        steps=[
            StepInterval(0, 1, timedelta(minutes=20), "20 минут", "Сразу после создания"),
            StepInterval(1, 2, timedelta(hours=2), "2 часа", "В течение дня"),
            StepInterval(2, 3, timedelta(hours=12), "12 часов", "Вечером / утром"),
            StepInterval(3, 4, timedelta(days=1), "24 часа (1 день)", "Перед экзаменом"),
        ],
    ),
    "long_term": Preset(
        id="long_term",
        title="Долговременный",
        emoji="🧠",
        description="20м → 12ч → 3д → 10д → 30д (5 шагов)",
        steps=[
            StepInterval(0, 1, timedelta(minutes=20), "20 минут", "Первичное закрепление"),
            StepInterval(1, 2, timedelta(hours=12), "12 часов", "Вечером / утром"),
            StepInterval(2, 3, timedelta(days=3), "3 дня", "Через пару дней"),
            StepInterval(3, 4, timedelta(days=10), "10 дней", "Через полторы недели"),
            StepInterval(4, 5, timedelta(days=30), "30 дней", "Через месяц"),
        ],
    ),
}


def get_preset(preset_id: str) -> Preset:
    """Return preset by ID, fallback to standard."""
    return PRESETS.get(preset_id, PRESETS["standard"])
