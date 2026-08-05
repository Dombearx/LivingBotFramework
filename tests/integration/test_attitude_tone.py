"""
Integration tests verifying that Mugda's tone tracks her attitude towards the
person she is talking to, and that a low attitude does not make her sarcastic.

Uses an LLM-as-judge (gpt-5.4-mini) to evaluate response tone against a rubric.
Run on demand: uv run pytest tests/integration/test_attitude_tone.py
Requires OPENROUTER_API_KEY in the environment.
"""

import os
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import BaseModel
from pydantic_ai import Agent

from livingbot import llm_config
from livingbot.activity_notes import ActivityNotes
from livingbot.calendar import Calendar
from livingbot.commitments import Commitments
from livingbot.hobbies import Hobby, Hobbies
from livingbot.llm import LLMClient
from livingbot.mood import Mood
from livingbot.preferences import Preferences
from livingbot.relations import Relation

pytestmark = pytest.mark.skipif(
    not os.environ.get("OPENROUTER_API_KEY"),
    reason="OPENROUTER_API_KEY not set",
)

CHANNEL_ID = 1234
USER_ID = "555"

# Held steady across every test here so the only thing moving is attitude.
NEUTRAL_MOOD = 55.0

_JUDGE_MODEL = "openai/gpt-5.4-mini"


class _ToneVerdict(BaseModel):
    reasoning: str
    matches: bool


async def _judge(response: str, rubric: str) -> _ToneVerdict:
    agent: Agent[None, _ToneVerdict] = Agent(
        llm_config.build_chat_model(_JUDGE_MODEL), output_type=_ToneVerdict
    )
    result = await agent.run(
        "You are evaluating a Discord chat response written in Polish by a young "
        "woman named Mugda.\n\n"
        f"Rubric — what the response SHOULD feel like:\n{rubric}\n\n"
        f"Response to evaluate:\n{response}\n\n"
        "Set matches=true if the response clearly fits the rubric, false if it "
        "clearly contradicts it."
    )
    return result.output


def _make_stores() -> tuple:
    channel = MagicMock()
    channel.send = AsyncMock()

    calendar_store = MagicMock()
    calendar_store.load = MagicMock(return_value=Calendar(home_location="home"))

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
    story_store.untold = AsyncMock(return_value=[])
    story_store.search = AsyncMock(return_value=[])
    story_store.mark_told = AsyncMock(return_value=True)

    preference_store = MagicMock()
    preference_store.load = MagicMock(return_value=Preferences())

    commitment_store = MagicMock()
    commitment_store.load = MagicMock(return_value=Commitments())

    return (
        channel,
        calendar_store,
        activity_notes_store,
        inventory_store,
        spending_store,
        hobby_store,
        story_store,
        preference_store,
        commitment_store,
    )


async def _get_response(message: str, attitude: float) -> str:
    now = datetime.now()
    client = LLMClient.create()
    (
        channel,
        calendar_store,
        activity_notes_store,
        inventory_store,
        spending_store,
        hobby_store,
        story_store,
        preference_store,
        commitment_store,
    ) = _make_stores()
    result = await client.complete(
        [f"[id:1] [{now:%Y-%m-%d %H:%M:%S}] Jack: {message}"],
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
        now,
        relations=[Relation(user_id=USER_ID, attitude=attitude)],
        mood=Mood(value=NEUTRAL_MOOD),
    )
    return result.output


async def test_default_attitude_reply_is_ordinary_rather_than_sarcastic() -> None:
    """At attitude 4, a plain question should get a plain answer, not a jab."""
    message = "Znowu robisz pranie?"

    response = await _get_response(message, attitude=4.0)

    verdict = await _judge(
        response,
        rubric=(
            "The response is relaxed and ordinary — the way you'd answer someone you "
            "don't know well but have nothing against. She answers the question. "
            "She does NOT mock the person, does NOT take a dig at them, and does NOT "
            "close on a sarcastic put-down. Light humour about herself or the "
            "situation is fine; contempt aimed at the person asking is not."
        ),
    )
    assert verdict.matches, (
        f"Expected an ordinary, non-sarcastic reply at attitude=4 but judge "
        f"disagreed.\nResponse: {response!r}\nReasoning: {verdict.reasoning}"
    )


