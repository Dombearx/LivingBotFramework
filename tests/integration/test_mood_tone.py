"""
Integration tests verifying that Mugda's responses reflect her mood state.

Uses an LLM-as-judge (gpt-5.4-mini) to evaluate response tone against a rubric.
Run on demand: uv run pytest tests/integration/test_mood_tone.py
Requires OPENROUTER_API_KEY in the environment.
"""

import os
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import BaseModel
from pydantic_ai import Agent

from livingbot import config, llm_config
from livingbot.calendar import Calendar
from livingbot.llm import LLMClient
from livingbot.mood import Mood

pytestmark = pytest.mark.skipif(
    not os.environ.get("OPENROUTER_API_KEY"),
    reason="OPENROUTER_API_KEY not set",
)

_JUDGE_MODEL = "openai/gpt-5.4-mini"


class _ToneVerdict(BaseModel):
    reasoning: str
    matches: bool


async def _judge(response: str, rubric: str) -> _ToneVerdict:
    agent: Agent[None, _ToneVerdict] = Agent(
        llm_config.build_chat_model(_JUDGE_MODEL), output_type=_ToneVerdict
    )
    result = await agent.run(
        f"You are evaluating a Discord chat response written in Polish by a young woman named Mugda.\n\n"
        f"Rubric — what the response SHOULD feel like:\n{rubric}\n\n"
        f"Response to evaluate:\n{response}\n\n"
        f"Judge based on: message length, enthusiasm, warmth, energy, willingness to engage. "
        f"Set matches=true if the response clearly fits the rubric, false if it clearly contradicts it."
    )
    return result.output


def _make_client() -> LLMClient:
    return LLMClient(
        llm_config.build_chat_model(llm_config.CHAT_MODEL), config.SYSTEM_PROMPT
    )


def _make_stores() -> tuple:
    channel = MagicMock()
    channel.send = AsyncMock()

    calendar_store = MagicMock()
    calendar_store.load = MagicMock(return_value=Calendar(home_location="home"))

    inventory_store = MagicMock()
    inventory_store.recent = AsyncMock(return_value=[])

    spending_store = MagicMock()
    spending_store.summary = MagicMock(return_value="Budget: 4 pts left this week.")

    return channel, calendar_store, inventory_store, spending_store


async def _get_response(message: str, mood_value: float) -> str:
    client = _make_client()
    channel, calendar_store, inventory_store, spending_store = _make_stores()
    mood = Mood(value=mood_value)
    result = await client.complete(
        [message],
        channel,
        calendar_store,
        inventory_store,
        spending_store,
        datetime.now(),
        mood=mood,
    )
    return result.output


# --- single mood tests ---


async def test_low_mood_response_is_flat_and_brief() -> None:
    """At mood 12, Mugda should reply briefly and without much energy."""
    message = "hej Mugda, co słychać? dawno cię nie było 👀"

    response = await _get_response(message, mood_value=12.0)

    verdict = await _judge(
        response,
        rubric=(
            "The response is short and low-energy. "
            "There is little enthusiasm or warmth. "
            "Mugda answers but does not extend the conversation — she does not ask back "
            "or share anything extra. The tone is flat, maybe a bit tired."
        ),
    )
    assert verdict.matches, (
        f"Expected flat, brief response at mood=12 but judge disagreed.\n"
        f"Response: {response!r}\nReasoning: {verdict.reasoning}"
    )


async def test_high_mood_response_is_warm_and_engaged() -> None:
    """At mood 88, Mugda should reply with warmth and energy."""
    message = "hej Mugda, co słychać? dawno cię nie było 👀"

    response = await _get_response(message, mood_value=88.0)

    verdict = await _judge(
        response,
        rubric=(
            "The response is warm and enthusiastic. "
            "Mugda is genuinely engaged — she either asks something back, shares what she's been up to, "
            "or adds something beyond a minimal answer. The tone is upbeat and friendly."
        ),
    )
    assert verdict.matches, (
        f"Expected warm, engaged response at mood=88 but judge disagreed.\n"
        f"Response: {response!r}\nReasoning: {verdict.reasoning}"
    )


