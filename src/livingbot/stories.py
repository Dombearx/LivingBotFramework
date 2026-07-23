import asyncio
import logging
import random
import uuid
from collections.abc import Mapping
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Self

import chromadb
from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel

from livingbot import clock, llm_config
from livingbot.prompts import (
    STORY_GENERATOR_SYSTEM_PROMPT,
    STORY_TIER_NORMAL,
    STORY_TIER_UNBELIEVABLE,
    STORY_TIER_UNUSUAL,
)

logger = logging.getLogger(__name__)

COLLECTION_NAME = "stories"
RETIREMENT_PERIOD = timedelta(days=60)


class Story(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    summary: str
    content: str
    created_at: datetime = Field(default_factory=clock.now)
    occurs_at: datetime | None = None
    told_at: datetime | None = None
    image_path: str | None = None

    def document(self) -> str:
        return self.summary

    def has_happened(self, now: datetime) -> bool:
        return self.occurs_at is None or self.occurs_at <= now


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

    async def all(self) -> list[Story]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._all)

    async def remove(self, story_id: str) -> bool:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._remove, story_id)

    async def untold(self, limit: int = 3) -> list[Story]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._untold, limit)

    async def search(self, query: str, limit: int = 3) -> list[Story]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._search, query, limit)

    async def recent_summaries(self, limit: int) -> list[str]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._recent_summaries, limit)

    async def get(self, story_id: str) -> "Story | None":
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._get, story_id)

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
        metadatas = result["metadatas"] or []
        return [
            _to_story(story_id, metadata)
            for story_id, metadata in zip(result["ids"], metadatas)
        ]

    def _remove(self, story_id: str) -> bool:
        if not self._collection.get(ids=[story_id])["ids"]:
            return False
        self._collection.delete(ids=[story_id])
        return True

    def _untold(self, limit: int) -> list[Story]:
        now = clock.now()
        stories = [
            story
            for story in self._all()
            if story.told_at is None and story.has_happened(now)
        ]
        stories.sort(key=lambda story: story.created_at)
        return stories[:limit]

    def _search(self, query: str, limit: int) -> list[Story]:
        count = self._collection.count()
        if count == 0:
            return []
        result = self._collection.query(
            query_texts=[query],
            n_results=min(count, limit + 5),
            include=["metadatas"],
        )
        now = clock.now()
        metadatas = (result["metadatas"] or [[]])[0]
        stories = [
            _to_story(story_id, metadata)
            for story_id, metadata in zip(result["ids"][0], metadatas)
        ]
        return [story for story in stories if story.has_happened(now)][:limit]

    def _recent_summaries(self, limit: int) -> list[str]:
        stories = sorted(self._all(), key=lambda story: story.created_at, reverse=True)
        return [story.summary for story in stories[:limit]]

    def _get(self, story_id: str) -> Story | None:
        existing = self._collection.get(ids=[story_id], include=["metadatas"])
        metadatas = existing["metadatas"]
        if not existing["ids"] or not metadatas:
            return None
        return _to_story(existing["ids"][0], metadatas[0])

    def _mark_told(self, story_id: str) -> bool:
        existing = self._collection.get(ids=[story_id], include=["metadatas"])
        metadatas = existing["metadatas"]
        if not existing["ids"] or not metadatas:
            return False
        story = _to_story(existing["ids"][0], metadatas[0])
        story.told_at = clock.now()
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


class StoryTier(BaseModel):
    name: str
    weight: int
    guidance: str


STORY_TIERS = [
    StoryTier(name="normal", weight=75, guidance=STORY_TIER_NORMAL),
    StoryTier(name="unusual", weight=20, guidance=STORY_TIER_UNUSUAL),
    StoryTier(name="unbelievable", weight=5, guidance=STORY_TIER_UNBELIEVABLE),
]


class GeneratedStory(BaseModel):
    summary: str
    content: str


class StoryGenerator:
    @classmethod
    def create(cls) -> Self:
        return cls(llm_config.build_chat_model(llm_config.STORY_GENERATOR_MODEL))

    def __init__(self, model: OpenAIChatModel) -> None:
        self._agent: Agent[None, GeneratedStory] = Agent(
            model,
            name="story_generator",
            instructions=STORY_GENERATOR_SYSTEM_PROMPT,
            output_type=GeneratedStory,
        )

    async def generate(
        self,
        week_start: date,
        hobbies: list[str],
        home_location: str,
        occurs_at: datetime,
        anchor: str | None,
        avoid: list[str],
        new_hobbies: list[str] | None = None,
    ) -> Story | None:
        tier = _choose_tier()
        context = (
            f"At that time she is: {anchor}."
            if anchor
            else "She has no plans then — it happens in a free moment of her week."
        )
        new_block = ""
        if new_hobbies:
            new_block = f"\nShe recently took up: {', '.join(new_hobbies)}."
        avoid_block = ""
        if avoid:
            listed = "\n".join(f"- {summary}" for summary in avoid)
            avoid_block = f"\nRecent episodes to stay clearly away from:\n{listed}"
        prompt = (
            f"The episode happens on {occurs_at:%A %d %B at %H:%M}, during the week "
            f"starting Monday {week_start}.\n"
            f"Her hobbies: {', '.join(hobbies)}.\n"
            f"Her home base: {home_location}.\n"
            f"{context}"
            f"{new_block}\n"
            f"Plausibility level — {tier.guidance}"
            f"{avoid_block}"
        )
        try:
            result = await self._agent.run(prompt)
        except Exception:
            logger.exception("Failed to generate %s story for %s", tier.name, occurs_at)
            return None
        return Story(
            summary=result.output.summary,
            content=result.output.content,
            occurs_at=occurs_at,
        )


def _choose_tier() -> StoryTier:
    return random.choices(STORY_TIERS, weights=[tier.weight for tier in STORY_TIERS])[0]


def _metadata(story: Story) -> dict[str, str]:
    return {
        "summary": story.summary,
        "content": story.content,
        "created_at": story.created_at.isoformat(),
        "occurs_at": story.occurs_at.isoformat() if story.occurs_at else "",
        "told_at": story.told_at.isoformat() if story.told_at else "",
        "image_path": story.image_path or "",
    }


def _to_story(story_id: str, metadata: Mapping[str, Any]) -> Story:
    occurs_at = metadata.get("occurs_at", "")
    told_at = metadata.get("told_at", "")
    return Story(
        id=story_id,
        summary=metadata["summary"],
        content=metadata["content"],
        created_at=metadata["created_at"],
        occurs_at=occurs_at or None,
        told_at=told_at or None,
        image_path=metadata.get("image_path", "") or None,
    )
