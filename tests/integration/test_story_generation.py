"""
Integration tests that send real requests to the LLM and verify StoryGenerator
produces a usable life story for Mugda's week.

Run on demand: uv run pytest tests/integration/test_story_generation.py
Requires OPENROUTER_API_KEY in the environment.
"""

import os
from datetime import date, datetime

import pytest

from livingbot import llm_config
from livingbot.stories import StoryGenerator

pytestmark = pytest.mark.skipif(
    not os.environ.get("OPENROUTER_API_KEY"),
    reason="OPENROUTER_API_KEY not set",
)

WEEK_START = date(2026, 6, 1)
OCCURS_AT = datetime(2026, 6, 4, 15, 0)


@pytest.fixture
def generator() -> StoryGenerator:
    return StoryGenerator(llm_config.build_chat_model(llm_config.STORY_GENERATOR_MODEL))


async def test_generate_returns_a_story(generator: StoryGenerator) -> None:
    """Generation should return a story with both a summary and content."""
    story = await generator.generate(WEEK_START, ["gym"], "home", OCCURS_AT, None, [])

    assert story is not None
    assert story.summary.strip()
    assert story.content.strip()


async def test_generated_story_carries_requested_occurs_at(
    generator: StoryGenerator,
) -> None:
    """The story should be stamped with the moment it is scheduled to happen."""
    story = await generator.generate(WEEK_START, ["gym"], "home", OCCURS_AT, None, [])

    assert story.occurs_at == OCCURS_AT


async def test_generate_with_anchor_returns_a_story(
    generator: StoryGenerator,
) -> None:
    """An episode tied to a planned activity should still produce a usable story."""
    story = await generator.generate(
        WEEK_START, ["gym"], "home", OCCURS_AT, "gym session at gym", []
    )

    assert story is not None
    assert story.content.strip()
