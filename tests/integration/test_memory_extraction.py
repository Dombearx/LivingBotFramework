"""
Integration tests that send real requests to mem0's fact extractor and verify
the custom_instructions in MemoryStore.create actually change how memories are
attributed — persona by name instead of "Assistant", Discord display name
instead of "User".

Run on demand: uv run pytest tests/integration/
Requires OPENROUTER_API_KEY in the environment.
"""

import os
import re

import pytest

from livingbot.memory import MemoryStore
from livingbot.prompts import PERSONA_NAME

pytestmark = pytest.mark.skipif(
    not os.environ.get("OPENROUTER_API_KEY"),
    reason="OPENROUTER_API_KEY not set",
)


def _joined_memory_texts(memories: list[dict]) -> str:
    return " ".join(memory["memory"] for memory in memories)


async def test_bot_opinion_is_attributed_to_the_persona_not_generic_assistant(
    tmp_path,
) -> None:
    """A personal opinion Mugda shares about herself should be attributed to
    her by name, not stored as a generic "Assistant" fact."""
    store = MemoryStore.create(tmp_path)
    conversation = [
        {
            "role": "user",
            "content": (
                "[id:1] [2026-07-27 10:00:00] Kuba: jaki model językowy jest "
                "twoim ulubionym?"
            ),
        },
        {
            "role": "assistant",
            "content": (
                "Zdecydowanie GPT-4o - działa bez zbędnego dramatu i szybko "
                "ogarnia zadania, to model który wybieram najczęściej."
            ),
        },
    ]

    await store.store(conversation, user_id="test-bot-opinion-user")
    memories = await store.all("test-bot-opinion-user")

    assert memories, "Expected at least one memory to be extracted"
    joined = _joined_memory_texts(memories)
    assert not re.search(r"\bassistant\b", joined, re.IGNORECASE), (
        f"Expected no generic 'Assistant' attribution, got memories: {memories}"
    )
    assert re.search(rf"\b{PERSONA_NAME}\b", joined, re.IGNORECASE), (
        f"Expected the opinion attributed to {PERSONA_NAME} by name, "
        f"got memories: {memories}"
    )


async def test_user_personal_fact_is_attributed_by_discord_display_name(
    tmp_path,
) -> None:
    """A personal fact the user shares should be attributed by their Discord
    display name, not stored as a generic "User" fact."""
    store = MemoryStore.create(tmp_path)
    conversation = [
        {
            "role": "user",
            "content": (
                "[id:2] [2026-07-27 10:05:00] Kuba: swoją drogą, uwielbiam "
                "ciemną czekoladę, zwłaszcza tą z solą morską"
            ),
        },
        {
            "role": "assistant",
            "content": "O, ciemna czekolada z solą morską to naprawdę dobry wybór",
        },
    ]

    await store.store(conversation, user_id="test-user-fact-user")
    memories = await store.all("test-user-fact-user")

    assert memories, "Expected at least one memory to be extracted"
    joined = _joined_memory_texts(memories)
    assert not re.search(r"\buser\b", joined, re.IGNORECASE), (
        f"Expected no generic 'User' attribution, got memories: {memories}"
    )
    assert re.search(r"\bkuba\b", joined, re.IGNORECASE), (
        f"Expected the fact attributed to Kuba by name, got memories: {memories}"
    )
