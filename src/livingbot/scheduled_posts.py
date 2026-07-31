import uuid
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

ScheduledPostStatus = Literal["pending", "posted", "cancelled"]


class ScheduledPost(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    topic: str
    run_at: datetime
    status: ScheduledPostStatus = "pending"
    posted_at: datetime | None = None


class ScheduledPosts(BaseModel):
    entries: list[ScheduledPost] = Field(default_factory=list)

    def due(self, now: datetime) -> list[ScheduledPost]:
        return [p for p in self.entries if p.status == "pending" and p.run_at <= now]


class ScheduledPostStore:
    def __init__(self, data_path: Path) -> None:
        self._path = data_path / "scheduled_posts.json"
        data_path.mkdir(parents=True, exist_ok=True)

    def load(self) -> ScheduledPosts:
        if not self._path.exists():
            return ScheduledPosts()
        return ScheduledPosts.model_validate_json(self._path.read_text())

    def save(self, posts: ScheduledPosts) -> None:
        self._path.write_text(posts.model_dump_json(indent=2))
