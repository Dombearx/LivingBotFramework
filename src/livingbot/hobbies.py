import logging
from collections.abc import Iterable
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field
from pydantic_ai import ModelRetry

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


def find_hobby(hobbies: Hobbies, name: str) -> Hobby | None:
    return next((hobby for hobby in hobbies.entries if hobby.name == name), None)


def reject_unknown_hobbies(used: Iterable[str], known: list[str]) -> None:
    """Send a model back when it names a hobby she doesn't have.

    An invented name matches nothing downstream — a week's experience is dropped, a
    story's picture loses the skill level it should have been drawn at — and the loss
    is silent, so it is worth spending a retry to get a real name.
    """
    unknown = sorted({name for name in used if name and name not in known})
    if not unknown:
        return
    raise ModelRetry(
        f"These are not her hobbies: {', '.join(unknown)}. A hobby must be exactly "
        f"one of: {', '.join(known)} — or empty where nothing fits. Fix that and "
        "return the whole result again."
    )


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
        hobby = find_hobby(hobbies, name)
        if hobby is None:
            logger.warning(
                "Dropped %d xp: no hobby named %r. Her hobbies are: %s",
                amount,
                name,
                ", ".join(entry.name for entry in hobbies.entries) or "(none)",
            )
            return
        hobby.gain_experience(amount)
        self.save(hobbies)
