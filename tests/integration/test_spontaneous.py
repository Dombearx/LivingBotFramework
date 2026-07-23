"""
Integration tests verifying that Mugda's unprompted messages sound natural.

Uses an LLM-as-judge (gpt-5.4-mini) to evaluate the composed message against a
rubric. Run on demand: uv run pytest tests/integration/test_spontaneous.py
Requires OPENROUTER_API_KEY in the environment.
"""

import os
from datetime import datetime

import pytest
from pydantic import BaseModel
from pydantic_ai import Agent

from livingbot import llm_config
from livingbot.mood import Mood, build_mood_block
from livingbot.spontaneous import SpontaneousMessenger

pytestmark = pytest.mark.skipif(
    not os.environ.get("OPENROUTER_API_KEY"),
    reason="OPENROUTER_API_KEY not set",
)

_JUDGE_MODEL = "openai/gpt-5.4-mini"

_NOW = datetime(2026, 6, 24, 19, 0)


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


def _messenger() -> SpontaneousMessenger:
    return SpontaneousMessenger.create()


def _context(situation: str, mood_value: float, *extra: str) -> str:
    lines = [
        f"Right now it is {_NOW:%A, %Y-%m-%d %H:%M}.",
        situation,
        "",
        build_mood_block(Mood(value=mood_value), _NOW).rstrip(),
        "",
        "Your hobbies: gym.",
        "",
        *extra,
    ]
    return "\n".join(lines)


async def test_spontaneous_message_sounds_like_a_natural_off_the_cuff_message() -> None:
    context = _context(
        "You are at home with nothing scheduled.",
        60.0,
        "Little episodes from your life you haven't shared yet:",
        "  - tripped in the shop and got dusted in spilled protein powder",
    )

    message = await _messenger().compose(context)

    verdict = await _judge(
        message or "",
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
    context = _context(
        "You are at gym, busy with gym session.",
        70.0,
        "Nothing new has happened that you haven't already shared.",
    )

    message = await _messenger().compose(context)

    verdict = await _judge(
        message or "",
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
    context = _context(
        "You are at home with nothing scheduled.",
        75.0,
        "Nothing new has happened that you haven't already shared.",
        "",
        "People you talk to here, in case you want to ask one of them something:",
        "  - <@111222333> (attitude 70/100; into bouldering, horror films; "
        "inside jokes: the cursed tram ride)",
    )

    message = await _messenger().compose(context)

    verdict = await _judge(
        message or "",
        rubric=(
            "A natural, casual message that reaches out to the listed person by pinging "
            "them with <@111222333> and asks them a genuine question tied to something "
            "they care about — bouldering, horror films, or the shared 'cursed tram "
            "ride' joke. It still reads like a real off-the-cuff message."
        ),
    )
    assert verdict.matches, (
        f"Expected a message that asks the user about their interest but judge disagreed.\n"
        f"Message: {message!r}\nReasoning: {verdict.reasoning}"
    )
