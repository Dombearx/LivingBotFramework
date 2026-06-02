import asyncio
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

    async def retrieve(self, query: str, user_id: str, limit: int = 5) -> list[str]:
        loop = asyncio.get_event_loop()
        user_results, global_results = await asyncio.gather(
            loop.run_in_executor(
                None, lambda: self._memory.search(query, user_id=user_id, limit=limit)
            ),
            loop.run_in_executor(
                None,
                lambda: self._memory.search(query, user_id=GLOBAL_USER_ID, limit=limit),
            ),
        )

        seen: set[str] = set()
        memories: list[str] = []
        for result in user_results + global_results:
            text: str = result["memory"]
            if text not in seen:
                seen.add(text)
                memories.append(text)
        return memories[:limit]

    async def store(self, conversation: list[dict], user_id: str) -> None:
        loop = asyncio.get_event_loop()
        await asyncio.gather(
            loop.run_in_executor(
                None, lambda: self._memory.add(conversation, user_id=user_id)
            ),
            loop.run_in_executor(
                None,
                lambda: self._memory.add(conversation, user_id=GLOBAL_USER_ID),
            ),
        )
        logger.debug("Stored memories for user %s and global", user_id)
