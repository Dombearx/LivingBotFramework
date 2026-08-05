"""
Integration tests verifying that Mugda's unprompted messages sound natural.

The spontaneous post is written by the main chat agent driven with
SPONTANEOUS_TRIGGER_MESSAGE, so these exercise the same agent as the chat tests.
Uses an LLM-as-judge to evaluate the message against a rubric. Run on demand:
uv run pytest tests/integration/test_spontaneous.py
Requires OPENROUTER_API_KEY in the environment.
"""

import os
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import BaseModel
from pydantic_ai import Agent

from livingbot import llm_config, prompts
from livingbot.activity_notes import ActivityNotes
from livingbot.calendar import Calendar, PlanEntry
from livingbot.commitments import Commitments
from livingbot.hobbies import Hobbies, Hobby
from livingbot.llm import LLMClient, LLMResult
from livingbot.directory import Directory
from livingbot.mood import Mood
from livingbot.preferences import Preferences
from livingbot.relations import Relation
from livingbot.stories import Story

pytestmark = pytest.mark.skipif(
    not os.environ.get("OPENROUTER_API_KEY"),
    reason="OPENROUTER_API_KEY not set",
)

_JUDGE_MODEL = "openai/gpt-5.4-mini"

_NOW = datetime(2026, 6, 24, 19, 0)
DIRECTORY = Directory({"111222333": "Kuba"})
_CHANNEL_ID = 1234


class _Verdict(BaseModel):
    reasoning: str
    matches: bool


async def _judge(message: str, rubric: str) -> _Verdict:
    agent: Agent[None, _Verdict] = Agent(
        llm_config.build_chat_model(_JUDGE_MODEL), output_type=_Verdict
    )
    result = await agent.run(
        "You are evaluating an unprompted Discord message written in Polish by a young "
        "woman named Mugda, who dropped it into a group chat out of the blue.\n\n"
        f"Rubric — what the message SHOULD be:\n{rubric}\n\n"
        f"Message to evaluate:\n{message}\n\n"
        "Set matches=true only if the message clearly fits the rubric, false otherwise."
    )
    return result.output


async def _run_spontaneously(
    calendar: Calendar,
    mood_value: float,
    untold: list[Story],
    relations: list[Relation],
) -> tuple[LLMResult, MagicMock]:
    channel = MagicMock()
    channel.send = AsyncMock()

    calendar_store = MagicMock()
    calendar_store.load = MagicMock(return_value=calendar)

    activity_notes_store = MagicMock()
    activity_notes_store.load = MagicMock(return_value=ActivityNotes())

    inventory_store = MagicMock()
    inventory_store.recent = AsyncMock(return_value=[])
    inventory_store.recently_acquired = AsyncMock(return_value=[])

    spending_store = MagicMock()
    spending_store.summary = MagicMock(return_value="Budget: 4 pts left this week.")

    hobby_store = MagicMock()
    hobby_store.load = MagicMock(return_value=Hobbies(entries=[Hobby(name="gym")]))

    story_store = MagicMock()
    story_store.untold = AsyncMock(return_value=untold)
    story_store.search = AsyncMock(return_value=[])
    story_store.mark_told = AsyncMock(return_value=True)
    story_store.get = AsyncMock(
        side_effect=lambda story_id: next(
            (story for story in untold if story.id == story_id), None
        )
    )

    preference_store = MagicMock()
    preference_store.load = MagicMock(return_value=Preferences())

    commitment_store = MagicMock()
    commitment_store.load = MagicMock(return_value=Commitments())

    result = await LLMClient.create().complete(
        [],
        channel,
        _CHANNEL_ID,
        calendar_store,
        activity_notes_store,
        inventory_store,
        spending_store,
        hobby_store,
        story_store,
        preference_store,
        commitment_store,
        _NOW,
        relations=relations,
        mood=Mood(value=mood_value),
        trigger=prompts.SPONTANEOUS_TRIGGER_MESSAGE,
        directory=DIRECTORY,
    )
    return result, story_store


