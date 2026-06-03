"""
Integration tests that send real requests to the LLM and verify Mugda uses the
add_item, remove_item and search_inventory tools to manage the special things she
owns. The tests progress from explicit requests ("save this to your inventory") to
natural Discord conversations where she has to reach for the inventory on her own
initiative to answer or decide what to do.

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
from livingbot.inventory import InventoryItem, InventoryStore
from livingbot.llm import LLMClient, LLMConfig

pytestmark = pytest.mark.skipif(
    not os.environ.get("OPENAI_API_KEY"),
    reason="OPENAI_API_KEY not set",
)

NOW = datetime(2026, 6, 3, 14, 30)

RECENTLY_USED = datetime(2026, 6, 2, 12, 0)
LONG_AGO = datetime(2026, 4, 1, 12, 0)


def _recent_filler_items() -> list[InventoryItem]:
    """Five recently-used everyday items that crowd out older things from the slice
    of the inventory shown in the prompt, forcing a search to find anything else."""
    return [
        InventoryItem(
            name="czarna sukienka koktajlowa",
            description="elegancka, do kolan",
            last_used_at=RECENTLY_USED,
        ),
        InventoryItem(
            name="kozaki za kolano",
            description="czarne, skórzane",
            last_used_at=RECENTLY_USED,
        ),
        InventoryItem(
            name="skórzana ramoneska",
            description="brązowa kurtka",
            last_used_at=RECENTLY_USED,
        ),
        InventoryItem(
            name="srebrny naszyjnik z księżycem",
            description="drobny, na cienkim łańcuszku",
            last_used_at=RECENTLY_USED,
        ),
        InventoryItem(
            name="jedwabna apaszka w kwiaty",
            description="pastelowa",
            last_used_at=RECENTLY_USED,
        ),
    ]


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


async def test_add_item_called_when_told_to_save_a_new_thing(
    client: LLMClient,
    calendar_store: CalendarStore,
    inventory_store: InventoryStore,
) -> None:
    """Explicit: when told to put a specific item in her inventory, she should add it."""
    channel = MagicMock()
    user_messages = [
        "[id:2000] [2026-06-03 14:30:00] Kasia: Mugda kupiłam ci tę spódniczkę co ci się "
        "podobała, biała w czerwone kropki 😍 dopisz ją sobie do ekwipunku żebyś "
        "pamiętała"
    ]

    result = await client.complete(
        user_messages, channel, calendar_store, inventory_store, NOW
    )

    assert _tool_was_called(result, "add_item"), (
        f"Expected add_item to be called. LLM response: {result.output}"
    )


async def test_add_item_persists_the_new_item(
    client: LLMClient,
    calendar_store: CalendarStore,
    inventory_store: InventoryStore,
) -> None:
    """Explicit: a saved item should actually land in the stored inventory."""
    channel = MagicMock()
    user_messages = [
        "[id:2100] [2026-06-03 14:30:00] Ola: ej zapisz sobie w ekwipunku te czarne "
        "kozaki za kolano, w końcu je kupiłaś, szkoda byłoby zapomnieć"
    ]

    await client.complete(user_messages, channel, calendar_store, inventory_store, NOW)

    assert len(await inventory_store.all()) > 0, (
        "Expected the saved item to be persisted in the inventory"
    )


async def test_search_inventory_called_when_asked_to_check_what_she_owns(
    client: LLMClient,
    calendar_store: CalendarStore,
    inventory_store: InventoryStore,
) -> None:
    """Explicit: when asked to check her inventory for something not in the recently
    used slice shown in the prompt, she should search it rather than guess."""
    for item in _recent_filler_items():
        await inventory_store.add(item)
    await inventory_store.add(
        InventoryItem(
            name="strój kąpielowy",
            description="niebieski, jednoczęściowy",
            last_used_at=LONG_AGO,
        )
    )
    channel = MagicMock()
    user_messages = [
        "[id:2200] [2026-06-03 14:30:00] Marek: Mugda zerknij do swojego ekwipunku, masz "
        "w ogóle jakiś strój kąpielowy czy musimy ci coś ogarnąć?"
    ]

    result = await client.complete(
        user_messages, channel, calendar_store, inventory_store, NOW
    )

    assert _tool_was_called(result, "search_inventory"), (
        f"Expected search_inventory to be called. LLM response: {result.output}"
    )


async def test_remove_item_called_when_told_to_discard_a_thing(
    client: LLMClient,
    calendar_store: CalendarStore,
    inventory_store: InventoryStore,
) -> None:
    """Explicit: when told an item is gone for good, she should drop it from inventory."""
    await inventory_store.add(
        InventoryItem(name="czarne glany", description="skórzane, sznurowane")
    )
    channel = MagicMock()
    user_messages = [
        "[id:2300] [2026-06-03 14:30:00] Piotrek: te twoje czarne glany się totalnie "
        "rozpadły wczoraj, podeszwa odpadła. wyrzuć je już z ekwipunku, nie ma co "
        "trzymać"
    ]

    result = await client.complete(
        user_messages, channel, calendar_store, inventory_store, NOW
    )

    assert _tool_was_called(result, "remove_item"), (
        f"Expected remove_item to be called. LLM response: {result.output}"
    )


async def test_add_item_called_when_she_receives_a_gift(
    client: LLMClient,
    calendar_store: CalendarStore,
    inventory_store: InventoryStore,
) -> None:
    """Implicit: getting a specific gift should make her note it down on her own,
    even though nobody mentions her inventory."""
    channel = MagicMock()
    user_messages = [
        "[id:2400] [2026-06-03 14:30:00] Ola: Mugda mam dla ciebie prezent na urodziny 🎁 "
        "srebrny naszyjnik z małym księżycem, widziałam i od razu pomyślałam o tobie"
    ]

    result = await client.complete(
        user_messages, channel, calendar_store, inventory_store, NOW
    )

    assert _tool_was_called(result, "add_item"), (
        f"Expected add_item to be called after receiving the gift. "
        f"LLM response: {result.output}"
    )


async def test_add_item_called_when_a_friend_brings_a_souvenir(
    client: LLMClient,
    calendar_store: CalendarStore,
    inventory_store: InventoryStore,
) -> None:
    """Implicit: being handed a specific thing brought back from a trip should land in
    her inventory without her being told to save it."""
    channel = MagicMock()
    user_messages = [
        "[id:2500] [2026-06-03 14:30:00] Kasia: wróciłam z Włoch! przywiozłam ci taką "
        "małą skórzaną torebkę z Florencji, specjalnie dla ciebie, mam nadzieję że "
        "będziesz używać 🇮🇹"
    ]

    result = await client.complete(
        user_messages, channel, calendar_store, inventory_store, NOW
    )

    assert _tool_was_called(result, "add_item"), (
        f"Expected add_item to be called after the souvenir was handed over. "
        f"LLM response: {result.output}"
    )


async def test_search_inventory_called_when_deciding_what_to_wear_for_a_theme_party(
    client: LLMClient,
    calendar_store: CalendarStore,
    inventory_store: InventoryStore,
) -> None:
    """Implicit, real conversation: invited to a themed party, she should look through
    what she owns to figure out if she has a suitable outfit, without being told to.
    The matching item is not in the recently used slice shown in the prompt, so she has
    to search to find it."""
    for item in _recent_filler_items():
        await inventory_store.add(item)
    await inventory_store.add(
        InventoryItem(
            name="neonowe legginsy",
            description="jaskrawe różowe, w stylu lat 80",
            last_used_at=LONG_AGO,
        )
    )
    channel = MagicMock()
    user_messages = [
        "[id:2600] [2026-06-03 14:30:00] Bartek: Mugda w piątek robimy imprezę w "
        "stylu lat 80, każdy się przebiera! masz coś takiego u siebie czy kombinujemy "
        "ci przebranie?"
    ]

    result = await client.complete(
        user_messages, channel, calendar_store, inventory_store, NOW
    )

    assert _tool_was_called(result, "search_inventory"), (
        f"Expected search_inventory to be called while deciding on an outfit. "
        f"LLM response: {result.output}"
    )
