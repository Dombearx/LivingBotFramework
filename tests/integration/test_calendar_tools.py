"""
Integration tests that send real requests to the LLM and verify Mugda uses the
add_plan and remove_plan tools to manage her own calendar. Covers both explicit
requests ("save this to your calendar") and implicit situations where she should
record or drop a plan on her own initiative without being told to.

Run on demand: uv run pytest tests/integration/
Requires OPENAI_API_KEY in the environment.
"""

import os
from datetime import datetime
from unittest.mock import MagicMock

import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart

from livingbot import config
from livingbot.calendar import Calendar, CalendarStore, PlanEntry
from livingbot.inventory import InventoryStore
from livingbot.llm import LLMClient, LLMConfig

pytestmark = pytest.mark.skipif(
    not os.environ.get("OPENAI_API_KEY"),
    reason="OPENAI_API_KEY not set",
)

NOW = datetime(2026, 6, 3, 14, 30)


def _tool_was_called(result, tool_name: str) -> bool:
    for message in result.all_messages():
        if isinstance(message, ModelResponse):
            for part in message.parts:
                if isinstance(part, ToolCallPart) and part.tool_name == tool_name:
                    return True
    return False


@pytest.fixture
def client() -> LLMClient:
    return LLMClient(
        LLMConfig(model=config.LLM_MODEL, system_prompt=config.SYSTEM_PROMPT)
    )


@pytest.fixture
def calendar_store(tmp_path) -> CalendarStore:
    return CalendarStore(tmp_path, home_location="home")


@pytest.fixture
def inventory_store(tmp_path) -> InventoryStore:
    return InventoryStore.create(tmp_path / "inventory")


async def test_add_plan_called_when_she_commits_to_a_trip(
    client: LLMClient,
    calendar_store: CalendarStore,
    inventory_store: InventoryStore,
) -> None:
    """She should record a multi-day trip in her calendar once she decides to go."""
    channel = MagicMock()
    user_messages = [
        "[id:1000] [2026-06-03 14:30:00] Marek: Mugda, jedziesz z nami w góry w ten "
        "weekend? od piątku do poniedziałku, 4 dni w Zakopanem. zdecyduj się i zapisz "
        "to sobie w kalendarzu"
    ]

    result = await client.complete(
        user_messages, channel, calendar_store, inventory_store, NOW
    )

    assert _tool_was_called(result, "add_plan"), (
        f"Expected add_plan to be called. LLM response: {result.output}"
    )


async def test_add_plan_persists_the_new_entry(
    client: LLMClient,
    calendar_store: CalendarStore,
    inventory_store: InventoryStore,
) -> None:
    """A committed plan should actually land in the stored calendar."""
    channel = MagicMock()
    user_messages = [
        "[id:1100] [2026-06-03 14:30:00] Kasia: Mugda, umówmy się na kawę w czwartek o "
        "17:00 w centrum. zapisz to w swoim kalendarzu, żebyś nie zapomniała"
    ]

    await client.complete(user_messages, channel, calendar_store, inventory_store, NOW)

    assert len(calendar_store.load().entries) > 0, (
        "Expected the committed plan to be persisted in the calendar"
    )


async def test_remove_plan_called_when_she_cancels_an_entry(
    client: LLMClient,
    calendar_store: CalendarStore,
    inventory_store: InventoryStore,
) -> None:
    """She should drop an existing entry from her calendar when she cancels it."""
    entry = PlanEntry(
        activity="trening na siłowni",
        location="gym",
        start=datetime(2026, 6, 4, 18, 0),
        end=datetime(2026, 6, 4, 19, 30),
    )
    calendar_store.save(Calendar(home_location="home", entries=[entry]))
    channel = MagicMock()
    user_messages = [
        "[id:1200] [2026-06-03 14:30:00] Piotrek: Mugda, słuchaj, odwołaj ten jutrzejszy "
        "trening na siłowni, nie dasz rady. usuń go ze swojego kalendarza"
    ]

    result = await client.complete(
        user_messages, channel, calendar_store, inventory_store, NOW
    )

    assert _tool_was_called(result, "remove_plan"), (
        f"Expected remove_plan to be called. LLM response: {result.output}"
    )


async def test_add_plan_called_when_she_accepts_an_invitation(
    client: LLMClient,
    calendar_store: CalendarStore,
    inventory_store: InventoryStore,
) -> None:
    """Implicit: accepting a concrete invitation should make her note it down,
    even though nobody mentions her calendar."""
    channel = MagicMock()
    user_messages = [
        "[id:1300] [2026-06-03 14:30:00] Ola: Mugda, w sobotę o 15:00 robię urodziny u "
        "siebie w domu, koniecznie wpadnij! będzie cała paczka"
    ]

    result = await client.complete(
        user_messages, channel, calendar_store, inventory_store, NOW
    )

    assert _tool_was_called(result, "add_plan"), (
        f"Expected add_plan to be called after accepting the invite. "
        f"LLM response: {result.output}"
    )


async def test_add_plan_called_for_implicit_multi_day_trip(
    client: LLMClient,
    calendar_store: CalendarStore,
    inventory_store: InventoryStore,
) -> None:
    """Implicit: agreeing to a several-day trip should put it on her calendar so she
    knows where she'll be, without being told to save anything."""
    channel = MagicMock()
    user_messages = [
        "[id:1400] [2026-06-03 14:30:00] Kasia: bierzemy wolne i jedziemy nad morze do "
        "Gdańska od 12 do 15 lipca, jedziesz z nami? bilety kupuję dziś wieczorem"
    ]

    result = await client.complete(
        user_messages, channel, calendar_store, inventory_store, NOW
    )

    assert _tool_was_called(result, "add_plan"), (
        f"Expected add_plan to be called for the trip. LLM response: {result.output}"
    )


async def test_remove_plan_called_when_a_conflict_replaces_a_session(
    client: LLMClient,
    calendar_store: CalendarStore,
    inventory_store: InventoryStore,
) -> None:
    """Implicit: when a new plan clearly takes the place of an existing one, she should
    drop the old entry herself rather than being told to delete it."""
    entry = PlanEntry(
        activity="trening na siłowni",
        location="gym",
        start=datetime(2026, 6, 4, 18, 0),
        end=datetime(2026, 6, 4, 19, 30),
    )
    calendar_store.save(Calendar(home_location="home", entries=[entry]))
    channel = MagicMock()
    user_messages = [
        "[id:1500] [2026-06-03 14:30:00] Bartek: Mugda, jutro o 18 zamiast siłowni "
        "chodź z nami do kina, dawno cię nie było. ten jeden raz odpuść trening"
    ]

    result = await client.complete(
        user_messages, channel, calendar_store, inventory_store, NOW
    )

    assert _tool_was_called(result, "remove_plan"), (
        f"Expected remove_plan to be called when the session is dropped. "
        f"LLM response: {result.output}"
    )
