import uuid
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

CommitmentStatus = Literal["open", "fulfilled", "dropped"]


class Commitment(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    user_id: str
    channel_id: int
    description: str
    due_hint: str
    made_at: datetime
    status: CommitmentStatus = "open"
    # Set once an automatic proactive nudge has fired, so the life loop never
    # nudges the same promise twice — further follow-through only happens
    # through the normal conversation (see resolve_commitment).
    nudged_at: datetime | None = None
    # When the follow-up judge decides it is not time yet, it also estimates how
    # long the wait still is; until this moment passes the promise is skipped
    # without spending a judgement call on it.
    check_after: datetime | None = None


class Commitments(BaseModel):
    entries: list[Commitment] = Field(default_factory=list)

    def open_entries(self) -> list[Commitment]:
        return [c for c in self.entries if c.status == "open"]

    def awaiting_followup(self, now: datetime) -> list[Commitment]:
        return [
            c
            for c in self.entries
            if c.status == "open"
            and c.nudged_at is None
            and (c.check_after is None or c.check_after <= now)
        ]


class CommitmentStore:
    def __init__(self, data_path: Path) -> None:
        self._path = data_path / "commitments.json"
        data_path.mkdir(parents=True, exist_ok=True)

    def load(self) -> Commitments:
        if not self._path.exists():
            return Commitments()
        return Commitments.model_validate_json(self._path.read_text())

    def save(self, commitments: Commitments) -> None:
        self._path.write_text(commitments.model_dump_json(indent=2))
