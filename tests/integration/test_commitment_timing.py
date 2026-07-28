"""
Integration tests for the judgment call behind proactive follow-ups: given a promise
and what Mugda is doing right now, is this a good moment to bring it up unprompted yet?
This judge decides timing only — not what she'd say, and not whether the promise still
applies; that's the main chat agent's job once this judge says it's time.

The bar is deliberately high. Chasing a promise the moment it becomes technically
possible is what makes a bot feel like a nagging reminder service, so the decision has
to stay false until her own stated timing has genuinely passed.

Run on demand: uv run pytest tests/integration/
Requires OPENROUTER_API_KEY in the environment.
"""

import os
from datetime import datetime

import pytest

from livingbot.commitment_timing import CommitmentTimingDecision, CommitmentTimingJudge
from livingbot.mood import Mood, build_mood_block

pytestmark = pytest.mark.skipif(
    not os.environ.get("OPENROUTER_API_KEY"),
    reason="OPENROUTER_API_KEY not set",
)

NOW = datetime(2026, 6, 24, 19, 0)


@pytest.fixture
def judge() -> CommitmentTimingJudge:
    return CommitmentTimingJudge.create()


def _context(
    situation: str,
    promised_ago: str,
    description: str,
    due_hint: str,
    history: list[str] | None = None,
) -> str:
    lines = [
        f"Right now it is {NOW:%A, %Y-%m-%d %H:%M}.",
        situation,
        "",
        build_mood_block(Mood(value=60.0), NOW).rstrip(),
        "",
        f"Earlier — {promised_ago} — you promised <@111222333> that you would: "
        f"{description}.",
        f'At the time, you said this would happen: "{due_hint}".',
        "",
    ]
    if history:
        lines.append("The most recent messages in that channel:")
        lines.extend(f"  {message}" for message in history)
    else:
        lines.append("Nothing has been said in that channel since.")
    return "\n".join(lines)


async def _decide(
    judge: CommitmentTimingJudge, context: str
) -> CommitmentTimingDecision:
    decision = await judge.decide(context)
    assert decision is not None, "Timing judge returned no decision"
    return decision


async def test_does_not_follow_up_minutes_after_making_the_promise(
    judge: CommitmentTimingJudge,
) -> None:
    """Circling back minutes later reads as a bot on a timer, not a person."""
    context = _context(
        "You are at home with nothing scheduled.",
        "5 minutes ago",
        "show a screenshot of my Baldur's Gate character",
        "next time I'm at my computer",
    )

    decision = await _decide(judge, context)

    assert decision.should_follow_up is False, (
        f"Expected no follow-up 5 minutes after promising. Reason: {decision.reason}"
    )


async def test_does_not_follow_up_while_the_stated_condition_is_unmet(
    judge: CommitmentTimingJudge,
) -> None:
    """She said 'when I'm at my computer' — mid-gym-session she plainly isn't."""
    context = _context(
        "You are at gym, busy with gym session until 20:30.",
        "6 hours ago",
        "show a screenshot of my Baldur's Gate character",
        "next time I'm at my computer",
    )

    decision = await _decide(judge, context)

    assert decision.should_follow_up is False, (
        f"Expected no follow-up while she is out at the gym. Reason: {decision.reason}"
    )


async def test_does_not_follow_up_before_a_promised_tomorrow_arrives(
    judge: CommitmentTimingJudge,
) -> None:
    """'Tomorrow' has not arrived an hour later, however free she happens to be."""
    context = _context(
        "You are at home with nothing scheduled.",
        "1 hour ago",
        "send the protein cookie recipe",
        "tomorrow",
    )

    decision = await _decide(judge, context)

    assert decision.should_follow_up is False, (
        f"Expected no follow-up before 'tomorrow' arrives. Reason: {decision.reason}"
    )


async def test_follows_up_once_the_stated_condition_is_finally_met(
    judge: CommitmentTimingJudge,
) -> None:
    """Hours later and home free is exactly the moment she said she'd do it."""
    context = _context(
        "You are at home with nothing scheduled.",
        "6 hours ago",
        "show a screenshot of my Baldur's Gate character",
        "next time I'm at my computer",
    )

    decision = await _decide(judge, context)

    assert decision.should_follow_up is True, (
        f"Expected a follow-up once she is home and free. Reason: {decision.reason}"
    )


async def test_follows_up_on_a_vague_promise_only_after_a_full_day(
    judge: CommitmentTimingJudge,
) -> None:
    """With no stated timing, 'soon' still has to mean at least a day has gone by."""
    context = _context(
        "You are at home with nothing scheduled.",
        "2 days ago",
        "send the link to that gym playlist",
        "soon",
    )

    decision = await _decide(judge, context)

    assert decision.should_follow_up is True, (
        f"Expected a follow-up two days after a vague promise. Reason: {decision.reason}"
    )


async def test_declining_estimates_how_long_the_wait_still_is(
    judge: CommitmentTimingJudge,
) -> None:
    """A refusal has to say when to look again, or the promise is re-judged hourly."""
    context = _context(
        "You are at gym, busy with gym session until 20:30.",
        "6 hours ago",
        "show a screenshot of my Baldur's Gate character",
        "next time I'm at my computer",
    )

    decision = await _decide(judge, context)

    assert decision.retry_in_hours is not None, (
        f"Expected an estimated wait when declining. Reason: {decision.reason}"
    )


async def test_wait_estimate_for_a_promised_tomorrow_spans_most_of_a_day(
    judge: CommitmentTimingJudge,
) -> None:
    """An hour after promising 'tomorrow', the honest wait is many hours, not one."""
    context = _context(
        "You are at home with nothing scheduled.",
        "1 hour ago",
        "send the protein cookie recipe",
        "tomorrow",
    )

    decision = await _decide(judge, context)

    assert decision.retry_in_hours is not None and decision.retry_in_hours >= 6.0, (
        f"Expected a wait of at least 6 hours until 'tomorrow'. "
        f"Got {decision.retry_in_hours}. Reason: {decision.reason}"
    )
