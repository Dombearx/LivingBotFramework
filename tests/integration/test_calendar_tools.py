"""
Integration tests verifying Mugda uses add_plan and remove_plan to manage her
calendar. Progression: explicit instruction → explicit cancel → implicit save
on acceptance → implicit remove when a plan is replaced.

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
from livingbot.spending import SpendingStore

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


async def test_add_plan_called_and_persisted_when_told_to_save(
    client: LLMClient,
    calendar_store: CalendarStore,
    inventory_store: InventoryStore,
    spending_store: SpendingStore,
) -> None:
    """Explicit: told to save a plan, she should call add_plan and it should persist."""
    channel = MagicMock()
    user_messages = [
        "[id:1000] [2026-06-03 14:30:00] Kasia: Mugda, umówmy się na kawę w czwartek o "
        "17:00 w centrum. zapisz to w swoim kalendarzu, żebyś nie zapomniała"
    ]

    result = await client.complete(
        user_messages, channel, calendar_store, inventory_store, spending_store, NOW
    )

    assert _tool_was_called(result, "add_plan"), (
        f"Expected add_plan to be called. LLM response: {result.output}"
    )
    assert len(calendar_store.load().entries) > 0, (
        "Expected the plan to be persisted in the calendar"
    )


async def test_remove_plan_called_when_told_to_cancel(
    client: LLMClient,
    calendar_store: CalendarStore,
    inventory_store: InventoryStore,
    spending_store: SpendingStore,
) -> None:
    """Explicit: told to cancel an existing entry, she should call remove_plan."""
    entry = PlanEntry(
        activity="trening na siłowni",
        location="gym",
        start=datetime(2026, 6, 4, 18, 0),
        end=datetime(2026, 6, 4, 19, 30),
    )
    calendar_store.save(Calendar(home_location="home", entries=[entry]))
    channel = MagicMock()
    user_messages = [
        "[id:1100] [2026-06-03 14:30:00] Piotrek: Mugda, słuchaj, odwołaj ten jutrzejszy "
        "trening na siłowni, nie dasz rady. usuń go ze swojego kalendarza"
    ]

    result = await client.complete(
        user_messages, channel, calendar_store, inventory_store, spending_store, NOW
    )

    assert _tool_was_called(result, "remove_plan"), (
        f"Expected remove_plan to be called. LLM response: {result.output}"
    )


async def test_add_plan_called_when_she_accepts_an_invitation(
    client: LLMClient,
    calendar_store: CalendarStore,
    inventory_store: InventoryStore,
    spending_store: SpendingStore,
) -> None:
    """Implicit: accepting a concrete invitation should make her save it without being
    told to open her calendar."""
    channel = MagicMock()
    user_messages = [
        "[id:1200] [2026-06-03 14:30:00] Ola: Mugda, w sobotę o 15:00 robię urodziny u "
        "siebie w domu, koniecznie wpadnij! będzie cała paczka"
    ]

    result = await client.complete(
        user_messages, channel, calendar_store, inventory_store, spending_store, NOW
    )

    assert _tool_was_called(result, "add_plan"), (
        f"Expected add_plan to be called after accepting the invite. "
        f"LLM response: {result.output}"
    )


async def test_remove_plan_called_when_a_conflict_replaces_a_session(
    client: LLMClient,
    calendar_store: CalendarStore,
    inventory_store: InventoryStore,
    spending_store: SpendingStore,
) -> None:
    """Implicit: when a new plan clearly takes the place of an existing one, she should
    drop the old entry on her own, without being told to delete it."""
    entry = PlanEntry(
        activity="trening na siłowni",
        location="gym",
        start=datetime(2026, 6, 4, 18, 0),
        end=datetime(2026, 6, 4, 19, 30),
    )
    calendar_store.save(Calendar(home_location="home", entries=[entry]))
    channel = MagicMock()
    user_messages = [
        "[id:1300] [2026-06-03 14:30:00] Bartek: Mugda, jutro o 18 zamiast siłowni "
        "chodź z nami do kina, dawno cię nie było. ten jeden raz odpuść trening"
    ]

    result = await client.complete(
        user_messages, channel, calendar_store, inventory_store, spending_store, NOW
    )

    assert _tool_was_called(result, "remove_plan"), (
        f"Expected remove_plan to be called when the session is dropped. "
        f"LLM response: {result.output}"
    )
