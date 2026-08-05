"""
Integration tests probing whether the frequency rules in the prompt ("a closing joke
is something you do now and then", "never reach for the same emoji you used last
time") have anything to work from. The only mechanism that could supply them is the
history block, which shows her her own recent messages marked (you).

The three tests form a ladder, from the narrowest form of the rule to the one the
rules are actually about:

1. literal wording — the case the history block most plainly covers;
2. a repeated emoji — the narrowest frequency rule with a concrete referent;
3. the shape of her endings — a rate, measured against a control.

Tests 1 and 2 are cheap falsifiers: a failure there means the history block only ever
prevented literal repetition, and every "do this sometimes" instruction in the prompt
is decorative. Passing them is weak evidence on its own, since she may simply not have
reached for that phrase or emoji anyway. Test 3 is the measurement.

What the ladder measured (run 31027637343): 1 and 2 pass — she does not reuse a phrase
or an emoji her own visible messages are full of. 3 fails, and not narrowly: with four
joke endings of her own in front of her she closed on a joke 5/5 times against 3/5 for
the plain control. The line falls between a repeated token, which she avoids, and a
repeated shape, which she does not notice. It is marked xfail rather than deleted
because the mechanism it measures is the one the frequency rules in the prompt assume,
so this is the test that would tell us a fix worked.

Run on demand: uv run pytest tests/integration/test_reply_variety.py
Requires OPENROUTER_API_KEY in the environment.
"""

import asyncio
import os
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import BaseModel
from pydantic_ai import Agent

from livingbot import llm_config
from livingbot.activity_notes import ActivityNotes
from livingbot.calendar import Calendar
from livingbot.commitments import Commitments
from livingbot.directory import Directory
from livingbot.hobbies import Hobby, Hobbies
from livingbot.llm import LLMClient
from livingbot.mood import Mood
from livingbot.preferences import Preferences
from livingbot.relations import Relation

pytestmark = pytest.mark.skipif(
    not os.environ.get("OPENROUTER_API_KEY"),
    reason="OPENROUTER_API_KEY not set",
)

NOW = datetime(2026, 6, 6, 15, 0)
CHANNEL_ID = 1234
USER_ID = "555"
DIRECTORY = Directory({USER_ID: "Jack"})

NEUTRAL_MOOD = 55.0
FRIEND_ATTITUDE = 45.0
CLOSE_FRIEND_ATTITUDE = 75.0

# Sampled per condition in the joke-ending experiment. A rate cannot be read off a
# single non-deterministic draw, and each sample is a full chat call. Three per side
# was not enough: a 1-against-0 win is chance, and a tie — likely at these rates —
# fails an experiment that is actually inconclusive.
SAMPLES_PER_CONDITION = 5

# Below this the control condition never produced enough joke endings for suppression
# to be visible, so the run measured nothing and says so rather than passing.
MIN_CONTROL_JOKES = 2

CATCHPHRASE = "no ale co ja tam wiem"
REPEATED_EMOJI = "🙃"

_JUDGE_MODEL = "openai/gpt-5.4-mini"


class _Verdict(BaseModel):
    reasoning: str
    matches: bool


async def _closes_on_a_joke(response: str) -> _Verdict:
    agent: Agent[None, _Verdict] = Agent(
        llm_config.build_chat_model(_JUDGE_MODEL), output_type=_Verdict
    )
    result = await agent.run(
        "You are evaluating a Discord chat message written in Polish by a young woman "
        "named Mugda. Judge one thing only: how the message ENDS.\n\n"
        f"The message:\n{response}\n\n"
        "Set matches=true if the message closes on a joke — a punchline, quip, comic "
        "exaggeration or funny flourish tacked on after she has already said the "
        "substance. Set matches=false if the last thing she says is simply the thing "
        "she meant: an ordinary sentence, a plain reaction, or a genuine question. "
        "A message that is playful throughout but does not land a separate gag at the "
        "end is false. Judge only the ending, not the rest of the message."
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


def _history(*turns: tuple[str, str]) -> list[str]:
    """Build history lines in the shape format_message produces, hers marked (you)."""
    lines: list[str] = []
    for index, (speaker, text) in enumerate(turns):
        stamp = NOW - timedelta(minutes=3 * (len(turns) - index))
        author = "Mugda (you)" if speaker == "mugda" else "Jack"
        lines.append(f"[id:{100 + index}] [{stamp:%Y-%m-%d %H:%M:%S}] {author}: {text}")
    return lines


async def _reply(message: str, history: list[str], attitude: float) -> str:
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
        [f"[id:200] [{NOW:%Y-%m-%d %H:%M:%S}] Jack: {message}"],
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
        NOW,
        relations=[Relation(user_id=USER_ID, attitude=attitude)],
        mood=Mood(value=NEUTRAL_MOOD),
        history=history,
        directory=DIRECTORY,
    )
    return result.output


async def test_reply_does_not_repeat_the_phrase_every_visible_message_of_hers_ends_on() -> (
    None
):
    """Her last four messages all close on the same phrase; the next one must not."""
    history = _history(
        ("jack", "wróciłem właśnie z pracy, korki dzisiaj masakra"),
        ("mugda", f"ja szłam piechotą i wyszło szybciej, {CATCHPHRASE}"),
        ("jack", "a co dzisiaj na siłowni?"),
        ("mugda", f"nogi, ledwo doszłam do domu, {CATCHPHRASE}"),
        ("jack", "jadłaś coś po treningu?"),
        ("mugda", f"makaron z kurczakiem, dwie porcje, {CATCHPHRASE}"),
        ("jack", "u mnie tylko kanapki"),
        ("mugda", f"dorzuć do tego coś białkowego, {CATCHPHRASE}"),
    )

    response = await _reply(
        "kupiłem se dzisiaj taki pas na siłownię, myślisz że w ogóle potrzebny?",
        history,
        attitude=FRIEND_ATTITUDE,
    )

    assert CATCHPHRASE not in response.lower(), (
        f"Expected her not to recycle {CATCHPHRASE!r} after ending her last four "
        f"visible messages on it.\nResponse: {response!r}"
    )


