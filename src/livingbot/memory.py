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

    async def retrieve(
        self, query: str, user_ids: list[str], limit: int = 5
    ) -> list[str]:
        loop = asyncio.get_event_loop()
        all_user_ids = list(dict.fromkeys(user_ids + [GLOBAL_USER_ID]))
        result_lists = await asyncio.gather(
            *[
                loop.run_in_executor(
                    None,
                    lambda uid=uid: self._memory.search(
                        query, user_id=uid, limit=limit
                    ),
                )
                for uid in all_user_ids
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
        return memories[:limit]

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
