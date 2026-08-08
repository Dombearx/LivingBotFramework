from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic_ai import Agent, BinaryContent, UnexpectedModelBehavior
from pydantic_ai.models.openai import OpenAIChatModel

from livingbot import config
from livingbot.activity_notes import ActivityNotes
from livingbot.calendar import Calendar, PlanEntry
from livingbot.commitments import Commitment
from livingbot.directory import Directory
from livingbot.hobbies import Hobby, Hobbies
from livingbot.inventory import InventoryItem
from livingbot.preferences import Preferences
from livingbot.llm import (
    LLMClient,
    _build_calendar_block,
    _build_commitments_block,
    _build_history_block,
    _build_images_block,
    _build_inventory_block,
    _build_new_messages_block,
    _build_recent_block,
    _build_relations_block,
    _build_server_emojis_block,
    _build_shared_ending_block,
    _build_stories_block,
    own_messages,
)
from livingbot.relations import _ATTITUDE_BEHAVIOURS, Relation, attitude_behaviour
from livingbot.tools import MessageImage
from livingbot.stories import Story

NOW = datetime(2026, 6, 3, 14, 30)
DIRECTORY = Directory({"42": "Kuba", "111": "Ola", "222": "Wiktor"})


def test_build_calendar_block_when_busy_reports_location_and_end_time() -> None:
    ongoing = PlanEntry(
        activity="gym session",
        location="gym",
        start=datetime(2026, 6, 3, 14, 0),
        end=datetime(2026, 6, 3, 16, 0),
    )
    calendar = Calendar(home_location="home", entries=[ongoing])

    block = _build_calendar_block(calendar, NOW)

    assert "gym" in block
    assert "until 16:00" in block


def test_build_calendar_block_when_free_reports_home_location() -> None:
    calendar = Calendar(home_location="home", entries=[])

    block = _build_calendar_block(calendar, NOW)

    assert "home" in block
    assert "nothing scheduled" in block


def test_build_calendar_block_lists_upcoming_entry_with_id() -> None:
    upcoming = PlanEntry(
        activity="trip",
        location="Zakopane",
        start=datetime(2026, 6, 5, 8, 0),
        end=datetime(2026, 6, 8, 20, 0),
    )
    calendar = Calendar(home_location="home", entries=[upcoming])

    block = _build_calendar_block(calendar, NOW)

    assert f"[id:{upcoming.id}]" in block
    assert "Zakopane" in block


def test_build_inventory_block_lists_owned_item_with_id_and_description() -> None:
    item = InventoryItem(name="biała spódniczka", description="w czerwone kropki")

    block = _build_inventory_block([item])

    assert f"[id:{item.id}]" in block
    assert "biała spódniczka" in block
    assert "w czerwone kropki" in block


def test_build_inventory_block_when_empty_notes_nothing_special() -> None:
    block = _build_inventory_block([])

    assert "nothing special yet" in block


def test_build_inventory_block_directs_to_search_for_items_not_shown() -> None:
    item = InventoryItem(name="biała spódniczka")

    block = _build_inventory_block([item])

    assert "search_inventory" in block


def test_build_stories_block_marks_story_that_has_a_photo() -> None:
    story = Story(summary="Met a dog", content="c", image_path="data/x.jpg")

    block = _build_stories_block([story])

    assert "(has a photo)" in block


def test_build_stories_block_omits_photo_marker_when_no_image() -> None:
    story = Story(summary="Met a dog", content="c", image_path=None)

    block = _build_stories_block([story])

    assert "(has a photo)" not in block


def test_build_stories_block_mentions_show_story_image_tool() -> None:
    story = Story(summary="Met a dog", content="c", image_path="data/x.jpg")

    block = _build_stories_block([story])

    assert "show_story_image" in block


def test_build_recent_block_when_nothing_recent_returns_empty_string() -> None:
    hobbies = Hobbies(entries=[Hobby(name="gym")])

    block = _build_recent_block(hobbies, [], NOW)

    assert block == ""


def test_build_recent_block_includes_recently_acquired_hobby() -> None:
    hobby = Hobby(name="pottery", acquired_at=NOW - timedelta(days=2))
    hobbies = Hobbies(entries=[hobby])

    block = _build_recent_block(hobbies, [], NOW)

    assert "You took up pottery 2 days ago." in block


