import asyncio
import functools
import itertools
import logging
import os
from pathlib import Path
from typing import Any, cast

import logfire
from mem0 import Memory

from livingbot.prompts import PERSONA_NAME

logger = logging.getLogger(__name__)

GLOBAL_USER_ID = "global"

# mem0's OpenAI LLM backend already auto-detects OPENROUTER_API_KEY and routes
# through OpenRouter on its own; the embedder doesn't, so it's pointed at
# OpenRouter explicitly here — OpenRouter proxies OpenAI's embeddings API too,
# so no separate OPENAI_API_KEY is needed.
_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# mem0's built-in fact-extraction prompt (ADDITIVE_EXTRACTION_PROMPT) has no
# notion of who "assistant" is, so it defaults to writing extracted facts
# like "Assistant stated a preference for...". `custom_instructions` is
# mem0's own supported hook for this — its prompt explicitly gives it
# "highest priority" — rather than us overriding the whole extraction prompt.
_CUSTOM_FACT_EXTRACTION_INSTRUCTIONS = (
    f"The 'assistant' role in this conversation is {PERSONA_NAME}, a Discord "
    "persona with her own opinions, tastes, and daily life — not a generic AI "
    f"assistant. When a fact comes from her own messages, attribute it to "
    f'{PERSONA_NAME} by name (e.g. "{PERSONA_NAME} prefers GPT-4o because...") '
    "instead of writing 'Assistant' or 'the assistant'."
)


def _extract_results(response: Any) -> list[dict[str, Any]]:
    """mem0's search()/get_all() return {"results": [...]} (v1.1+ format)."""
    return cast(
        "list[dict[str, Any]]",
        response.get("results", response) if isinstance(response, dict) else response,
    )


class MemoryStore:
    def __init__(self, memory: Memory) -> None:
        self._memory = memory

    @classmethod
    def create(cls, data_path: Path) -> "MemoryStore":
        data_path.mkdir(parents=True, exist_ok=True)
        config = {
            "custom_instructions": _CUSTOM_FACT_EXTRACTION_INSTRUCTIONS,
            "vector_store": {
                "provider": "chroma",
                "config": {
                    "collection_name": "bot_memories",
                    "path": str(data_path),
                },
            },
            "llm": {
                "provider": "openai",
                "config": {
                    "model": "gpt-5-nano",
                    "reasoning_effort": "low",
                },
            },
            "embedder": {
                "provider": "openai",
                "config": {
                    "model": "text-embedding-3-small",
                    "api_key": os.environ["OPENROUTER_API_KEY"],
                    "openai_base_url": _OPENROUTER_BASE_URL,
                },
            },
        }
        return cls(Memory.from_config(config))

    async def retrieve(
        self,
        queries: list[tuple[str, str]],
        per_message_limit: int = 3,
        limit: int = 8,
    ) -> list[str]:
        with logfire.span("memory.retrieve", query_count=len(queries)) as span:
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
            result = memories[:limit]
            span.set_attribute("retrieved", len(result))
            return result

    async def _retrieve_for_message(
        self, query: str, user_id: str, limit: int
    ) -> list[str]:
        loop = asyncio.get_event_loop()
        banks = list(dict.fromkeys([user_id, GLOBAL_USER_ID]))
        result_lists = await asyncio.gather(
            *[
                loop.run_in_executor(
                    None,
                    functools.partial(
                        self._memory.search,
                        query,
                        filters={"user_id": uid},
                        top_k=limit,
                    ),
                )
                for uid in banks
            ]
        )

        seen: set[str] = set()
        memories: list[str] = []
        for results in result_lists:
            for result in _extract_results(results):
                text: str = result["memory"]
                if text not in seen:
                    seen.add(text)
                    memories.append(text)
        return memories

    async def all(self, user_id: str) -> list[dict[str, Any]]:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None, lambda: self._memory.get_all(filters={"user_id": user_id})
        )
        return _extract_results(result)

    async def delete(self, memory_id: str) -> None:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: self._memory.delete(memory_id))

    async def store(
        self, conversation: list[dict[str, Any]], user_id: str | None = None
    ) -> None:
        loop = asyncio.get_event_loop()
        targets = [GLOBAL_USER_ID] if user_id is None else [user_id]
        with logfire.span("memory.store", targets=targets, turns=len(conversation)):
            await asyncio.gather(
                *[
                    loop.run_in_executor(
                        None,
                        functools.partial(self._memory.add, conversation, user_id=uid),
                    )
                    for uid in targets
                ]
            )
        logger.debug("Stored memories for %s", targets)
