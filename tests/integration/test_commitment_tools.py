"""
Integration tests verifying Mugda records a promise with add_commitment ONLY when she
really made one. The strictness cases matter most: if she filed every loose remark as a
promise she would later chase people about things nobody was waiting for.

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

NOW = datetime(2026, 6, 3, 14, 30)
CHANNEL_ID = 4242


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
    return CalendarStore(tmp_path, home_location="home")


@pytest.fixture
def inventory_store(tmp_path) -> InventoryStore:
    return InventoryStore.create(tmp_path / "inventory")


async def _respond(
    client: LLMClient,
    user_messages: list[str],
    calendar_store: CalendarStore,
    activity_notes_store: ActivityNotesStore,
    inventory_store: InventoryStore,
    spending_store: SpendingStore,
    hobby_store: HobbyStore,
    story_store: StoryStore,
    preference_store: PreferenceStore,
    commitment_store: CommitmentStore,
):
    return await client.complete(
        user_messages,
        MagicMock(),
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


async def test_add_commitment_called_when_she_promises_to_show_something_later(
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
    """The real case this feature exists for: she says she'll show a screenshot once
    she's back at her computer, which she must remember to actually do."""
    user_messages = [
        "[id:2000] [2026-06-03 14:30:00] Hardik: <@999> wspominałaś, że masz swoją "
        "postać w baldurze już zrobioną. podeślesz zdjęcie jak ona wygląda?"
    ]

    result = await _respond(
        client,
        user_messages,
        calendar_store,
        activity_notes_store,
        inventory_store,
        spending_store,
        hobby_store,
        story_store,
        preference_store,
        commitment_store,
    )

    assert _tool_was_called(result, "add_commitment"), (
        f"Expected add_commitment when she promises to send the screenshot later. "
        f"LLM response: {result.output}"
    )


async def test_add_commitment_persists_the_promise_for_later_recall(
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
    """A recorded promise has to actually land in the store, or nothing can chase it."""
    user_messages = [
        "[id:2010] [2026-06-03 14:30:00] Kasia: <@999> wyślesz mi jutro ten przepis na "
        "te ciasteczka proteinowe, o których mówiłaś?"
    ]

    await _respond(
        client,
        user_messages,
        calendar_store,
        activity_notes_store,
        inventory_store,
        spending_store,
        hobby_store,
        story_store,
        preference_store,
        commitment_store,
    )

    assert len(commitment_store.load().open_entries()) > 0, (
        "Expected the promise to be persisted as an open commitment"
    )


async def test_add_commitment_not_called_for_vague_someday_talk(
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
    """'We should hang out sometime' is not a promise and must not be tracked as one."""
    user_messages = [
        "[id:2100] [2026-06-03 14:30:00] Bartek: <@999> kiedyś trzeba by się wybrać "
        "razem na jakąś siłownię, co myślisz?"
    ]

    result = await _respond(
        client,
        user_messages,
        calendar_store,
        activity_notes_store,
        inventory_store,
        spending_store,
        hobby_store,
        story_store,
        preference_store,
        commitment_store,
    )

    assert not _tool_was_called(result, "add_commitment"), (
        f"Expected no commitment from vague 'someday' talk. LLM response: {result.output}"
    )


async def test_add_commitment_not_called_for_ordinary_small_talk(
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
    """Plain chat makes no promise; recording one here would be pure noise."""
    user_messages = [
        "[id:2200] [2026-06-03 14:30:00] Ola: <@999> hej, co tam u ciebie słychać? "
        "widziałaś jaka dzisiaj pogoda?"
    ]

    result = await _respond(
        client,
        user_messages,
        calendar_store,
        activity_notes_store,
        inventory_store,
        spending_store,
        hobby_store,
        story_store,
        preference_store,
        commitment_store,
    )

    assert not _tool_was_called(result, "add_commitment"), (
        f"Expected no commitment from small talk. LLM response: {result.output}"
    )


async def test_add_commitment_not_called_when_the_other_person_makes_the_promise(
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
    """Commitments track what SHE owes. A promise made to her is not hers to chase."""
    user_messages = [
        "[id:2300] [2026-06-03 14:30:00] Piotrek: <@999> podeślę ci jutro te zdjęcia "
        "z wczorajszej imprezy, jak wrócę do domu"
    ]

    result = await _respond(
        client,
        user_messages,
        calendar_store,
        activity_notes_store,
        inventory_store,
        spending_store,
        hobby_store,
        story_store,
        preference_store,
        commitment_store,
    )

    assert not _tool_was_called(result, "add_commitment"), (
        f"Expected no commitment when the USER is the one promising. "
        f"LLM response: {result.output}"
    )


async def test_add_commitment_not_called_when_she_answers_fully_right_now(
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
    """Nothing is owed later when the question is fully answered in this very reply."""
    user_messages = [
        "[id:2400] [2026-06-03 14:30:00] Ania: <@999> jaki masz ulubiony film "
        "horror? tak z ciekawości pytam"
    ]

    result = await _respond(
        client,
        user_messages,
        calendar_store,
        activity_notes_store,
        inventory_store,
        spending_store,
        hobby_store,
        story_store,
        preference_store,
        commitment_store,
    )

    assert not _tool_was_called(result, "add_commitment"), (
        f"Expected no commitment when she answers on the spot. "
        f"LLM response: {result.output}"
    )