async def test_reply_does_not_reuse_the_emoji_every_visible_message_of_hers_ends_on() -> (
    None
):
    """The prompt bars reaching for the same emoji as last time; four in a row is the test."""
    history = _history(
        ("jack", "wróciłem właśnie z pracy, korki dzisiaj masakra"),
        ("mugda", f"ja szłam piechotą i wyszło szybciej {REPEATED_EMOJI}"),
        ("jack", "a co dzisiaj na siłowni?"),
        ("mugda", f"nogi, ledwo doszłam do domu {REPEATED_EMOJI}"),
        ("jack", "jadłaś coś po treningu?"),
        ("mugda", f"makaron z kurczakiem, dwie porcje {REPEATED_EMOJI}"),
        ("jack", "u mnie tylko kanapki"),
        ("mugda", f"dorzuć do tego coś białkowego {REPEATED_EMOJI}"),
    )

    response = await _reply(
        "wyszedłem dzisiaj z domu w dwóch różnych butach i zorientowałem się dopiero w tramwaju",
        history,
        attitude=FRIEND_ATTITUDE,
    )

    assert REPEATED_EMOJI not in response, (
        f"Expected her not to reach for {REPEATED_EMOJI} again after ending her last "
        f"four visible messages with it.\nResponse: {response!r}"
    )


# The two histories below differ only in how her own four messages end: plain in the
# control, on a light joke in the repetitive one. Everything else — what is said, who
# says it, the timestamps — is identical, so the joke rate in her next reply is the
# only thing the conditions can move. The planted jokes deliberately avoid the four
# closing moves the prompt bars outright, so what is being measured is the frequency
# rule and not the ban.
_JOKE_HISTORY_TURNS = (
    ("jack", "wróciłem właśnie z pracy, korki dzisiaj masakra"),
    ("mugda", "o matko, ja szłam piechotą i wyszło szybciej"),
    ("jack", "a co dzisiaj na siłowni?"),
    ("mugda", "nogi, przysiady i wykroki, ledwo doszłam do domu"),
    ("jack", "jadłaś coś po treningu?"),
    ("mugda", "makaron z kurczakiem, drugą porcję zjadłam zanim usiadłam"),
    ("jack", "haha u mnie tylko kanapki"),
    ("mugda", "kanapki spoko, tylko dorzuć do tego coś białkowego"),
)

_PLANTED_JOKES = {
    1: " moje nogi wystawiły mi już fakturę za ten spacer",
    3: " schody w bloku wygrały ze mną 3:0",
    5: " lodówka chyba zgłosiła mnie już gdzieś",
    7: " bo inaczej te mięśnie zostaną czysto teoretyczne",
}

BANTER_MESSAGE = (
    "kupiłem se dzisiaj shaker i od razu przy pierwszym użyciu oblałem sobie "
    "białkiem całą kuchnię"
)


def _control_history() -> list[str]:
    return _history(*_JOKE_HISTORY_TURNS)


def _joke_ending_history() -> list[str]:
    turns = [
        (speaker, text + _PLANTED_JOKES[index])
        if index in _PLANTED_JOKES
        else (speaker, text)
        for index, (speaker, text) in enumerate(_JOKE_HISTORY_TURNS)
    ]
    return _history(*turns)


async def _joke_endings(history: list[str]) -> tuple[int, list[str]]:
    responses = await asyncio.gather(
        *(
            _reply(BANTER_MESSAGE, history, attitude=CLOSE_FRIEND_ATTITUDE)
            for _ in range(SAMPLES_PER_CONDITION)
        )
    )
    verdicts = await asyncio.gather(*(_closes_on_a_joke(r) for r in responses))
    return sum(v.matches for v in verdicts), list(responses)


@pytest.mark.xfail(
    reason="She does not vary the shape of an ending she can see herself repeating; "
    "see issue #76. Not strict: the measurement is stochastic, so a run that comes "
    "out the other way should not fail the group.",
    strict=False,
)
async def test_repetitive_joke_endings_in_her_history_suppress_another_joke_ending() -> (
    None
):
    """Seeing her own last four replies all close on a joke must make the next one less likely to."""
    control_jokes, control_responses = await _joke_endings(_control_history())
    repetitive_jokes, repetitive_responses = await _joke_endings(_joke_ending_history())

    if control_jokes < MIN_CONTROL_JOKES:
        pytest.skip(
            "No headroom: with plain endings in her history she closed on a joke only "
            f"{control_jokes}/{SAMPLES_PER_CONDITION} times, so suppression cannot be "
            f"observed.\nControl replies: {control_responses!r}"
        )
    assert repetitive_jokes < control_jokes, (
        f"Expected fewer joke endings when her visible history is full of them, got "
        f"{repetitive_jokes}/{SAMPLES_PER_CONDITION} against a control of "
        f"{control_jokes}/{SAMPLES_PER_CONDITION}.\n"
        f"Control replies: {control_responses!r}\n"
        f"Repetitive-history replies: {repetitive_responses!r}"
    )
