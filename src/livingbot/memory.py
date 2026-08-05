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
    "generic word 'User'. "
    "All of the above is a rule for wording memories, not something to "
    "remember: never store a memory about what someone is called or which "
    'display name they use (e.g. "Kuba is named Kuba"). '
    "Write every memory in the language the conversation is in, so that a "
    "Polish exchange yields Polish memories."
)

# ADDITIVE_EXTRACTION_PROMPT tells the model to extract when in doubt and treats
# casual chat as prime material, which on a Discord server fills the store with
# greetings, banter and one-off jokes. These instructions raise the bar back to
# durable facts; mem0 gives custom instructions "highest priority", so they win
# over the base prompt's bias. The keep list leads and is marked as mandatory
# because leading with the rejections instead made the extractor discard even
# plain "I love dark chocolate"; the rejections carry the override marker so
# they still beat the base prompt, which otherwise yields entries like
# "Mugda reacted to Kuba's plan by wishing him luck".
_REJECTION_INSTRUCTIONS = (
    "OVERRIDE — the rules below beat every instruction above them, including "
    "the guidance to extract when in doubt and the claim that casual chat is "
    "valuable. Never extract:\n"
    "- greetings, goodbyes, reactions and filler\n"
    "- jokes, banter, teasing, sarcasm, memes and wordplay\n"
    "- any statement describing the exchange itself — anything shaped like "
    f'"X said/asked/replied/reacted/joked/wished...", and in particular every '
    f"sentence about what {PERSONA_NAME} said or how she reacted\n"
    "- what someone is doing right now or in the next few minutes, and "
    "momentary moods\n"
    "- how something was phrased, which emoji, slang or spelling was used\n"
    "A message carrying nothing from the keep list yields no memory at all."
)

# The per-user banks and the shared global bank are written by separate
# extraction passes over the same conversation, so the global bank holds what
# stays true no matter who is talking. Each pass gets its own keep list rather
# than a shared one plus a scope caveat: a shared list ordering "capture
# everyone's job" and a caveat saying "but not for the people here" contradict
# each other, and the mandatory-sounding list won — Kuba's new job kept landing
# in the global bank.
_PERSONAL_MEMORY_INSTRUCTIONS = (
    f"{_ATTRIBUTION_INSTRUCTIONS}\n"
    "This bank is read back whenever {name} talks with the people in this "
    "conversation, and holds facts about them — never about {name} herself. "
    "Capture every one of these whenever it appears; none may be dropped:\n"
    "- who they are and their stable circumstances: work, studies, where they "
    "live, family, pets, health\n"
    "- their lasting preferences, tastes and strong opinions, including food, "
    "drink, music, games and anything else they say they love or hate\n"
    "- who to ask about what, even when that person is not in the "
    'conversation (e.g. "for anything about the Minecraft server, ask '
    'Weronika")\n'
    "- standing instructions they gave about how {name} should behave towards "
    "them\n"
    "- their ongoing projects and plans with dates\n"
    "- promises made to them and things they are waiting for\n"
    "- significant events in their lives\n"
    "{rejections}".format(name=PERSONA_NAME, rejections=_REJECTION_INSTRUCTIONS)
)

_GLOBAL_MEMORY_INSTRUCTIONS = (
    f"{_ATTRIBUTION_INSTRUCTIONS}\n"
    "This bank is read back in conversations with everyone on the server, so "
    "it holds only what stays true regardless of who is talking. Capture:\n"
    "- what {name} herself is like: her tastes, opinions, habits, what she "
    "owns, what she has done and what she plans\n"
    "- how the server and the group work: recurring events, rules, roles, who "
    "runs what\n"
    "- facts about the world that came up and are worth knowing later\n"
    "The people in this conversation each have their own bank. Their jobs, "
    "homes, families, tastes and plans go there, never here — extracting a "
    "fact about one of them into this bank is an error, however durable that "
    "fact is. If the conversation says nothing about {name}, the server or "
    "the world, extract nothing.\n"
    "{rejections}".format(name=PERSONA_NAME, rejections=_REJECTION_INSTRUCTIONS)
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