def test_build_recent_block_excludes_hobby_acquired_outside_window() -> None:
    hobby = Hobby(
        name="pottery",
        acquired_at=NOW - config.RECENT_HOBBY_WINDOW - timedelta(days=1),
    )
    hobbies = Hobbies(entries=[hobby])

    block = _build_recent_block(hobbies, [], NOW)

    assert block == ""


def test_build_recent_block_excludes_hobby_with_no_acquired_at() -> None:
    hobbies = Hobbies(entries=[Hobby(name="gym", acquired_at=None)])

    block = _build_recent_block(hobbies, [], NOW)

    assert block == ""


def test_build_recent_block_includes_recently_acquired_item() -> None:
    item = InventoryItem(name="sukienka", acquired_at=NOW - timedelta(days=1))

    block = _build_recent_block(Hobbies(), [item], NOW)

    assert "You got sukienka 1 day ago." in block


def test_build_recent_block_sorts_entries_newest_first() -> None:
    hobby = Hobby(name="pottery", acquired_at=NOW - timedelta(days=5))
    item = InventoryItem(name="sukienka", acquired_at=NOW - timedelta(days=1))
    hobbies = Hobbies(entries=[hobby])

    block = _build_recent_block(hobbies, [item], NOW)

    lines = block.strip().splitlines()
    assert "sukienka" in lines[1]
    assert "pottery" in lines[2]


def test_build_commitments_block_lists_promise_with_id_and_recipient() -> None:
    commitment = Commitment(
        user_id="42",
        channel_id=1,
        description="show a screenshot",
        due_hint="next time at her computer",
        made_at=NOW - timedelta(hours=3),
    )

    block = _build_commitments_block([commitment], NOW, DIRECTORY)

    assert f"[id:{commitment.id}]" in block
    assert "Kuba" in block
    assert "show a screenshot" in block
    assert "next time at her computer" in block


def test_build_commitments_block_notes_a_promise_already_brought_up() -> None:
    commitment = Commitment(
        user_id="42",
        channel_id=1,
        description="show a screenshot",
        due_hint="soon",
        made_at=NOW - timedelta(days=1),
        nudged_at=NOW - timedelta(hours=2),
    )

    block = _build_commitments_block([commitment], NOW, DIRECTORY)

    assert "you already brought this up 2 hours ago" in block


def test_build_commitments_block_omits_the_note_for_a_promise_never_raised() -> None:
    commitment = Commitment(
        user_id="42",
        channel_id=1,
        description="show a screenshot",
        due_hint="soon",
        made_at=NOW - timedelta(days=1),
    )

    block = _build_commitments_block([commitment], NOW, DIRECTORY)

    assert "already brought this up" not in block


def test_build_commitments_block_mentions_resolve_commitment_tool() -> None:
    commitment = Commitment(
        user_id="42",
        channel_id=1,
        description="show a screenshot",
        due_hint="soon",
        made_at=NOW,
    )

    block = _build_commitments_block([commitment], NOW, DIRECTORY)

    assert "resolve_commitment" in block


def test_build_history_block_labels_it_as_earlier_conversation() -> None:
    block = _build_history_block(["[id:1] alice: hey", "[id:2] bob: yo"])

    assert block.startswith("Earlier in the conversation:\n")
    assert "[id:1] alice: hey" in block
    assert "[id:2] bob: yo" in block


def test_build_history_block_tells_her_not_to_copy_her_own_earlier_messages() -> None:
    block = _build_history_block(["[id:1] Mugda (you): hey 😭"])

    assert "not as a style to copy" in block


def make_llm_client() -> LLMClient:
    return LLMClient(MagicMock(spec=OpenAIChatModel), "instructions")


def make_complete_kwargs() -> dict:
    """Every store complete() reads on its way to building the prompt, stubbed with
    the emptiest thing each block builder accepts."""
    calendar_store = MagicMock()
    calendar_store.load.return_value = Calendar(home_location="dom")
    activity_notes_store = MagicMock()
    activity_notes_store.load.return_value = ActivityNotes()
    inventory_store = MagicMock()
    inventory_store.recently_acquired = AsyncMock(return_value=[])
    inventory_store.recent = AsyncMock(return_value=[])
    spending_store = MagicMock()
    spending_store.summary.return_value = "budget"
    hobby_store = MagicMock()
    hobby_store.load.return_value = Hobbies()
    story_store = MagicMock()
    story_store.untold = AsyncMock(return_value=[])
    preference_store = MagicMock()
    preference_store.load.return_value = Preferences()
    return dict(
        user_messages=["[id:30] Ola: co tam?"],
        channel=MagicMock(),
        channel_id=1,
        calendar_store=calendar_store,
        activity_notes_store=activity_notes_store,
        inventory_store=inventory_store,
        spending_store=spending_store,
        hobby_store=hobby_store,
        story_store=story_store,
        preference_store=preference_store,
        commitment_store=MagicMock(),
        now=NOW,
    )


