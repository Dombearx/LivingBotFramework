import uuid
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field

from livingbot import clock


class Preference(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    topic: str
    stance: str
    created_at: datetime = Field(default_factory=clock.now)


class Preferences(BaseModel):
    entries: list[Preference] = Field(default_factory=list)


class PreferenceStore:
    def __init__(self, data_path: Path) -> None:
        self._path = data_path / "preferences.json"
        data_path.mkdir(parents=True, exist_ok=True)

    def load(self) -> Preferences:
        if not self._path.exists():
            return Preferences()
        return Preferences.model_validate_json(self._path.read_text())

    def save(self, preferences: Preferences) -> None:
        self._path.write_text(preferences.model_dump_json(indent=2))

    def record(self, topic: str, stance: str) -> Preference:
        preferences = self.load()
        preference = Preference(topic=topic, stance=stance)
        preferences.entries = [
            entry
            for entry in preferences.entries
            if entry.topic.casefold() != topic.casefold()
        ]
        preferences.entries.append(preference)
        self.save(preferences)
        return preference
