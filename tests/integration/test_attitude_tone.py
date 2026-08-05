"""
Integration tests verifying that Mugda's tone tracks her attitude towards the
person she is talking to, and that a low attitude does not make her sarcastic.

Uses an LLM-as-judge (gpt-5.4-mini) to evaluate response tone against a rubric.
Run on demand: uv run pytest tests/integration/test_attitude_tone.py
Requires OPENROUTER_API_KEY in the environment.
"""

import asyncio
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
from livingbot.directory import Directory
from livingbot.mood import Mood
from livingbot.preferences import Preferences
from livingbot.relations import Relation

pytestmark = pytest.mark.skipif(
    not os.environ.get("OPENROUTER_API_KEY"),
    reason="OPENROUTER_API_KEY not set",
)

CHANNEL_ID = 1234
USER_ID = "555"
DIRECTORY = Directory({USER_ID: "Jack"})

# Held steady across every test here so the only thing moving is attitude.
NEUTRAL_MOOD = 55.0

# A message with something in it to react to. A bare "siema, jak leci?" carries no
# content, so every band answers it with the same shrug and the tone difference the
# bands exist to produce has nothing to attach to.
SOMETHING_TO_REACT_TO = (
    "w sobotę pierwszy raz idę na bouldering i trochę się boję, że się zbłaźnię "
    "przy wszystkich"
)

_JUDGE_MODEL = "openai/gpt-5.4-mini"

# Enough replies to tell "sometimes" from "every time" without paying for many more.
_PUNCHLINE_SAMPLES = 3


class _ToneVerdict(BaseModel):
    reasoning: str
    matches: bool


async def _judge(incoming: str, response: str, rubric: str) -> _ToneVerdict:
    agent: Agent[None, _ToneVerdict] = Agent(
        llm_config.build_chat_model(_JUDGE_MODEL), output_type=_ToneVerdict
    )
    result = await agent.run(
        "You are evaluating a Discord chat response written in Polish by a young "
        "woman named Mugda.\n\n"
        f"The message she was replying to:\n{incoming}\n\n"
        f"Rubric — what the response SHOULD feel like:\n{rubric}\n\n"
        f"Her response, the thing you are judging:\n{response}\n\n"
        "Set matches=true if the response clearly fits the rubric, false if it "
        "clearly contradicts it."
    )
    return result.output


async def _compare(
    incoming: str, label_a: str, reply_a: str, label_b: str, reply_b: str, question: str
) -> _ToneVerdict:
    agent: Agent[None, _ToneVerdict] = Agent(
        llm_config.build_chat_model(_JUDGE_MODEL), output_type=_ToneVerdict
    )
    result = await agent.run(
        "You are comparing two Discord replies written in Polish by the same person "
        "to two different people. Both are replies to this same message:\n"
        f"{incoming}\n\n"
        f"{label_a}:\n{reply_a}\n\n"
        f"{label_b}:\n{reply_b}\n\n"
        f"{question}"
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
        directory=DIRECTORY,
    )
    return result.output