@patch.object(Agent, "run", new_callable=AsyncMock)
async def test_complete_sends_every_image_after_the_prompt_text(
    mock_run: AsyncMock,
) -> None:
    images = [make_message_image(10), make_message_image(20)]

    await make_llm_client().complete(**make_complete_kwargs(), images=images)

    prompt = mock_run.await_args.args[0]
    assert prompt[1:] == [image.content for image in images]


@patch.object(Agent, "run", new_callable=AsyncMock)
async def test_complete_tells_her_which_message_each_image_came_from(
    mock_run: AsyncMock,
) -> None:
    await make_llm_client().complete(
        **make_complete_kwargs(), images=[make_message_image(10)]
    )

    prompt_text = mock_run.await_args.args[0][0]
    assert "- image 1: attached to message [id:10]" in prompt_text


@patch.object(Agent, "run", new_callable=AsyncMock)
async def test_complete_without_images_sends_the_prompt_text_alone(
    mock_run: AsyncMock,
) -> None:
    await make_llm_client().complete(**make_complete_kwargs())

    prompt = mock_run.await_args.args[0]
    assert len(prompt) == 1


def make_message_image(message_id: int) -> MessageImage:
    return MessageImage(
        message_id=message_id,
        content=BinaryContent(data=b"bytes", media_type="image/png"),
    )


def test_build_images_block_numbers_the_images_in_the_order_they_are_attached() -> None:
    """The images arrive after the text with nothing tying them to a sender, so the
    only thing she can match them by is their position and the message id."""
    block = _build_images_block([make_message_image(10), make_message_image(20)])

    assert "- image 1: attached to message [id:10]" in block
    assert "- image 2: attached to message [id:20]" in block


def test_build_images_block_states_how_many_images_follow() -> None:
    block = _build_images_block([make_message_image(10), make_message_image(20)])

    assert "The 2 images at the end of this message" in block


def test_build_images_block_tells_her_to_describe_what_is_actually_there() -> None:
    block = _build_images_block([make_message_image(10)])

    assert "go by what you can actually see in it" in block


def test_build_new_messages_block_labels_messages_to_respond_to() -> None:
    block = _build_new_messages_block(["[id:3] alice: are you there?"])

    assert block == "New message(s) to respond to:\n[id:3] alice: are you there?"


def test_build_server_emojis_block_lists_every_emoji_token() -> None:
    block = _build_server_emojis_block(["<:mugda_lift:111>", "<a:kekw:222>"])

    assert "<:mugda_lift:111>" in block
    assert "<a:kekw:222>" in block


def test_build_server_emojis_block_asks_for_the_token_written_verbatim() -> None:
    block = _build_server_emojis_block(["<:mugda_lift:111>"])

    assert "exactly as shown" in block


def test_build_relations_block_describes_how_she_feels_about_each_user() -> None:
    relations = [
        Relation(user_id="111", attitude=4),
        Relation(user_id="222", attitude=65),
    ]

    result = _build_relations_block(relations, DIRECTORY)

    assert attitude_behaviour(4) in result
    assert attitude_behaviour(65) in result


def test_build_relations_block_omits_the_bands_a_user_does_not_fall_into() -> None:
    relations = [Relation(user_id="111", attitude=4)]

    result = _build_relations_block(relations, DIRECTORY)

    unmatched = [
        description
        for _, description in _ATTITUDE_BEHAVIOURS
        if description != attitude_behaviour(4)
    ]
    assert not [description for description in unmatched if description in result]


def test_build_shared_ending_block_names_the_ending_she_must_not_repeat() -> None:
    block = _build_shared_ending_block("a joke after you have already made your point")

    assert "a joke after you have already made your point" in block


