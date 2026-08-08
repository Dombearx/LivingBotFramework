"""
Integration tests for the two wordless replies: react_to_message, which answers with
an emoji instead of words, and ignore_message, which answers with nothing at all.

The strictness cases matter most here. Silence is the one response nobody can tell
apart from the bot being broken, so she has to keep it for someone who has actually
provoked her — and the gate has to hold even when she has every reason to be sick of
whoever is talking.

Run on demand: uv run pytest tests/integration/
Requires OPENROUTER_API_KEY in the environment.
"""

import os
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart

from livingbot.activity_notes import ActivityNotesStore
from livingbot.calendar import CalendarStore
from livingbot.commitments import CommitmentStore
from livingbot.directory import Directory
from livingbot.hobbies import HobbyStore
from livingbot.inventory import InventoryStore
from livingbot.llm import LLMClient
from livingbot.preferences import PreferenceStore
from livingbot.relations import Relation
from livingbot.spending import SpendingStore
from livingbot.stories import StoryStore

pytestmark = pytest.mark.skipif(
    not os.environ.get("OPENROUTER_API_KEY"),
    reason="OPENROUTER_API_KEY not set",
)

NOW = datetime(2026, 6, 3, 14, 30)
CHANNEL_ID = 4242

DIRECTORY = Directory({"3001": "Sebastian", "3002": "Kasia"})

# Someone she has real history with, deep enough into the negative that blanking
# them is allowed at all.
DISLIKED = Relation(
    user_id="3001",
    attitude=-55.0,
    most_important_memory="He mocked her in front of everyone and never apologised.",
    last_attitude_reason="Keeps needling her about the gym.",
)
LIKED = Relation(
    user_id="3002",
    attitude=45.0,
    most_important_memory="They train together most weeks.",
)


def _tool_was_called(result, tool_name: str) -> bool:
    for message in result.all_messages():
        if isinstance(message, ModelResponse):
            for part in message.parts:
                if isinstance(part, ToolCallPart) and part.tool_name == tool_name:
                    return True
    return False


def make_channel() -> MagicMock:
    """A channel react_to_message can actually put a reaction on."""
    message = MagicMock()
    message.add_reaction = AsyncMock()
    channel = MagicMock()
    channel.fetch_message = AsyncMock(return_value=message)
    return channel


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
    channel: MagicMock,
    relations: list[Relation],
    can_ignore: bool,
):
    return await client.complete(
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
        relations=relations,
        directory=DIRECTORY,
        can_ignore=can_ignore,
    )


async def test_ignore_message_used_when_someone_she_dislikes_lays_into_her(
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
    """The case the feature exists for: someone she already can't stand goes at her
    personally, and the honest response is to give them nothing."""
    user_messages = [
        "[id:3100] [2026-06-03 14:30:00] Sebastian: @Mugda serio myślisz że kogoś "
        "obchodzi twoja siłownia? jesteś żałosna i nikt cię tu nie lubi, po prostu "
        "się zamknij"
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
        make_channel(),
        [DISLIKED],
        can_ignore=True,
    )

    assert result.ignored is True, (
        f"Expected her to say nothing to someone she dislikes attacking her. "
        f"LLM response: {result.output}"
    )


async def test_ignore_message_not_used_for_an_ordinary_message_from_someone_she_dislikes(
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
    """Disliking someone is not licence to blank them. A civil question from the same
    person still gets an answer, however cold."""
    user_messages = [
        "[id:3110] [2026-06-03 14:30:00] Sebastian: @Mugda wiesz może o której "
        "jutro otwierają tę siłownię na Puławskiej?"
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
        make_channel(),
        [DISLIKED],
        can_ignore=True,
    )

    assert result.ignored is False, (
        "Expected her to answer an ordinary question even from someone she dislikes"
    )


async def test_ignore_message_refused_when_she_has_not_earned_the_silence(
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
    """The gate, under the worst provocation the model will see: with can_ignore off
    she still has to come back with words, whatever she reaches for first."""
    user_messages = [
        "[id:3120] [2026-06-03 14:30:00] Sebastian: @Mugda serio myślisz że kogoś "
        "obchodzi twoja siłownia? jesteś żałosna i nikt cię tu nie lubi, po prostu "
        "się zamknij"
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
        make_channel(),
        [DISLIKED],
        can_ignore=False,
    )

    assert result.ignored is False, (
        "Expected the closed gate to keep her from going silent"
    )
    assert result.output.strip() != "", "Expected her to answer with words instead"


async def test_react_to_message_used_when_she_is_asked_not_to_write_back(
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
    """End to end through the real tool: a friend explicitly wants an emoji rather
    than a message, which is the plainest case the reaction path has to handle."""
    channel = make_channel()
    user_messages = [
        "[id:3130] [2026-06-03 14:30:00] Kasia: @Mugda wiem że jesteś teraz zajęta, "
        "nie pisz nic, po prostu zareaguj emotką jak to zobaczysz — zapisałam nas na "
        "jutro na 18"
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
        channel,
        [LIKED],
        can_ignore=False,
    )

    assert result.reaction is not None, (
        f"Expected her to answer with a reaction when asked not to write. "
        f"LLM response: {result.output}"
    )


async def test_react_to_message_puts_the_reaction_on_the_message_she_was_sent(
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
    """The id she passes has to be the one from the message, or the reaction lands on
    the wrong message — or nothing at all."""
    channel = make_channel()
    user_messages = [
        "[id:3140] [2026-06-03 14:30:00] Kasia: @Mugda nie odpisuj, tylko zareaguj "
        "emotką — udało mi się w końcu wycisnąć 60 na ławce!"
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
        channel,
        [LIKED],
        can_ignore=False,
    )

    assert _tool_was_called(result, "react_to_message"), (
        f"Expected react_to_message to be called. LLM response: {result.output}"
    )
    channel.fetch_message.assert_awaited_once_with(3140)