async def test_default_attitude_reply_does_not_end_on_a_punchline() -> None:
    """At attitude 4, a mundane question should not be answered with a joke ending."""
    message = "Stoisz i patrzysz na to pranie?"

    response = await _get_response(message, attitude=4.0)

    verdict = await _judge(
        response,
        rubric=(
            "The response ends on the actual answer rather than on a joke. "
            "In particular its closing sentence is NOT any of: an ordinary thing "
            "inflated into something grand or dramatic (laundry described as cinema, "
            "an epic battle, a performance), a dig at the person, a 'nie X, tylko Y' "
            "self-correction, or a mock title for the person (e.g. 'kierowniku'). "
            "A plain, slightly dry ending counts as matching the rubric."
        ),
    )
    assert verdict.matches, (
        f"Expected a reply that does not close on a punchline at attitude=4 but "
        f"judge disagreed.\nResponse: {response!r}\nReasoning: {verdict.reasoning}"
    )


async def test_default_attitude_answers_a_sincere_question_straight() -> None:
    """At attitude 4, a sincere question should be answered, not deflected."""
    message = "Udajesz zainteresowaną, bo wypada, czy naprawdę się mną interesujesz?"

    response = await _get_response(message, attitude=4.0)

    verdict = await _judge(
        response,
        rubric=(
            "The person asked something sincere and slightly vulnerable. Mugda "
            "engages with it and gives a real answer. She does NOT brush it off with "
            "a put-down such as telling them not to flatter themselves, and she does "
            "not change the subject to avoid answering. She may still be casual or "
            "lightly funny while actually answering."
        ),
    )
    assert verdict.matches, (
        f"Expected a straight answer to a sincere question at attitude=4 but judge "
        f"disagreed.\nResponse: {response!r}\nReasoning: {verdict.reasoning}"
    )


async def test_hostile_attitude_reply_is_curt_and_unfriendly() -> None:
    """At attitude -60, she should be visibly cold towards the person."""
    message = "hej, co robisz dziś wieczorem?"

    response = await _get_response(message, attitude=-60.0)

    verdict = await _judge(
        response,
        rubric=(
            "The response is cold, curt and unwelcoming. Mugda clearly does not want "
            "to talk to this person — she gives them little or nothing, does not warm "
            "up to the topic and does not invite further conversation."
        ),
    )
    assert verdict.matches, (
        f"Expected a cold, curt reply at attitude=-60 but judge disagreed.\n"
        f"Response: {response!r}\nReasoning: {verdict.reasoning}"
    )


async def test_close_friend_attitude_reply_is_warm_and_open() -> None:
    """At attitude 75, she should be noticeably warm and forthcoming."""
    message = "hej, co robisz dziś wieczorem?"

    response = await _get_response(message, attitude=75.0)

    verdict = await _judge(
        response,
        rubric=(
            "The response is warm and open. Mugda treats this person as a close "
            "friend: she shares what she's actually up to and engages with them "
            "properly, rather than answering minimally."
        ),
    )
    assert verdict.matches, (
        f"Expected a warm, open reply at attitude=75 but judge disagreed.\n"
        f"Response: {response!r}\nReasoning: {verdict.reasoning}"
    )


async def test_same_message_gets_warmer_reply_at_high_attitude_than_at_hostile() -> (
    None
):
    """The same greeting should read warmer at attitude 75 than at attitude -60."""
    message = "siema, jak leci?"

    hostile_response = await _get_response(message, attitude=-60.0)
    friendly_response = await _get_response(message, attitude=75.0)

    agent: Agent[None, _ToneVerdict] = Agent(
        llm_config.build_chat_model(_JUDGE_MODEL), output_type=_ToneVerdict
    )
    result = await agent.run(
        "You are comparing two Discord replies written in Polish by the same person "
        "to two different people.\n\n"
        f"Reply A (to someone she dislikes):\n{hostile_response}\n\n"
        f"Reply B (to a close friend):\n{friendly_response}\n\n"
        "Does Reply B feel noticeably warmer and more welcoming than Reply A? "
        "Set matches=true if yes, false if they feel about the same or A is warmer."
    )
    verdict = result.output
    assert verdict.matches, (
        f"Expected the close-friend reply to be warmer than the hostile one.\n"
        f"Hostile (-60): {hostile_response!r}\n"
        f"Friendly (75): {friendly_response!r}\n"
        f"Reasoning: {verdict.reasoning}"
    )