def test_own_messages_returns_only_her_lines_in_order() -> None:
    lines = own_messages(
        [
            "[id:1] [2026-06-03 14:00:00] Kuba: hey",
            "[id:2] [2026-06-03 14:01:00] Mugda (you): siema",
            "[id:3] [2026-06-03 14:02:00] Ola: co tam",
            "[id:4] [2026-06-03 14:03:00] Mugda (you): nic, leżę",
        ]
    )

    assert lines == [
        "[id:2] [2026-06-03 14:01:00] Mugda (you): siema",
        "[id:4] [2026-06-03 14:03:00] Mugda (you): nic, leżę",
    ]


def test_own_messages_keeps_only_the_most_recent_ones() -> None:
    history = [
        f"[id:{i}] [2026-06-03 14:0{i}:00] Mugda (you): wiadomość {i}"
        for i in range(config.RECENT_OWN_MESSAGE_LIMIT + 2)
    ]

    lines = own_messages(history)

    assert len(lines) == config.RECENT_OWN_MESSAGE_LIMIT
    assert "wiadomość 0" not in lines[0]


def test_own_messages_does_not_mistake_a_quoted_marker_for_her_own_line() -> None:
    lines = own_messages(["[id:1] [2026-06-03 14:00:00] Kuba: haha (you): nope"])

    assert lines == []


@patch.object(Agent, "run", new_callable=AsyncMock)
async def test_complete_when_ignoring_is_allowed_offers_her_the_option(
    mock_run: AsyncMock,
) -> None:
    await make_llm_client().complete(**make_complete_kwargs(), can_ignore=True)

    prompt_text = mock_run.await_args.args[0][0]
    assert "ignore_message" in prompt_text


@patch.object(Agent, "run", new_callable=AsyncMock)
async def test_complete_when_ignoring_is_not_allowed_never_mentions_it(
    mock_run: AsyncMock,
) -> None:
    await make_llm_client().complete(**make_complete_kwargs())

    prompt_text = mock_run.await_args.args[0][0]
    assert "ignore_message" not in prompt_text


@patch.object(Agent, "run", new_callable=AsyncMock)
async def test_complete_passes_the_ignore_permission_to_the_tools(
    mock_run: AsyncMock,
) -> None:
    await make_llm_client().complete(**make_complete_kwargs(), can_ignore=True)

    assert mock_run.await_args.kwargs["deps"].can_ignore is True


def _answer_wordlessly(ignored: bool = False, reaction: str | None = None):
    """Stand in for a run where she picked a wordless answer and then ended her turn
    with no text — which is what pydantic-ai retries into UnexpectedModelBehavior."""

    async def run(prompt, deps=None, **kwargs):
        deps.ignored = ignored
        deps.reaction = reaction
        raise UnexpectedModelBehavior("Exceeded maximum output retries (1)")

    return run


@patch.object(Agent, "run", new_callable=AsyncMock)
async def test_complete_when_she_ignores_them_survives_her_empty_turn(
    mock_run: AsyncMock,
) -> None:
    mock_run.side_effect = _answer_wordlessly(ignored=True)

    result = await make_llm_client().complete(**make_complete_kwargs(), can_ignore=True)

    assert result.ignored is True


@patch.object(Agent, "run", new_callable=AsyncMock)
async def test_complete_when_she_ignores_them_returns_no_text_to_send(
    mock_run: AsyncMock,
) -> None:
    mock_run.side_effect = _answer_wordlessly(ignored=True)

    result = await make_llm_client().complete(**make_complete_kwargs(), can_ignore=True)

    assert result.output == ""


@patch.object(Agent, "run", new_callable=AsyncMock)
async def test_complete_when_she_only_reacts_survives_her_empty_turn(
    mock_run: AsyncMock,
) -> None:
    mock_run.side_effect = _answer_wordlessly(reaction="🔥")

    result = await make_llm_client().complete(**make_complete_kwargs())

    assert result.reaction == "🔥"


@patch.object(Agent, "run", new_callable=AsyncMock)
async def test_complete_when_she_said_nothing_wordless_lets_the_error_through(
    mock_run: AsyncMock,
) -> None:
    mock_run.side_effect = _answer_wordlessly()

    with pytest.raises(UnexpectedModelBehavior):
        await make_llm_client().complete(**make_complete_kwargs())