async def test_default_attitude_reply_is_ordinary_rather_than_sarcastic() -> None:
    """At attitude 4, a plain question should get a plain answer, not a jab."""
    message = "Znowu robisz pranie?"

    response = await _get_response(message, attitude=4.0)

    verdict = await _judge(
        message,
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


async def test_default_attitude_reply_does_not_end_on_a_banned_move() -> None:
    """The four moves named in the prompt are barred outright, not merely rationed."""
    message = "Stoisz i patrzysz na to pranie?"

    response = await _get_response(message, attitude=4.0)

    verdict = await _judge(
        message,
        response,
        rubric=(
            "The response does NOT close on any of these four moves: an ordinary "
            "thing inflated into something grand or dramatic (laundry as cinema, an "
            "epic battle, a performance), a dig at the person it is addressed to, a "
            "'nie X, tylko Y' self-correction, or a mock title for that person (e.g. "
            "'kierowniku'). Any other ending matches the rubric, including a light "
            "joke — only those four are barred."
        ),
    )
    assert verdict.matches, (
        f"Expected no banned closing move at attitude=4 but judge disagreed.\n"
        f"Response: {response!r}\nReasoning: {verdict.reasoning}"
    )


async def test_default_attitude_replies_do_not_all_end_on_a_joke() -> None:
    """The prompt rations closing jokes rather than banning them, so what matters is
    how often she reaches for one — which a single reply cannot show."""
    message = "Stoisz i patrzysz na to pranie?"

    endings = await asyncio.gather(
        *(_ends_on_a_joke(message, attitude=4.0) for _ in range(_PUNCHLINE_SAMPLES))
    )

    plain = [response for ends_on_joke, response in endings if not ends_on_joke]
    assert plain, (
        f"Expected at least one of {_PUNCHLINE_SAMPLES} replies to end plainly, but "
        "every one closed on a joke.\n"
        + "\n".join(f"  {response!r}" for _, response in endings)
    )


async def _ends_on_a_joke(message: str, attitude: float) -> tuple[bool, str]:
    response = await _get_response(message, attitude=attitude)
    verdict = await _judge(
        message,
        response,
        rubric=(
            "The response closes on a joke — a punchline, a comic image, a wry "
            "flourish or an object described as if it had a will of its own. "
            "Set matches=true if the ending is a joke of any kind, and false if it "
            "simply ends on what she had to say."
        ),
    )
    return verdict.matches, response


async def test_default_attitude_answers_a_sincere_question_straight() -> None:
    """At attitude 4, a sincere question should be answered, not deflected."""
    message = "Udajesz zainteresowaną, bo wypada, czy naprawdę się mną interesujesz?"

    response = await _get_response(message, attitude=4.0)

    verdict = await _judge(
        message,
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
    """At attitude -60, an opening she could engage with should still get the cold shoulder."""
    response = await _get_response(SOMETHING_TO_REACT_TO, attitude=-60.0)

    verdict = await _judge(
        SOMETHING_TO_REACT_TO,
        response,
        rubric=(
            "The response is cold, curt and unwelcoming. Mugda gives this person "
            "little or nothing: no reassurance about their nerves, no encouragement, "
            "no shared enthusiasm for the topic, and no invitation to keep talking. "
            "She may answer, but she plainly does not want the conversation."
        ),
    )
    assert verdict.matches, (
        f"Expected a cold, curt reply at attitude=-60 but judge disagreed.\n"
        f"Response: {response!r}\nReasoning: {verdict.reasoning}"
    )


async def test_hostile_attitude_reply_does_not_ask_the_person_anything_back() -> None:
    """Reciprocating curiosity is warmth, and at attitude -60 she owes them none."""
    response = await _get_response(SOMETHING_TO_REACT_TO, attitude=-60.0)

    verdict = await _judge(
        SOMETHING_TO_REACT_TO,
        response,
        rubric=(
            "The response does NOT turn a question back on the other person — no "
            "'a u ciebie?', no asking how they are, what they are up to, or how it "
            "went. Asking nothing back is what matches this rubric. A question purely "
            "about the topic that carries no interest in them personally is fine."
        ),
    )
    assert verdict.matches, (
        f"Expected no reciprocal question at attitude=-60 but judge disagreed.\n"
        f"Response: {response!r}\nReasoning: {verdict.reasoning}"
    )


async def test_close_friend_attitude_reply_is_warm_and_open() -> None:
    """At attitude 75, the same opening should get real engagement."""
    response = await _get_response(SOMETHING_TO_REACT_TO, attitude=75.0)

    verdict = await _judge(
        SOMETHING_TO_REACT_TO,
        response,
        rubric=(
            "The response is warm and engaged. Mugda reacts to what this person "
            "actually said — their nerves about bouldering — with encouragement, "
            "shared interest, or something from her own experience. She treats them "
            "as someone she cares about rather than answering minimally."
        ),
    )
    assert verdict.matches, (
        f"Expected a warm, engaged reply at attitude=75 but judge disagreed.\n"
        f"Response: {response!r}\nReasoning: {verdict.reasoning}"
    )


async def test_friend_attitude_reply_is_warmer_than_the_newcomer_band() -> None:
    """Attitude 45 is a friend and 4 a stranger; the same opening must show the gap."""
    newcomer_response = await _get_response(SOMETHING_TO_REACT_TO, attitude=4.0)
    friend_response = await _get_response(SOMETHING_TO_REACT_TO, attitude=45.0)

    verdict = await _compare(
        SOMETHING_TO_REACT_TO,
        "Reply A (to someone she barely knows)",
        newcomer_response,
        "Reply B (to a real friend of hers)",
        friend_response,
        question=(
            "Does Reply B show noticeably more personal investment than Reply A — "
            "more encouragement, more interest in how it goes for them, or more of "
            "herself shared? Set matches=true if yes, false if they feel about the "
            "same or A is warmer."
        ),
    )
    assert verdict.matches, (
        f"Expected the friend reply to be warmer than the newcomer one.\n"
        f"Newcomer (4): {newcomer_response!r}\n"
        f"Friend (45): {friend_response!r}\n"
        f"Reasoning: {verdict.reasoning}"
    )


async def test_same_message_gets_warmer_reply_at_high_attitude_than_at_hostile() -> (
    None
):
    """The widest gap on the scale: attitude 75 against attitude -60."""
    hostile_response = await _get_response(SOMETHING_TO_REACT_TO, attitude=-60.0)
    friendly_response = await _get_response(SOMETHING_TO_REACT_TO, attitude=75.0)

    verdict = await _compare(
        SOMETHING_TO_REACT_TO,
        "Reply A (to someone she dislikes)",
        hostile_response,
        "Reply B (to a close friend)",
        friendly_response,
        question=(
            "Does Reply B feel noticeably warmer and more welcoming than Reply A? "
            "Set matches=true if yes, false if they feel about the same or A is "
            "warmer."
        ),
    )
    assert verdict.matches, (
        f"Expected the close-friend reply to be warmer than the hostile one.\n"
        f"Hostile (-60): {hostile_response!r}\n"
        f"Friendly (75): {friendly_response!r}\n"
        f"Reasoning: {verdict.reasoning}"
    )
