import logging
import uuid
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field

from livingbot import clock
from livingbot.calendar import PlanEntry

logger = logging.getLogger(__name__)


class ActivityNote(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    activity: str
    note: str
    created_at: datetime = Field(default_factory=clock.now)

    def matches(self, entry: PlanEntry) -> bool:
        target = self.activity.casefold()
        return target == entry.hobby.casefold() or target in entry.activity.casefold()


class ActivityNotes(BaseModel):
    entries: list[ActivityNote] = Field(default_factory=list)

    def apply_to(self, entry: PlanEntry) -> None:
        for note in self.entries:
            if note.matches(entry):
                entry.note = merge_note(entry.note, note.note)


class ActivityNotesStore:
    def __init__(self, data_path: Path) -> None:
        self._path = data_path / "activity_notes.json"
        data_path.mkdir(parents=True, exist_ok=True)

    def load(self) -> ActivityNotes:
        if not self._path.exists():
            return ActivityNotes()
        return ActivityNotes.model_validate_json(self._path.read_text())

    def save(self, notes: ActivityNotes) -> None:
        self._path.write_text(notes.model_dump_json(indent=2))


def merge_note(existing: str, addition: str) -> str:
    if not existing:
        return addition
    if addition in existing:
        return existing
    return f"{existing}; {addition}"
