import asyncio
import itertools
import logging
from pathlib import Path

from mem0 import Memory

logger = logging.getLogger(__name__)

GLOBAL_USER_ID = "global"


class MemoryStore:
    def __init__(self, memory: Memory) -> None:
        self._memory = memory

    @classmethod
    def create(cls, data_path: Path) -> "MemoryStore":
        data_path.mkdir(parents=True, exist_ok=True)
        config = {
            "vector_store": {
                "provider": "chroma",
                "config": {
                    "collection_name": "bot_memories",
                    "path": str(data_path),
                },
            }
        }
        return cls(Memory.from_config(config))

    async def retrieve(
        self,
        queries: list[tuple[str, str]],
        per_message_limit: int = 3,
        limit: int = 8,
    ) -> list[str]:
        per_message = await asyncio.gather(
            *[
                self._retrieve_for_message(text, user_id, per_message_limit)
                for text, user_id in queries
            ]
        )

        seen: set[str] = set()
        memories: list[str] = []
        for column in itertools.zip_longest(*per_message):
            for text in column:
                if text is not None and text not in seen:
                    seen.add(text)
                    memories.append(text)
        return memories[:limit]

    async def _retrieve_for_message(
        self, query: str, user_id: str, limit: int
    ) -> list[str]:
        loop = asyncio.get_event_loop()
        banks = list(dict.fromkeys([user_id, GLOBAL_USER_ID]))
        result_lists = await asyncio.gather(
            *[
                loop.run_in_executor(
                    None,
                    lambda uid=uid: self._memory.search(
                        query, user_id=uid, limit=limit
                    ),
                )
                for uid in banks
            ]
        )

        seen: set[str] = set()
        memories: list[str] = []
        for results in result_lists:
            for result in results:
                text: str = result["memory"]
                if text not in seen:
                    seen.add(text)
                    memories.append(text)
        return memories

    async def all(self, user_id: str) -> list[dict]:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None, lambda: self._memory.get_all(user_id=user_id)
        )
        return result.get("results", result) if isinstance(result, dict) else result

    async def delete(self, memory_id: str) -> None:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: self._memory.delete(memory_id))

    async def store(self, conversation: list[dict], user_id: str | None = None) -> None:
        loop = asyncio.get_event_loop()
        targets = [GLOBAL_USER_ID] if user_id is None else [user_id, GLOBAL_USER_ID]
        await asyncio.gather(
            *[
                loop.run_in_executor(
                    None,
                    lambda uid=uid: self._memory.add(conversation, user_id=uid),
                )
                for uid in targets
            ]
        )
        logger.debug("Stored memories for %s", targets)
