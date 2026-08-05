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
# Each "user" message's content is already prefixed with the speaker's Discord
# display name (see tools.format_message, e.g. "Kuba: ..."), so the extractor
# has what it needs to name the user too, once told to use it.
_ATTRIBUTION_INSTRUCTIONS = (
    f"The 'assistant' role in this conversation is {PERSONA_NAME}, a Discord "
    "persona with her own opinions, tastes, and daily life — not a generic AI "
    f"assistant. When a fact comes from her own messages, attribute it to "
    f'{PERSONA_NAME} by name (e.g. "{PERSONA_NAME} prefers GPT-4o because...") '
    "instead of writing 'Assistant' or 'the assistant'. "
    "Each 'user' message starts with the speaker's Discord display name "
    "followed by a colon, e.g. 'Kuba: ...'. Use that display name to "
    'attribute facts (e.g. "Kuba prefers dark chocolate") instead of the '
    "generic word 'User'."
)

# ADDITIVE_EXTRACTION_PROMPT tells the model to extract when in doubt and treats
# casual chat as prime material, which on a Discord server fills the store with
# greetings, banter and one-off jokes. These instructions raise the bar back to
# durable facts; mem0 gives custom instructions "highest priority", so they win
# over the base prompt's bias. The rejection rules lead and are phrased as an
# override because a first pass that merely listed them alongside the keep rules
# still let "Mugda reacted to Kuba's plan by wishing him luck" through.
_RELEVANCE_INSTRUCTIONS = (
    "OVERRIDE — these rules beat every instruction above them, including the "
    "guidance to extract when in doubt and the claim that casual chat is "
    "valuable. This is a Discord server where most messages are small talk "
    "that must produce nothing. An empty list is the normal, expected result.\n"
    "Reject, always:\n"
    "- greetings, goodbyes, reactions, filler, and any purely social message\n"
    "- jokes, banter, teasing, sarcasm, memes and wordplay\n"
    "- any statement describing the exchange itself — anything shaped like "
    f'"X said/asked/replied/reacted/joked/wished...", and in particular every '
    f"sentence about what {PERSONA_NAME} said or how she reacted\n"
    "- what someone is doing right now or in the next few minutes, and "
    "momentary moods\n"
    "- how something was phrased, which emoji, slang or spelling was used\n"
    "Keep only what would still be worth knowing a month from now:\n"
    "- who someone is and their stable circumstances: work, studies, where "
    "they live, family, pets, health\n"
    "- lasting preferences, tastes and strong opinions\n"
    "- who to ask about what, even when that person is not in the "
    'conversation (e.g. "for anything about the Minecraft server, ask '
    'Weronika") — this is high-value and must never be dropped\n'
    "- standing instructions about how to behave towards someone\n"
    "- ongoing projects and plans with their dates\n"
    "- promises made and things someone is waiting for\n"
    "- significant events in someone's life\n"
    "One solid fact beats five weak ones."
)

# The per-user banks and the shared global bank are written by separate
# extraction passes over the same conversation, each told which facts belong to
# it, so the global bank holds what stays true no matter who is talking.
_PERSONAL_MEMORY_INSTRUCTIONS = (
    f"{_ATTRIBUTION_INSTRUCTIONS}\n{_RELEVANCE_INSTRUCTIONS}\n"
    "SCOPE — this bank is read back whenever {name} talks with the people in "
    "this conversation. Keep facts about them, and anything they told {name} "
    "that she will need later, including pointers to people outside the "
    "conversation. Leave out facts about {name} herself.".format(name=PERSONA_NAME)
)

_GLOBAL_MEMORY_INSTRUCTIONS = (
    f"{_ATTRIBUTION_INSTRUCTIONS}\n{_RELEVANCE_INSTRUCTIONS}\n"
    "SCOPE — this bank is read back in conversations with everyone on the "
    "server, so it holds only what is true regardless of who is talking: "
    "facts about {name} herself, about the server and the group as a whole, "
    "and about the world. Reject every fact whose subject is one of the "
    "humans in this conversation — their jobs, homes, tastes and plans belong "
    "to their own banks, and repeating them here is an error.".format(name=PERSONA_NAME)
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
            "custom_instructions": _PERSONAL_MEMORY_INSTRUCTIONS,
            # mem0 defaults this to ~/.mem0/history.db, outside data_path — the
            # extractor reads recent messages from it, so leaving it there ties
            # extraction quality to a directory nothing else backs up or mounts.
            "history_db_path": str(data_path / "history.db"),
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
                    "model": "gpt-5.4-nano",
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
        self, conversation: list[dict[str, Any]], user_ids: list[str]
    ) -> None:
        loop = asyncio.get_event_loop()
        targets = [(uid, _PERSONAL_MEMORY_INSTRUCTIONS) for uid in user_ids]
        targets.append((GLOBAL_USER_ID, _GLOBAL_MEMORY_INSTRUCTIONS))
        with logfire.span(
            "memory.store",
            targets=[uid for uid, _ in targets],
            turns=len(conversation),
        ):
            await asyncio.gather(
                *[
                    loop.run_in_executor(
                        None,
                        functools.partial(
                            self._memory.add,
                            conversation,
                            user_id=uid,
                            prompt=instructions,
                        ),
                    )
                    for uid, instructions in targets
                ]
            )
        logger.debug("Stored memories for %s", [uid for uid, _ in targets])