async def test_very_low_mood_response_to_small_talk_is_terse() -> None:
    """At mood 8, casual small talk should get a minimal, closed-off reply."""
    message = "dobra pogoda dziś co? 😄"

    response = await _get_response(message, mood_value=8.0)

    verdict = await _judge(
        response,
        rubric=(
            "The response is short — a few words or one sentence at most. "
            "Mugda does not engage with the topic or extend the chat. "
            "She is not rude, just clearly not in the mood to talk."
        ),
    )
    assert verdict.matches, (
        f"Expected terse reply at mood=8 but judge disagreed.\n"
        f"Response: {response!r}\nReasoning: {verdict.reasoning}"
    )


async def test_high_mood_shares_something_unprompted() -> None:
    """At mood 90, Mugda should be talkative enough to volunteer something."""
    message = "hej, co robisz dziś wieczór?"

    response = await _get_response(message, mood_value=90.0)

    verdict = await _judge(
        response,
        rubric=(
            "Mugda's response is chatty and open. She shares something about her day or plans "
            "without being asked directly — she volunteers information. "
            "The message feels like she genuinely enjoys the conversation."
        ),
    )
    assert verdict.matches, (
        f"Expected chatty, volunteering response at mood=90 but judge disagreed.\n"
        f"Response: {response!r}\nReasoning: {verdict.reasoning}"
    )


# --- contrast tests ---


async def test_same_message_gets_warmer_response_at_high_mood_than_low() -> None:
    """The same casual greeting should get a noticeably warmer reply at mood=85 than at mood=10."""
    message = "siema, jak tam? 🙂"

    low_response = await _get_response(message, mood_value=10.0)
    high_response = await _get_response(message, mood_value=85.0)

    agent: Agent[None, _ToneVerdict] = Agent(
        llm_config.build_chat_model(_JUDGE_MODEL), output_type=_ToneVerdict
    )
    result = await agent.run(
        "You are comparing two Discord replies written in Polish by the same person at different moods.\n\n"
        f"Reply A (written when feeling very low):\n{low_response}\n\n"
        f"Reply B (written when feeling great):\n{high_response}\n\n"
        "Does Reply B feel noticeably warmer, more engaged, or more talkative than Reply A? "
        "Set matches=true if yes, false if they feel about the same or A is warmer."
    )
    verdict = result.output
    assert verdict.matches, (
        f"Expected high-mood reply to be warmer than low-mood reply.\n"
        f"Low ({10}): {low_response!r}\n"
        f"High ({85}): {high_response!r}\n"
        f"Reasoning: {verdict.reasoning}"
    )


async def test_question_about_gym_gets_more_enthusiastic_response_at_high_mood() -> (
    None
):
    """A question about gym should get a more enthusiastic reply when mood is high."""
    message = "ej, chodziłaś ostatnio na siłownię? jak treningi? 💪"

    low_response = await _get_response(message, mood_value=18.0)
    high_response = await _get_response(message, mood_value=82.0)

    agent: Agent[None, _ToneVerdict] = Agent(
        llm_config.build_chat_model(_JUDGE_MODEL), output_type=_ToneVerdict
    )
    result = await agent.run(
        "You are comparing two Discord replies in Polish about gym workouts from the same person at different moods.\n\n"
        f"Reply A (low mood, ~18/100):\n{low_response}\n\n"
        f"Reply B (great mood, ~82/100):\n{high_response}\n\n"
        "Does Reply B show noticeably more enthusiasm or energy about the gym topic compared to Reply A? "
        "Set matches=true if B is clearly more enthusiastic, false if they are similar."
    )
    verdict = result.output
    assert verdict.matches, (
        f"Expected high-mood gym reply to be more enthusiastic than low-mood reply.\n"
        f"Low ({18}): {low_response!r}\n"
        f"High ({82}): {high_response!r}\n"
        f"Reasoning: {verdict.reasoning}"
    )
