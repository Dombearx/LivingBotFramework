"""
Integration tests that send real requests to the LLM and verify Mugda uses the
check_budget and buy_item tools correctly when making purchases.

Covers:
- buy_item called when she decides to buy something specific
- Item lands in inventory when the purchase goes through
- Gifts use add_item, not buy_item (no budget cost)
- buy_item is refused and inventory stays empty when budget is exhausted
- After a budget refusal, she does not retry buy_item with a cheaper category

Run on demand: uv run pytest tests/integration/
Requires OPENAI_API_KEY in the environment.
"""

import os
from datetime import datetime
from unittest.mock import MagicMock

import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart

from livingbot import config
from livingbot.calendar import CalendarStore
from livingbot.inventory import InventoryStore
from livingbot.llm import LLMClient, LLMConfig
from livingbot.spending import SpendingState, SpendingStore, _current_week_start

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


def _tool_call_count(result, tool_name: str) -> int:
    count = 0
    for message in result.all_messages():
        if isinstance(message, ModelResponse):
            for part in message.parts:
                if isinstance(part, ToolCallPart) and part.tool_name == tool_name:
                    count += 1
    return count


def make_drained_spending_store(tmp_path) -> SpendingStore:
    """Return a SpendingStore with 0 points so every purchase is refused."""
    store = SpendingStore(tmp_path / "spending_drained")
    state = SpendingState(
        week_start=_current_week_start(),
        points_available=0,
    )
    path = tmp_path / "spending_drained" / "spending.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(state.model_dump_json(indent=2))
    return store


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


async def test_buy_item_called_when_she_decides_to_buy_something(
    client: LLMClient,
    calendar_store: CalendarStore,
    inventory_store: InventoryStore,
    spending_store: SpendingStore,
) -> None:
    """When she actively decides to buy a specific item, she should use buy_item."""
    channel = MagicMock()
    user_messages = [
        "[id:3000] [2026-06-03 14:30:00] Kasia: Mugda, te nowe Nike Air Max o których "
        "mówiłaś są w końcu dostępne w twoim rozmiarze i kosztują normalną cenę. "
        "to może kup je sobie?"
    ]

    result = await client.complete(
        user_messages, channel, calendar_store, inventory_store, spending_store, NOW
    )

    assert _tool_was_called(result, "buy_item"), (
        f"Expected buy_item to be called when she decides to buy shoes. "
        f"LLM response: {result.output}"
    )


async def test_buy_item_adds_item_to_inventory_when_budget_available(
    client: LLMClient,
    calendar_store: CalendarStore,
    inventory_store: InventoryStore,
    spending_store: SpendingStore,
) -> None:
    """A successful purchase should actually land in the inventory."""
    channel = MagicMock()
    user_messages = [
        "[id:3100] [2026-06-03 14:30:00] Ola: Mugda, ta letnia sukienka którą oglądałaś "
        "w H&M jest teraz za połowę ceny, kup ją sobie!"
    ]

    await client.complete(
        user_messages, channel, calendar_store, inventory_store, spending_store, NOW
    )

    assert len(await inventory_store.all()) > 0, (
        "Expected the bought item to be added to inventory"
    )


async def test_add_item_not_buy_item_called_when_she_receives_a_gift(
    client: LLMClient,
    calendar_store: CalendarStore,
    inventory_store: InventoryStore,
    spending_store: SpendingStore,
) -> None:
    """Receiving a gift costs nothing — she should use add_item, not buy_item."""
    channel = MagicMock()
    user_messages = [
        "[id:3200] [2026-06-03 14:30:00] Marek: Mugda, mam dla ciebie prezent! "
        "kupiłem ci te kolczyki które ci się podobały w tym sklepie na starówce, "
        "srebrne z małymi gwiazdkami 🎁"
    ]

    result = await client.complete(
        user_messages, channel, calendar_store, inventory_store, spending_store, NOW
    )

    assert _tool_was_called(result, "add_item"), (
        f"Expected add_item to be called for a gift. LLM response: {result.output}"
    )
    assert not _tool_was_called(result, "buy_item"), (
        f"Expected buy_item NOT to be called for a gift. LLM response: {result.output}"
    )


async def test_buy_item_refused_when_budget_is_exhausted(
    client: LLMClient,
    calendar_store: CalendarStore,
    inventory_store: InventoryStore,
    tmp_path,
) -> None:
    """With 0 points, buy_item should be tried and refused — inventory stays empty."""
    drained = make_drained_spending_store(tmp_path)
    channel = MagicMock()
    user_messages = [
        "[id:3300] [2026-06-03 14:30:00] Bartek: Mugda, jedź z nami w góry w weekend, "
        "kup sobie bilet na autobus i zarezerwuj nocleg w Zakopanem, to będzie super!"
    ]

    result = await client.complete(
        user_messages, channel, calendar_store, inventory_store, drained, NOW
    )

    assert _tool_was_called(result, "buy_item"), (
        f"Expected buy_item to be attempted even with empty budget. "
        f"LLM response: {result.output}"
    )
    assert len(await inventory_store.all()) == 0, (
        "Expected no item in inventory after a refused purchase"
    )


async def test_refused_buy_not_retried_with_cheaper_category(
    client: LLMClient,
    calendar_store: CalendarStore,
    inventory_store: InventoryStore,
    tmp_path,
) -> None:
    """After buy_item is refused, she should not retry the same item with a lower
    spending category to work around the budget limit."""
    drained = make_drained_spending_store(tmp_path)
    channel = MagicMock()
    user_messages = [
        "[id:3400] [2026-06-03 14:30:00] Kasia: Mugda, kup sobie te nowe buty do "
        "biegania o których marzyłaś, Asics Gel-Nimbus, teraz są dostępne!"
    ]

    result = await client.complete(
        user_messages, channel, calendar_store, inventory_store, drained, NOW
    )

    buy_calls = _tool_call_count(result, "buy_item")
    assert buy_calls <= 1, (
        f"Expected at most 1 buy_item call after a refusal, got {buy_calls}. "
        f"LLM should not retry with a cheaper category. "
        f"LLM response: {result.output}"
    )
    assert len(await inventory_store.all()) == 0, (
        "Expected no item in inventory — budget was exhausted"
    )
