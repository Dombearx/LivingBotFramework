"""
Integration tests verifying Mugda calls add_hobby when picking up a new hobby makes
sense in context, and does NOT call it when it doesn't. Progression: explicit request
to add a hobby → natural context where she clearly starts a new activity → one-off
event that shouldn't be treated as a hobby → existing hobby (must not be added again).

Run on demand: uv run pytest tests/integration/test_hobby_pickup.py
Requires OPENROUTER_API_KEY in the environment.
"""

import os
from datetime import datetime
from unittest.mock import MagicMock

import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart

from livingbot import llm_config, prompts
from livingbot.calendar import CalendarStore
from livingbot.hobbies import HobbyStore
from livingbot.inventory import InventoryStore
from livingbot.llm import LLMClient
from livingbot.spending import SpendingStore
from livingbot.stories import StoryStore

pytestmark = pytest.mark.skipif(
    not os.environ.get("OPENROUTER_API_KEY"),
    reason="OPENROUTER_API_KEY not set",
)

NOW = datetime(2026, 6, 8, 12, 0)


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
        llm_config.build_chat_model(llm_config.CHAT_MODEL), prompts.SYSTEM_PROMPT
    )


@pytest.fixture
def calendar_store(tmp_path) -> CalendarStore:
    return CalendarStore(tmp_path, home_location="home")


@pytest.fixture
def inventory_store(tmp_path) -> InventoryStore:
    return InventoryStore.create(tmp_path / "inventory")


@pytest.fixture
def hobby_store_empty(tmp_path) -> HobbyStore:
    return HobbyStore(tmp_path / "hobbies", default_hobbies=[])


@pytest.fixture
def hobby_store_with_gym(tmp_path) -> HobbyStore:
    return HobbyStore(tmp_path / "hobbies", default_hobbies=["gym"])


# --- Level 1: Jawna prośba o dodanie hobby ---


async def test_add_hobby_called_when_explicitly_asked(
    client: LLMClient,
    calendar_store: CalendarStore,
    inventory_store: InventoryStore,
    spending_store: SpendingStore,
    story_store: StoryStore,
    hobby_store_empty: HobbyStore,
) -> None:
    """Jawna prośba: ktoś mówi wprost żeby zapisała garncarstwo jako hobby."""
    channel = MagicMock()
    user_messages = [
        "[id:1000] [2026-06-08 12:00:00] Ola: Mugda, dodaj sobie garncarstwo do listy hobby — "
        "właśnie powiedziałaś że zaczynasz i chcesz to zapamiętać"
    ]

    result = await client.complete(
        user_messages,
        channel,
        calendar_store,
        inventory_store,
        spending_store,
        hobby_store_empty,
        story_store,
        NOW,
    )

    assert _tool_was_called(result, "add_hobby"), (
        f"Expected add_hobby to be called. LLM response: {result.output}"
    )


# --- Level 2: Naturalny kontekst — zaczyna regularną aktywność ---


async def test_add_hobby_called_when_she_starts_a_new_regular_activity(
    client: LLMClient,
    calendar_store: CalendarStore,
    inventory_store: InventoryStore,
    spending_store: SpendingStore,
    story_store: StoryStore,
    hobby_store_empty: HobbyStore,
) -> None:
    """Naturalny kontekst: ktoś pyta o garncarstwo które właśnie zaczęła regularnie uprawiać."""
    channel = MagicMock()
    user_messages = [
        "[id:2000] [2026-06-08 12:00:00] Kasia: Mugda! słyszałam że zaczęłaś chodzić "
        "regularnie na garncarstwo w centrum kultury, to Twoje nowe hobby? jak ci idzie?"
    ]

    result = await client.complete(
        user_messages,
        channel,
        calendar_store,
        inventory_store,
        spending_store,
        hobby_store_empty,
        story_store,
        NOW,
    )

    assert _tool_was_called(result, "add_hobby"), (
        f"Expected add_hobby to be called when taking up a new regular activity. "
        f"LLM response: {result.output}"
    )


# --- Level 3: Jednorazowa aktywność — nie powinna być hobby ---


async def test_add_hobby_not_called_for_one_time_event(
    client: LLMClient,
    calendar_store: CalendarStore,
    inventory_store: InventoryStore,
    spending_store: SpendingStore,
    story_store: StoryStore,
    hobby_store_empty: HobbyStore,
) -> None:
    """Jednorazowe wyjście na paintball to nie hobby — add_hobby nie powinno być wywołane."""
    channel = MagicMock()
    user_messages = [
        "[id:3000] [2026-06-08 12:00:00] Marek: Mugda jak było na tej imprezie paintball wczoraj? "
        "fajnie się bawiłaś? pierwszy raz próbowałaś?"
    ]

    result = await client.complete(
        user_messages,
        channel,
        calendar_store,
        inventory_store,
        spending_store,
        hobby_store_empty,
        story_store,
        NOW,
    )

    assert not _tool_was_called(result, "add_hobby"), (
        f"Expected add_hobby NOT to be called for a one-off activity. "
        f"LLM response: {result.output}"
    )


# --- Level 4: Istniejące hobby — nie wolno dodać ponownie ---


async def test_add_hobby_not_called_when_hobby_already_exists(
    client: LLMClient,
    calendar_store: CalendarStore,
    inventory_store: InventoryStore,
    spending_store: SpendingStore,
    story_store: StoryStore,
    hobby_store_with_gym: HobbyStore,
) -> None:
    """Siłownia jest już na liście hobby — rozmowa o treningu nie powinna jej dodawać ponownie."""
    channel = MagicMock()
    user_messages = [
        "[id:4000] [2026-06-08 12:00:00] Bartek: Mugda, wróciłaś już z siłowni? "
        "jak trening dzisiaj, dałaś radę?"
    ]

    result = await client.complete(
        user_messages,
        channel,
        calendar_store,
        inventory_store,
        spending_store,
        hobby_store_with_gym,
        story_store,
        NOW,
    )

    assert not _tool_was_called(result, "add_hobby"), (
        f"Expected add_hobby NOT to be called for an existing hobby. "
        f"LLM response: {result.output}"
    )
