import asyncio
import logging
import uuid
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

import chromadb
from pydantic import BaseModel, Field

from livingbot import clock

logger = logging.getLogger(__name__)

COLLECTION_NAME = "inventory"


class InventoryItem(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    name: str
    description: str = ""
    acquired_at: datetime = Field(default_factory=clock.now)
    last_used_at: datetime = Field(default_factory=clock.now)

    def document(self) -> str:
        if self.description:
            return f"{self.name}. {self.description}"
        return self.name


class InventoryStore:
    def __init__(self, collection: chromadb.Collection) -> None:
        self._collection = collection

    @classmethod
    def create(cls, data_path: Path) -> "InventoryStore":
        data_path.mkdir(parents=True, exist_ok=True)
        client = chromadb.PersistentClient(path=str(data_path))
        return cls(client.get_or_create_collection(COLLECTION_NAME))

    async def add(self, item: InventoryItem) -> None:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._add, item)

    async def remove(self, item_id: str) -> bool:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._remove, item_id)

    async def all(self) -> list[InventoryItem]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._all)

    async def recent(self, limit: int = 5) -> list[InventoryItem]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._recent, limit)

    async def recently_acquired(
        self, since: datetime, limit: int = 5
    ) -> list[InventoryItem]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._recently_acquired, since, limit)

    async def search(self, query: str, limit: int = 5) -> list[InventoryItem]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._search, query, limit)

    def _add(self, item: InventoryItem) -> None:
        self._collection.upsert(
            ids=[item.id],
            documents=[item.document()],
            metadatas=[_metadata(item)],
        )

    def _remove(self, item_id: str) -> bool:
        if not self._collection.get(ids=[item_id])["ids"]:
            return False
        self._collection.delete(ids=[item_id])
        return True

    def _all(self) -> list[InventoryItem]:
        result = self._collection.get(include=["metadatas"])
        metadatas = result["metadatas"] or []
        items = [
            _to_item(item_id, metadata)
            for item_id, metadata in zip(result["ids"], metadatas)
        ]
        return sorted(items, key=lambda item: item.acquired_at)

    def _recent(self, limit: int) -> list[InventoryItem]:
        items = self._all()
        items.sort(key=lambda item: item.last_used_at, reverse=True)
        return items[:limit]

    def _recently_acquired(self, since: datetime, limit: int) -> list[InventoryItem]:
        items = [item for item in self._all() if item.acquired_at >= since]
        items.sort(key=lambda item: item.acquired_at, reverse=True)
        return items[:limit]

    def _search(self, query: str, limit: int) -> list[InventoryItem]:
        result = self._collection.query(
            query_texts=[query], n_results=limit, include=["metadatas"]
        )
        metadatas = (result["metadatas"] or [[]])[0]
        items = [
            _to_item(item_id, metadata)
            for item_id, metadata in zip(result["ids"][0], metadatas)
        ]
        self._touch(items)
        return items

    def _touch(self, items: list[InventoryItem]) -> None:
        if not items:
            return
        now = clock.now()
        for item in items:
            item.last_used_at = now
        self._collection.update(
            ids=[item.id for item in items],
            metadatas=[_metadata(item) for item in items],
        )


def _metadata(item: InventoryItem) -> dict[str, str]:
    return {
        "name": item.name,
        "description": item.description,
        "acquired_at": item.acquired_at.isoformat(),
        "last_used_at": item.last_used_at.isoformat(),
    }


def _to_item(item_id: str, metadata: Mapping[str, Any]) -> InventoryItem:
    return InventoryItem(
        id=item_id,
        name=metadata["name"],
        description=metadata["description"],
        acquired_at=metadata["acquired_at"],
        last_used_at=metadata["last_used_at"],
    )
