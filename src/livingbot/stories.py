import asyncio
import logging
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import chromadb
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

COLLECTION_NAME = "stories"
RETIREMENT_PERIOD = timedelta(days=60)


class Story(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    summary: str
    content: str
    created_at: datetime = Field(default_factory=datetime.now)
    told_at: datetime | None = None

    def document(self) -> str:
        return self.summary


class StoryStore:
    def __init__(self, collection: chromadb.Collection) -> None:
        self._collection = collection

    @classmethod
    def create(cls, data_path: Path) -> "StoryStore":
        data_path.mkdir(parents=True, exist_ok=True)
        client = chromadb.PersistentClient(path=str(data_path))
        return cls(client.get_or_create_collection(COLLECTION_NAME))

    async def add(self, story: Story) -> None:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._add, story)

    async def untold(self, limit: int = 3) -> list[Story]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._untold, limit)

    async def search(self, query: str, limit: int = 3) -> list[Story]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._search, query, limit)

    async def mark_told(self, story_id: str) -> bool:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._mark_told, story_id)

    async def prune_stale(self, now: datetime) -> None:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._prune_stale, now)

    def _add(self, story: Story) -> None:
        self._collection.upsert(
            ids=[story.id],
            documents=[story.document()],
            metadatas=[_metadata(story)],
        )

    def _all(self) -> list[Story]:
        result = self._collection.get(include=["metadatas"])
        return [
            _to_story(story_id, metadata)
            for story_id, metadata in zip(result["ids"], result["metadatas"])
        ]

    def _untold(self, limit: int) -> list[Story]:
        stories = [story for story in self._all() if story.told_at is None]
        stories.sort(key=lambda story: story.created_at)
        return stories[:limit]

    def _search(self, query: str, limit: int) -> list[Story]:
        result = self._collection.query(
            query_texts=[query], n_results=limit, include=["metadatas"]
        )
        return [
            _to_story(story_id, metadata)
            for story_id, metadata in zip(result["ids"][0], result["metadatas"][0])
        ]

    def _mark_told(self, story_id: str) -> bool:
        existing = self._collection.get(ids=[story_id], include=["metadatas"])
        if not existing["ids"]:
            return False
        story = _to_story(existing["ids"][0], existing["metadatas"][0])
        story.told_at = datetime.now()
        self._collection.update(ids=[story.id], metadatas=[_metadata(story)])
        return True

    def _prune_stale(self, now: datetime) -> None:
        cutoff = now - RETIREMENT_PERIOD
        stale_ids = [
            story.id
            for story in self._all()
            if story.told_at is not None and story.told_at < cutoff
        ]
        if stale_ids:
            self._collection.delete(ids=stale_ids)
            logger.info("Retired %d stale stories", len(stale_ids))


def _metadata(story: Story) -> dict:
    return {
        "summary": story.summary,
        "content": story.content,
        "created_at": story.created_at.isoformat(),
        "told_at": story.told_at.isoformat() if story.told_at else "",
    }


def _to_story(story_id: str, metadata: dict) -> Story:
    told_at = metadata["told_at"]
    return Story(
        id=story_id,
        summary=metadata["summary"],
        content=metadata["content"],
        created_at=metadata["created_at"],
        told_at=told_at or None,
    )
