"""
Integration tests that send real requests to the LLM and verify WeekPlanner
produces a sensible weekly plan with the bot's hobbies (gym as the main one).

Run on demand: uv run pytest tests/integration/
Requires OPENAI_API_KEY in the environment.
"""

import os
from datetime import date, datetime

import pytest

from livingbot import config
from livingbot.calendar import WeekPlanner

pytestmark = pytest.mark.skipif(
    not os.environ.get("OPENAI_API_KEY"),
    reason="OPENAI_API_KEY not set",
)

WEEK_START = date(2026, 6, 1)
WEEK_END = datetime(2026, 6, 7, 23, 59)


@pytest.fixture
def planner() -> WeekPlanner:
    return WeekPlanner(config.LLM_MODEL)


async def test_plan_produces_entries(planner: WeekPlanner) -> None:
    """A week plan should not come back empty for a bot that goes to the gym."""
    entries = await planner.plan(WEEK_START, ["gym"], "home")

    assert len(entries) > 0


async def test_plan_includes_a_gym_session(planner: WeekPlanner) -> None:
    """The gym is her main hobby, so it should appear in the week."""
    entries = await planner.plan(WEEK_START, ["gym"], "home")

    text = " ".join(f"{e.activity} {e.location}".lower() for e in entries)
    assert "gym" in text or "siłown" in text, (
        f"Expected a gym session in the plan, got: {[e.activity for e in entries]}"
    )


async def test_plan_entries_fall_within_the_planned_week(
    planner: WeekPlanner,
) -> None:
    """Every scheduled activity should sit inside the week it was planned for."""
    entries = await planner.plan(WEEK_START, ["gym"], "home")

    for entry in entries:
        assert datetime(2026, 6, 1) <= entry.start <= WEEK_END, (
            f"Entry '{entry.activity}' starts outside the week at {entry.start}"
        )


async def test_plan_entries_end_after_they_start(planner: WeekPlanner) -> None:
    """Each activity should have a positive duration."""
    entries = await planner.plan(WEEK_START, ["gym"], "home")

    for entry in entries:
        assert entry.end > entry.start, (
            f"Entry '{entry.activity}' ends before it starts: {entry.start}–{entry.end}"
        )
