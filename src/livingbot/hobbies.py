import logging
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

EXPERIENCE_PER_SESSION = 10

LEVEL_ORDER = [
    "novice",
    "beginner",
    "intermediate",
    "advanced",
    "expert",
]

LEVEL_UP_THRESHOLDS = {
    "novice": 100,
    "beginner": 200,
    "intermediate": 300,
    "advanced": 400,
}


class HobbyLevel(str, Enum):
    novice = "novice"
    beginner = "beginner"
    intermediate = "intermediate"
    advanced = "advanced"
    expert = "expert"


class Hobby(BaseModel):
    name: str
    level: HobbyLevel = HobbyLevel.novice
    experience: int = 0
    acquired_at: datetime | None = None

    def gain_experience(self, amount: int) -> None:
        self.experience += amount
        threshold = LEVEL_UP_THRESHOLDS.get(self.level.value)
        while threshold is not None and self.experience >= threshold:
            self.experience -= threshold
            self.level = HobbyLevel(
                LEVEL_ORDER[LEVEL_ORDER.index(self.level.value) + 1]
            )
            threshold = LEVEL_UP_THRESHOLDS.get(self.level.value)


class Hobbies(BaseModel):
    entries: list[Hobby] = Field(default_factory=list)


def experience_progress(hobby: Hobby) -> str:
    """Experience as progress within the current level, e.g. "20 / 100 xp → beginner".

    Levelling up subtracts the threshold, so the bare number drops on level-up and
    reads as lost experience unless the level it counts towards is shown with it.
    """
    threshold = LEVEL_UP_THRESHOLDS.get(hobby.level.value)
    if threshold is None:
        return f"{hobby.experience} xp"
    next_level = LEVEL_ORDER[LEVEL_ORDER.index(hobby.level.value) + 1]
    return f"{hobby.experience} / {threshold} xp → {next_level}"


def recent_hobbies(hobbies: Hobbies, now: datetime, within: timedelta) -> list[Hobby]:
    return [
        hobby
        for hobby in hobbies.entries
        if hobby.acquired_at is not None and now - hobby.acquired_at < within
    ]


class HobbyStore:
    def __init__(self, data_path: Path, default_hobbies: list[str]) -> None:
        self._path = data_path / "hobbies.json"
        self._default_hobbies = default_hobbies
        data_path.mkdir(parents=True, exist_ok=True)

    def load(self) -> Hobbies:
        if not self._path.exists():
            return Hobbies(entries=[Hobby(name=name) for name in self._default_hobbies])
        return Hobbies.model_validate_json(self._path.read_text())

    def save(self, hobbies: Hobbies) -> None:
        self._path.write_text(hobbies.model_dump_json(indent=2))

    def gain_experience(self, name: str, amount: int) -> None:
        hobbies = self.load()
        for hobby in hobbies.entries:
            if hobby.name == name:
                hobby.gain_experience(amount)
                self.save(hobbies)
                return
        logger.warning(
            "Dropped %d xp: no hobby named %r. Her hobbies are: %s",
            amount,
            name,
            ", ".join(hobby.name for hobby in hobbies.entries) or "(none)",
        )
