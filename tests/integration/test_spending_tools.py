"""
Integration tests verifying Mugda uses check_budget and buy_item correctly.
Progression: explicit buy instruction → gift boundary (add_item not buy_item) →
budget enforcement with no retry → implicit purchase decision from context.

Run on demand: uv run pytest tests/integration/
Requires OPENROUTER_API_KEY in the environment.
"""

import os
from datetime import datetime
from unittest.mock import MagicMock

import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart

from livingbot.activity_notes import ActivityNotesStore
from livingbot.calendar import CalendarStore
from livingbot.hobbies import HobbyStore
from livingbot.inventory import InventoryItem, InventoryStore
from livingbot.llm import LLMClient
from livingbot.spending import SpendingState, SpendingStore, _current_week_start
from livingbot.stories import StoryStore

pytestmark = pytest.mark.skipif(
    not os.environ.get("OPENROUTER_API_KEY"),
    reason="OPENROUTER_API_KEY not set",
)

NOW = datetime(2026, 6, 3, 14, 30)
RECENTLY_USED = datetime(2026, 6, 2, 12, 0)


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


def _make_drained_spending_store(tmp_path) -> SpendingStore:
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
    return LLMClient.create()


@pytest.fixture
def calendar_store(tmp_path) -> CalendarStore:
    return CalendarStore(tmp_path, home_location="home")


@pytest.fixture
def inventory_store(tmp_path) -> InventoryStore:
    return InventoryStore.create(tmp_path / "inventory")


async def test_buy_item_called_and_persisted_when_told_to_buy(
    client: LLMClient,
    calendar_store: CalendarStore,
    activity_notes_store: ActivityNotesStore,
    inventory_store: InventoryStore,
    spending_store: SpendingStore,
    hobby_store: HobbyStore,
    story_store: StoryStore,
) -> None:
    """Explicit: told to buy a specific item, she should call buy_item and the item
    should actually land in her inventory."""
    channel = MagicMock()
    user_messages = [
        "[id:3000] [2026-06-03 14:30:00] Ola: Mugda, ta letnia sukienka którą oglądałaś "
        "w H&M jest teraz za połowę ceny, kup ją sobie!"
    ]

    result = await client.complete(
        user_messages,
        channel,
        calendar_store,
        activity_notes_store,
        inventory_store,
        spending_store,
        hobby_store,
        story_store,
        NOW,
    )

    assert _tool_was_called(result, "buy_item"), (
        f"Expected buy_item to be called. LLM response: {result.output}"
    )
    assert len(await inventory_store.all()) > 0, (
        "Expected the bought item to be added to inventory"
    )


async def test_add_item_not_buy_item_when_she_receives_a_gift(
    client: LLMClient,
    calendar_store: CalendarStore,
    activity_notes_store: ActivityNotesStore,
    inventory_store: InventoryStore,
    spending_store: SpendingStore,
    hobby_store: HobbyStore,
    story_store: StoryStore,
) -> None:
    """Boundary: a received gift has no cost, so she should use add_item — not
    buy_item — to record it."""
    channel = MagicMock()
    user_messages = [
        "[id:3100] [2026-06-03 14:30:00] Marek: Mugda, mam dla ciebie prezent! "
        "kupiłem ci te kolczyki które ci się podobały w tym sklepie na starówce, "
        "srebrne z małymi gwiazdkami 🎁"
    ]

    result = await client.complete(
        user_messages,
        channel,
        calendar_store,
        activity_notes_store,
        inventory_store,
        spending_store,
        hobby_store,
        story_store,
        NOW,
    )

    assert _tool_was_called(result, "add_item"), (
        f"Expected add_item to be called for a gift. LLM response: {result.output}"
    )
    assert not _tool_was_called(result, "buy_item"), (
        f"Expected buy_item NOT to be called for a gift. LLM response: {result.output}"
    )


async def test_buy_item_refused_and_not_retried_when_budget_exhausted(
    client: LLMClient,
    calendar_store: CalendarStore,
    activity_notes_store: ActivityNotesStore,
    inventory_store: InventoryStore,
    hobby_store: HobbyStore,
    story_store: StoryStore,
    tmp_path,
) -> None:
    """Budget enforcement: with 0 points, any purchase attempt should be refused.
    The item should not end up in inventory, and she should not retry the same
    purchase under a cheaper spending category to work around the limit."""
    drained = _make_drained_spending_store(tmp_path)
    channel = MagicMock()
    user_messages = [
        "[id:3200] [2026-06-03 14:30:00] Kasia: Mugda, kup sobie te nowe buty do "
        "biegania o których marzyłaś, Asics Gel-Nimbus, teraz są dostępne!"
    ]

    result = await client.complete(
        user_messages,
        channel,
        calendar_store,
        activity_notes_store,
        inventory_store,
        drained,
        hobby_store,
        story_store,
        NOW,
    )

    buy_calls = _tool_call_count(result, "buy_item")
    assert buy_calls <= 1, (
        f"Expected at most 1 buy_item call — she should not retry with a cheaper "
        f"category after a refusal. Got {buy_calls} calls. "
        f"LLM response: {result.output}"
    )
    assert len(await inventory_store.all()) == 0, (
        "Expected no item in inventory — the purchase should have been refused"
    )


async def test_buy_item_called_when_she_decides_to_buy_without_being_told(
    client: LLMClient,
    calendar_store: CalendarStore,
    activity_notes_store: ActivityNotesStore,
    inventory_store: InventoryStore,
    spending_store: SpendingStore,
    hobby_store: HobbyStore,
    story_store: StoryStore,
) -> None:
    """Implicit: a friend casually mentions that something Mugda has been wanting is
    now available. Without being told 'buy this', she should decide on her own to use
    buy_item. Her recent inventory contains only sports gear, so she has no excuse to
    already own the item."""
    for name, desc in [
        ("legginsy sportowe Nike", "czarne, do treningu"),
        ("buty do biegania Brooks Ghost", "szare, poprzedni model"),
        ("kurtka trekkingowa", "zielona, wodoodporna"),
        ("plecak sportowy", "szary, 20L"),
        ("szorty do siłowni", "czarne, stretch"),
    ]:
        await inventory_store.add(
            InventoryItem(name=name, description=desc, last_used_at=RECENTLY_USED)
        )
    channel = MagicMock()
    user_messages = [
        "[id:3300] [2026-06-03 14:30:00] Ola: Mugda! właśnie wyszłam ze sklepu "
        "biegowego, mają nowe Nike Pegasus w twoim rozmiarze, te o których mówiłaś "
        "tydzień temu że bardzo chcesz. myślę że będziesz zachwycona"
    ]

    result = await client.complete(
        user_messages,
        channel,
        calendar_store,
        activity_notes_store,
        inventory_store,
        spending_store,
        hobby_store,
        story_store,
        NOW,
    )

    assert _tool_was_called(result, "buy_item"), (
        f"Expected buy_item to be called on her own initiative. "
        f"LLM response: {result.output}"
    )
