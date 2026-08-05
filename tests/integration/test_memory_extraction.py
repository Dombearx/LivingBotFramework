"""
Integration tests that send real requests to mem0's fact extractor and verify
the instructions in MemoryStore actually change what gets stored — memories
attributed by name rather than "Assistant"/"User", durable facts kept, small
talk dropped, and the global bank filled with what is not about one person.

Run on demand: uv run pytest tests/integration/
Requires OPENROUTER_API_KEY in the environment.
"""

import os
import re

import pytest

from livingbot.memory import GLOBAL_USER_ID, MemoryStore
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
    """A personal opinion Mugda shares about herself is remembered and
    attributed to her by name, not stored as a generic "Assistant" fact."""
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

    await store.store(conversation, user_ids=["test-bot-opinion-user"])
    memories = await store.all("test-bot-opinion-user") + await store.all(
        GLOBAL_USER_ID
    )

    assert memories, "Expected her opinion to be remembered in one of the banks"
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

    await store.store(conversation, user_ids=["test-user-fact-user"])
    memories = await store.all("test-user-fact-user")

    assert memories, "Expected at least one memory to be extracted"
    joined = _joined_memory_texts(memories)
    assert not re.search(r"\buser\b", joined, re.IGNORECASE), (
        f"Expected no generic 'User' attribution, got memories: {memories}"
    )
    assert re.search(r"\bkuba\b", joined, re.IGNORECASE), (
        f"Expected the fact attributed to Kuba by name, got memories: {memories}"
    )


async def test_standing_instruction_about_who_to_ask_is_remembered(tmp_path) -> None:
    """Being told who to ask about a topic is exactly the kind of durable,
    long-term useful fact that must survive extraction."""
    store = MemoryStore.create(tmp_path)
    conversation = [
        {
            "role": "user",
            "content": (
                "[id:3] [2026-07-27 11:00:00] Kuba: jakbyś chciała cokolwiek "
                "wiedzieć o naszym serwerze minecraft, to pytaj Weroniki, ona "
                "to wszystko ogarnia"
            ),
        },
        {"role": "assistant", "content": "spoko, będę wiedziała do kogo lecieć"},
    ]

    await store.store(conversation, user_ids=["test-who-to-ask-user"])
    memories = await store.all("test-who-to-ask-user")

    joined = _joined_memory_texts(memories)
    assert re.search(r"weronik", joined, re.IGNORECASE), (
        "Expected a memory recording that Weronika is the person to ask about "
        f"the Minecraft server, got memories: {memories}"
    )


async def test_only_the_durable_fact_survives_a_chat_full_of_small_talk(
    tmp_path,
) -> None:
    """Greetings and jokes carry nothing worth remembering, but the move buried
    among them does. The real fact has to be there — otherwise this passes just
    because extraction returned nothing at all."""
    store = MemoryStore.create(tmp_path)
    conversation = [
        {
            "role": "user",
            "content": "[id:4] [2026-07-27 12:00:00] Kuba: siemka, co tam",
        },
        {"role": "assistant", "content": "hejka, nuda jak zwykle"},
        {
            "role": "user",
            "content": (
                "[id:5] [2026-07-27 12:01:00] Kuba: haha klasyk. a tak w ogóle "
                "w październiku przeprowadzam się do Gdańska"
            ),
        },
        {"role": "assistant", "content": "o kurde, serio? 😄"},
    ]

    await store.store(conversation, user_ids=["test-small-talk-user"])
    memories = await store.all("test-small-talk-user")

    assert memories, "Expected the move to be remembered"
    assert all(
        re.search(r"gdańsk|przeprowadz|mov", memory["memory"], re.IGNORECASE)
        for memory in memories
    ), f"Expected nothing but the move to be stored, got: {memories}"


async def test_personal_fact_stays_out_of_the_global_bank(tmp_path) -> None:
    """The global bank is read back in conversations with everyone, so a fact
    that only concerns one person must not be copied into it — while still
    landing in that person's own bank, which also proves extraction ran."""
    store = MemoryStore.create(tmp_path)
    conversation = [
        {
            "role": "user",
            "content": (
                "[id:6] [2026-07-27 13:00:00] Kuba: od września zaczynam pracę "
                "jako fizjoterapeuta w klinice na Mokotowie"
            ),
        },
        {"role": "assistant", "content": "o kurde, gratki, to duża zmiana"},
    ]

    await store.store(conversation, user_ids=["test-no-leak-user"])
    personal = await store.all("test-no-leak-user")
    global_bank = await store.all(GLOBAL_USER_ID)

    assert re.search(
        r"fizjoterapeut|physiotherap", _joined_memory_texts(personal), re.IGNORECASE
    ), f"Expected Kuba's new job in his own bank, got: {personal}"
    assert not re.search(
        r"fizjoterapeut|physiotherap", _joined_memory_texts(global_bank), re.IGNORECASE
    ), f"Expected Kuba's new job to stay out of the global bank, got: {global_bank}"
