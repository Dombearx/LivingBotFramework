"""
Integration tests verifying Mugda reaches for recall_past_plans when the
conversation is about what she has already been doing. Her calendar block only
lists what is still ahead of her, so without the tool she has to invent a past.

Everything here is dated from the real clock rather than a fixed date, because
recall_past_plans splits past from future on clock.now() while the rest of the
prompt is built from the moment passed in; in production those are the same
moment, and dating the fixtures relatively keeps them the same here too.

Run on demand: uv run pytest tests/integration/
Requires OPENROUTER_API_KEY in the environment.
"""

import os
from datetime import date, datetime, time, timedelta
from unittest.mock import MagicMock

import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart

from livingbot import clock
from livingbot.activity_notes import ActivityNotesStore
from livingbot.calendar import Calendar, CalendarStore, PlanEntry
from livingbot.commitments import CommitmentStore
from livingbot.hobbies import HobbyStore
from livingbot.inventory import InventoryStore
from livingbot.llm import LLMClient
from livingbot.preferences import PreferenceStore
from livingbot.spending import SpendingStore
from livingbot.stories import StoryStore

pytestmark = pytest.mark.skipif(
    not os.environ.get("OPENROUTER_API_KEY"),
    reason="OPENROUTER_API_KEY not set",
)

NOW = clock.now()
TWO_DAYS_AGO = (NOW - timedelta(days=2)).date()
YESTERDAY = (NOW - timedelta(days=1)).date()
TOMORROW = (NOW + timedelta(days=1)).date()
CHANNEL_ID = 1234


def _at(day: date, hour: int, minute: int = 0) -> datetime:
    return datetime.combine(day, time(hour, minute))


def _message(message_id: int, author: str, text: str) -> str:
    return f"[id:{message_id}] [{NOW:%Y-%m-%d %H:%M:%S}] {author}: {text}"


def _tool_was_called(result, tool_name: str) -> bool:
    for message in result.all_messages():
        if isinstance(message, ModelResponse):
            for part in message.parts:
                if isinstance(part, ToolCallPart) and part.tool_name == tool_name:
                    return True
    return False


@pytest.fixture
def client() -> LLMClient:
    return LLMClient.create()


@pytest.fixture
def calendar_store(tmp_path) -> CalendarStore:
    """A distinctive finished entry, so a remembered answer can be told apart from an
    invented one, an ordinary one, and one still ahead of her."""
    store = CalendarStore(tmp_path, home_location="home")
    store.save(
        Calendar(
            home_location="home",
            entries=[
                PlanEntry(
                    activity="wspinaczka na ściance",
                    location="ścianka wspinaczkowa",
                    start=_at(TWO_DAYS_AGO, 18),
                    end=_at(TWO_DAYS_AGO, 20),
                ),
                PlanEntry(
                    activity="trening na siłowni",
                    location="gym",
                    start=_at(YESTERDAY, 18),
                    end=_at(YESTERDAY, 19, 30),
                ),
                PlanEntry(
                    activity="kino z Olą",
                    location="kino",
                    start=_at(TOMORROW, 20),
                    end=_at(TOMORROW, 22),
                ),
            ],
        )
    )
    return store


@pytest.fixture
def inventory_store(tmp_path) -> InventoryStore:
    return InventoryStore.create(tmp_path / "inventory")


async def test_recall_past_plans_called_when_asked_what_she_has_been_doing(
    client: LLMClient,
    calendar_store: CalendarStore,
    activity_notes_store: ActivityNotesStore,
    inventory_store: InventoryStore,
    spending_store: SpendingStore,
    hobby_store: HobbyStore,
    story_store: StoryStore,
    preference_store: PreferenceStore,
    commitment_store: CommitmentStore,
) -> None:
    """Asked how her week went, she should look her finished plans up rather than
    answer from a calendar that only shows what is still ahead."""
    channel = MagicMock()
    user_messages = [
        _message(
            2000,
            "Kasia",
            "Mugda, co u ciebie, jak minął ci ten tydzień? robiłaś coś ciekawego?",
        )
    ]

    result = await client.complete(
        user_messages,
        channel,
        CHANNEL_ID,
        calendar_store,
        activity_notes_store,
        inventory_store,
        spending_store,
        hobby_store,
        story_store,
        preference_store,
        commitment_store,
        NOW,
    )

    assert _tool_was_called(result, "recall_past_plans"), (
        f"Expected recall_past_plans to be called. LLM response: {result.output}"
    )


async def test_recall_past_plans_answer_names_what_she_actually_did(
    client: LLMClient,
    calendar_store: CalendarStore,
    activity_notes_store: ActivityNotesStore,
    inventory_store: InventoryStore,
    spending_store: SpendingStore,
    hobby_store: HobbyStore,
    story_store: StoryStore,
    preference_store: PreferenceStore,
    commitment_store: CommitmentStore,
) -> None:
    """The recalled entry has to reach her reply — a tool call she then ignores in
    favour of an invented evening is no better than not having the tool."""
    channel = MagicMock()
    user_messages = [
        _message(
            2100,
            "Piotrek",
            "Mugda, powiedz szczerze, co robiłaś przedwczoraj wieczorem?",
        )
    ]

    result = await client.complete(
        user_messages,
        channel,
        CHANNEL_ID,
        calendar_store,
        activity_notes_store,
        inventory_store,
        spending_store,
        hobby_store,
        story_store,
        preference_store,
        commitment_store,
        NOW,
    )

    output = result.output.lower()
    assert "wspinacz" in output or "ściank" in output, (
        f"Expected her to name the climbing session from two evenings ago. "
        f"LLM response: {result.output}"
    )


async def test_recall_past_plans_called_when_asked_about_one_past_activity(
    client: LLMClient,
    calendar_store: CalendarStore,
    activity_notes_store: ActivityNotesStore,
    inventory_store: InventoryStore,
    spending_store: SpendingStore,
    hobby_store: HobbyStore,
    story_store: StoryStore,
    preference_store: PreferenceStore,
    commitment_store: CommitmentStore,
) -> None:
    """Asked whether one particular thing happened, she should check instead of
    guessing — the case the query argument exists for."""
    channel = MagicMock()
    user_messages = [
        _message(
            2200, "Bartek", "Mugda, byłaś ostatnio na siłowni czy znowu odpuściłaś?"
        )
    ]

    result = await client.complete(
        user_messages,
        channel,
        CHANNEL_ID,
        calendar_store,
        activity_notes_store,
        inventory_store,
        spending_store,
        hobby_store,
        story_store,
        preference_store,
        commitment_store,
        NOW,
    )

    assert _tool_was_called(result, "recall_past_plans"), (
        f"Expected recall_past_plans to be called before answering. "
        f"LLM response: {result.output}"
    )
