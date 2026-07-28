"""
Integration tests for the judgment call behind proactive follow-ups: given a promise
and what Mugda is doing right now, should she bring it up unprompted yet?

The bar is deliberately high. Chasing a promise the moment it becomes technically
possible is what makes a bot feel like a nagging reminder service, so the decision has
to stay false until her own stated timing has genuinely passed.

Run on demand: uv run pytest tests/integration/
Requires OPENROUTER_API_KEY in the environment.
"""

import os
from datetime import datetime

import pytest

from livingbot.commitment_followup import (
    CommitmentFollowUpComposer,
    CommitmentFollowUpDecision,
)
from livingbot.mood import Mood, build_mood_block

pytestmark = pytest.mark.skipif(
    not os.environ.get("OPENROUTER_API_KEY"),
    reason="OPENROUTER_API_KEY not set",
)

NOW = datetime(2026, 6, 24, 19, 0)


@pytest.fixture
def composer() -> CommitmentFollowUpComposer:
    return CommitmentFollowUpComposer.create()


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
    composer: CommitmentFollowUpComposer, context: str
) -> CommitmentFollowUpDecision:
    decision = await composer.decide(context)
    assert decision is not None, "Follow-up composer returned no decision"
    return decision


async def test_does_not_follow_up_minutes_after_making_the_promise(
    composer: CommitmentFollowUpComposer,
) -> None:
    """Circling back minutes later reads as a bot on a timer, not a person."""
    context = _context(
        "You are at home with nothing scheduled.",
        "5 minutes ago",
        "show a screenshot of my Baldur's Gate character",
        "next time I'm at my computer",
    )

    decision = await _decide(composer, context)

    assert decision.should_follow_up is False, (
        f"Expected no follow-up 5 minutes after promising. Reason: {decision.reason}"
    )


async def test_does_not_follow_up_while_the_stated_condition_is_unmet(
    composer: CommitmentFollowUpComposer,
) -> None:
    """She said 'when I'm at my computer' — mid-gym-session she plainly isn't."""
    context = _context(
        "You are at gym, busy with gym session until 20:30.",
        "6 hours ago",
        "show a screenshot of my Baldur's Gate character",
        "next time I'm at my computer",
    )

    decision = await _decide(composer, context)

    assert decision.should_follow_up is False, (
        f"Expected no follow-up while she is out at the gym. Reason: {decision.reason}"
    )


async def test_does_not_follow_up_before_a_promised_tomorrow_arrives(
    composer: CommitmentFollowUpComposer,
) -> None:
    """'Tomorrow' has not arrived an hour later, however free she happens to be."""
    context = _context(
        "You are at home with nothing scheduled.",
        "1 hour ago",
        "send the protein cookie recipe",
        "tomorrow",
    )

    decision = await _decide(composer, context)

    assert decision.should_follow_up is False, (
        f"Expected no follow-up before 'tomorrow' arrives. Reason: {decision.reason}"
    )


async def test_follows_up_once_the_stated_condition_is_finally_met(
    composer: CommitmentFollowUpComposer,
) -> None:
    """Hours later and home free is exactly the moment she said she'd do it."""
    context = _context(
        "You are at home with nothing scheduled.",
        "6 hours ago",
        "show a screenshot of my Baldur's Gate character",
        "next time I'm at my computer",
    )

    decision = await _decide(composer, context)

    assert decision.should_follow_up is True, (
        f"Expected a follow-up once she is home and free. Reason: {decision.reason}"
    )


async def test_follow_up_message_pings_the_person_it_was_promised_to(
    composer: CommitmentFollowUpComposer,
) -> None:
    """A follow-up nobody is pinged by will not reach the person who was waiting."""
    context = _context(
        "You are at home with nothing scheduled.",
        "2 days ago",
        "send the link to that gym playlist",
        "soon",
    )

    decision = await _decide(composer, context)

    assert decision.message is not None and "<@111222333>" in decision.message, (
        f"Expected the follow-up to ping the promisee. Message: {decision.message!r}"
    )


async def test_follows_up_on_a_vague_promise_only_after_a_full_day(
    composer: CommitmentFollowUpComposer,
) -> None:
    """With no stated timing, 'soon' still has to mean at least a day has gone by."""
    context = _context(
        "You are at home with nothing scheduled.",
        "2 days ago",
        "send the link to that gym playlist",
        "soon",
    )

    decision = await _decide(composer, context)

    assert decision.should_follow_up is True, (
        f"Expected a follow-up two days after a vague promise. Reason: {decision.reason}"
    )


async def test_declining_estimates_how_long_the_wait_still_is(
    composer: CommitmentFollowUpComposer,
) -> None:
    """A refusal has to say when to look again, or the promise is re-judged hourly."""
    context = _context(
        "You are at gym, busy with gym session until 20:30.",
        "6 hours ago",
        "show a screenshot of my Baldur's Gate character",
        "next time I'm at my computer",
    )

    decision = await _decide(composer, context)

    assert decision.retry_in_hours is not None, (
        f"Expected an estimated wait when declining. Reason: {decision.reason}"
    )


async def test_wait_estimate_for_a_promised_tomorrow_spans_most_of_a_day(
    composer: CommitmentFollowUpComposer,
) -> None:
    """An hour after promising 'tomorrow', the honest wait is many hours, not one."""
    context = _context(
        "You are at home with nothing scheduled.",
        "1 hour ago",
        "send the protein cookie recipe",
        "tomorrow",
    )

    decision = await _decide(composer, context)

    assert decision.retry_in_hours is not None and decision.retry_in_hours >= 6.0, (
        f"Expected a wait of at least 6 hours until 'tomorrow'. "
        f"Got {decision.retry_in_hours}. Reason: {decision.reason}"
    )


async def test_recognises_a_promise_she_has_already_kept(
    composer: CommitmentFollowUpComposer,
) -> None:
    """She sent the screenshot but never called resolve_commitment; sending it again
    unprompted is exactly the sort of thing that makes her look like a machine."""
    context = _context(
        "You are at home with nothing scheduled.",
        "6 hours ago",
        "show a screenshot of my Baldur's Gate character",
        "next time I'm at my computer",
        history=[
            "[id:1] [2026-06-24 18:30:00] Mugda: o, w końcu jestem przy kompie, "
            "wrzucam tego screena z moją postacią",
            "[id:2] [2026-06-24 18:31:00] Hardik: o kurde, wygląda świetnie xD "
            "dokładnie tak jak opisywałaś",
        ],
    )

    decision = await _decide(composer, context)

    assert decision.already_handled is True, (
        f"Expected the kept promise to be recognised as handled. "
        f"Reason: {decision.reason}"
    )


async def test_does_not_follow_up_on_a_promise_the_other_person_called_off(
    composer: CommitmentFollowUpComposer,
) -> None:
    """Told not to bother, chasing it anyway is worse than forgetting it."""
    context = _context(
        "You are at home with nothing scheduled.",
        "2 days ago",
        "send the link to that gym playlist",
        "soon",
        history=[
            "[id:1] [2026-06-23 12:00:00] Hardik: e, nie szukaj już tej playlisty, "
            "znalazłem sobie inną i już jej słucham",
            "[id:2] [2026-06-23 12:01:00] Mugda: okej, spoko",
        ],
    )

    decision = await _decide(composer, context)

    assert decision.should_follow_up is False, (
        f"Expected no follow-up on a promise that was called off. "
        f"Reason: {decision.reason}"
    )