async def _post_spontaneously(
    calendar: Calendar,
    mood_value: float,
    untold: list[Story],
    relations: list[Relation],
) -> str:
    result, _ = await _run_spontaneously(calendar, mood_value, untold, relations)
    return result.output


async def test_spontaneous_message_sounds_like_a_natural_off_the_cuff_message() -> None:
    story = Story(
        summary="tripped in the shop and got dusted in spilled protein powder",
        content="She knocked a tub of protein powder off the shelf and wore most of it.",
        occurs_at=_NOW,
    )

    message = await _post_spontaneously(
        Calendar(home_location="home"), 60.0, [story], []
    )

    verdict = await _judge(
        message,
        rubric=(
            "A short, casual message that reads like a real person dropping a thought "
            "into a group chat unprompted. It does NOT greet the whole group formally, "
            "does NOT explain that it is starting a conversation, and gives no hint that "
            "it comes from a bot or AI."
        ),
    )
    assert verdict.matches, (
        f"Expected a natural off-the-cuff message but judge disagreed.\n"
        f"Message: {message!r}\nReasoning: {verdict.reasoning}"
    )


async def test_spontaneous_message_reflects_being_at_the_gym() -> None:
    calendar = Calendar(
        home_location="home",
        entries=[
            PlanEntry(
                start=_NOW.replace(hour=18),
                end=_NOW.replace(hour=20),
                activity="gym session",
                location="gym",
            )
        ],
    )

    message = await _post_spontaneously(calendar, 70.0, [], [])

    verdict = await _judge(
        message,
        rubric=(
            "The message fits the fact that she is at the gym right now — it reads like "
            "something fired off mid-workout (training, a set, the gym). It does NOT "
            "place her somewhere else like at home or out shopping, and it still sounds "
            "like a natural, casual chat message."
        ),
    )
    assert verdict.matches, (
        f"Expected a gym-grounded message but judge disagreed.\n"
        f"Message: {message!r}\nReasoning: {verdict.reasoning}"
    )


async def test_spontaneous_message_can_ask_a_user_about_their_interest() -> None:
    relation = Relation(
        user_id="111222333",
        attitude=70.0,
        topics_of_interest=["bouldering", "horror films"],
        inside_jokes=["the cursed tram ride"],
    )

    message = await _post_spontaneously(
        Calendar(home_location="home"), 75.0, [], [relation]
    )

    verdict = await _judge(
        message,
        rubric=(
            "A natural, casual message that reaches out to the listed person by pinging "
            "them as @Kuba and asks them a genuine question tied to something "
            "they care about — bouldering, horror films, or the shared 'cursed tram "
            "ride' joke. It still reads like a real off-the-cuff message."
        ),
    )
    assert verdict.matches, (
        f"Expected a message that asks the user about their interest but judge disagreed.\n"
        f"Message: {message!r}\nReasoning: {verdict.reasoning}"
    )


async def test_spontaneous_story_telling_marks_the_story_told() -> None:
    story = Story(
        summary="tripped in the shop and got dusted in spilled protein powder",
        content="She knocked a tub of protein powder off the shelf and wore most of it.",
        occurs_at=_NOW,
    )

    _, story_store = await _run_spontaneously(
        Calendar(home_location="home"), 60.0, [story], []
    )

    story_store.mark_told.assert_awaited_once_with(story.id)


async def test_spontaneous_story_telling_attaches_the_story_photo(tmp_path) -> None:
    image_path = tmp_path / "story.jpg"
    image_path.write_bytes(b"fake-jpeg-bytes")
    story = Story(
        summary="tripped in the shop and got dusted in spilled protein powder",
        content="She knocked a tub of protein powder off the shelf and wore most of it.",
        occurs_at=_NOW,
        image_path=str(image_path),
    )

    result, _ = await _run_spontaneously(
        Calendar(home_location="home"), 60.0, [story], []
    )

    assert result.photo == b"fake-jpeg-bytes"
