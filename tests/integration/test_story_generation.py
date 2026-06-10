"""
Integration tests that send real requests to the LLM and verify StoryGenerator
produces a usable life story for Mugda's week. The content of each story is graded
by a second model acting as a judge.

Run on demand: uv run pytest tests/integration/test_story_generation.py
Requires OPENROUTER_API_KEY in the environment.
"""

import os
from datetime import date, datetime
from unittest.mock import patch

import pytest
from pydantic import BaseModel
from pydantic_ai import Agent

from livingbot import llm_config
from livingbot.stories import STORY_TIERS, StoryGenerator

pytestmark = pytest.mark.skipif(
    not os.environ.get("OPENROUTER_API_KEY"),
    reason="OPENROUTER_API_KEY not set",
)

WEEK_START = date(2026, 6, 1)
OCCURS_AT = datetime(2026, 6, 4, 15, 0)
_JUDGE_MODEL = "openai/gpt-5.4-mini"
_TIERS = {tier.name: tier for tier in STORY_TIERS}


class _StoryVerdict(BaseModel):
    reasoning: str
    matches: bool


async def _judge(story_text: str, rubric: str) -> _StoryVerdict:
    agent: Agent[None, _StoryVerdict] = Agent(
        llm_config.build_chat_model(_JUDGE_MODEL), output_type=_StoryVerdict
    )
    result = await agent.run(
        "You are evaluating a short personal anecdote, written as if it happened to "
        "Mugda — a young woman from Poland whose main passion is the gym. The text may "
        "be in Polish or English.\n\n"
        f"Criterion:\n{rubric}\n\n"
        f"Story to evaluate:\n{story_text}\n\n"
        "Set matches=true if the story clearly satisfies the criterion, false if it "
        "clearly violates it."
    )
    return result.output


@pytest.fixture
def generator() -> StoryGenerator:
    return StoryGenerator(llm_config.build_chat_model(llm_config.STORY_GENERATOR_MODEL))


async def test_generated_story_reads_like_a_personal_anecdote(
    generator: StoryGenerator,
) -> None:
    """The story should read like something that happened to one real person."""
    story = await generator.generate(WEEK_START, ["gym"], "home", OCCURS_AT, None, [])

    verdict = await _judge(
        story.content,
        rubric=(
            "The text reads like a short personal anecdote about something that "
            "happened to one young woman, told from her own point of view. It is a "
            "concrete little episode, not a list, an essay, or instructions."
        ),
    )
    assert verdict.matches, (
        f"Expected a personal anecdote but judge disagreed.\n"
        f"Story: {story.content!r}\nReasoning: {verdict.reasoning}"
    )


@patch("livingbot.stories._choose_tier")
async def test_normal_tier_story_is_grounded_and_believable(
    mock_choose_tier, generator: StoryGenerator
) -> None:
    """A 'normal' tier episode should stay everyday and entirely believable."""
    mock_choose_tier.return_value = _TIERS["normal"]

    story = await generator.generate(WEEK_START, ["gym"], "home", OCCURS_AT, None, [])

    verdict = await _judge(
        story.content,
        rubric=(
            "The event is ordinary and entirely believable — the kind of thing that "
            "could really happen in everyday life. Nothing impossible, magical, or "
            "wildly improbable occurs."
        ),
    )
    assert verdict.matches, (
        f"Expected a grounded, believable story but judge disagreed.\n"
        f"Story: {story.content!r}\nReasoning: {verdict.reasoning}"
    )


@patch("livingbot.stories._choose_tier")
async def test_unbelievable_tier_story_is_fantastical(
    mock_choose_tier, generator: StoryGenerator
) -> None:
    """An 'unbelievable' tier episode should be clearly far-fetched."""
    mock_choose_tier.return_value = _TIERS["unbelievable"]

    story = await generator.generate(WEEK_START, ["gym"], "home", OCCURS_AT, None, [])

    verdict = await _judge(
        story.content,
        rubric=(
            "The event is wildly far-fetched, fantastical, or impossible — the kind "
            "of tall tale that could not really have happened."
        ),
    )
    assert verdict.matches, (
        f"Expected a fantastical story but judge disagreed.\n"
        f"Story: {story.content!r}\nReasoning: {verdict.reasoning}"
    )


@patch("livingbot.stories._choose_tier")
async def test_anchored_story_takes_place_during_the_activity(
    mock_choose_tier, generator: StoryGenerator
) -> None:
    """A story tied to a planned activity should happen during that activity."""
    mock_choose_tier.return_value = _TIERS["normal"]

    story = await generator.generate(
        WEEK_START, ["gym"], "home", OCCURS_AT, "gym session at gym", []
    )

    verdict = await _judge(
        story.content,
        rubric=(
            "The episode takes place during or around a gym session — she is working "
            "out, at the gym, or in a gym-related situation when it happens."
        ),
    )
    assert verdict.matches, (
        f"Expected the story to happen during a gym session but judge disagreed.\n"
        f"Story: {story.content!r}\nReasoning: {verdict.reasoning}"
    )


@patch("livingbot.stories._choose_tier")
async def test_generated_story_differs_from_recent_episode(
    mock_choose_tier, generator: StoryGenerator
) -> None:
    """Passing a recent episode to avoid should yield a clearly different story."""
    mock_choose_tier.return_value = _TIERS["unusual"]
    avoid = ["Mugda bumped into Arnold Schwarzenegger on the train and chatted."]

    story = await generator.generate(
        WEEK_START, ["gym"], "home", OCCURS_AT, None, avoid
    )

    verdict = await _judge(
        story.content,
        rubric=(
            "This story is about a clearly different event than: 'Mugda bumped into "
            "Arnold Schwarzenegger on the train and chatted.' It does not retell that "
            "same encounter or a near-identical version of it."
        ),
    )
    assert verdict.matches, (
        f"Expected a story distinct from the avoided one but judge disagreed.\n"
        f"Story: {story.content!r}\nReasoning: {verdict.reasoning}"
    )


async def test_generated_story_carries_requested_occurs_at(
    generator: StoryGenerator,
) -> None:
    """The story should be stamped with the moment it is scheduled to happen."""
    story = await generator.generate(WEEK_START, ["gym"], "home", OCCURS_AT, None, [])

    assert story.occurs_at == OCCURS_AT
