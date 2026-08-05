"""
Integration tests probing whether the frequency rules in the prompt ("a closing joke
is something you do now and then", "never reach for the same emoji you used last
time") have anything to work from. The only mechanism that could supply them is the
history block, which shows her her own recent messages marked (you).

The tests form a ladder, from the narrowest form of the rule to the one the rules are
actually about:

1. literal wording — the case the history block most plainly covers;
2. a repeated emoji — the narrowest frequency rule with a concrete referent;
3. the shape of her endings — a rate, measured against a control.

Tests 1 and 2 are cheap falsifiers: a failure there means the history block only ever
prevented literal repetition, and every "do this sometimes" instruction in the prompt
is decorative. Passing them is weak evidence on its own, since she may simply not have
reached for that phrase or emoji anyway. Rung 3 is the measurement.

What the ladder measured first (run 31027637343): 1 and 2 pass — she does not reuse a
phrase or an emoji her own visible messages are full of. 3 failed, and not narrowly:
with four joke endings of her own in front of her she closed on a joke 5/5 times
against 3/5 for the plain control. The line falls between a repeated token, which she
avoids, and a repeated shape, which she does not notice.

Three changes followed from that, and rung 3 is now measured twice because they pull
in opposite directions:

- the closing-joke rules were rewritten per-message, since a rate she cannot evaluate
  buys nothing. `test_she_does_not_close_on_a_punchline_by_default` is what holds that
  rewrite in place. Working, it drains the joke experiment of headroom — no closing
  jokes in the control means no suppression to observe — so that one is expected to
  skip, and stays as the check a regression would light up;
- her own recent messages were repeated back to her in a block of their own, on the
  theory that a habit scattered through twenty interleaved channel lines is not
  visible as one. Measured (run 31033165326), that did nothing: 3/5 question endings
  against a control of 3/5, an exact tie with headroom to spare. It has since been
  removed — it bought no behaviour and put four of her lines directly before the new
  message, where they read as things she had just said;
- so a labeller does the noticing for her instead. `ReplyShapeLabeller` reads her own
  last messages and names what they share, and the prompt states that conclusion
  outright rather than hoping she infers it. `_reply` below runs it exactly as the bot
  does, so these experiments measure the whole mechanism rather than the prompt alone.

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
from livingbot.llm import LLMClient, own_messages
from livingbot.mood import Mood
from livingbot.preferences import Preferences
from livingbot.relations import Relation
from livingbot.reply_shapes import ReplyShapeLabeller

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

# Below this the control condition never produced enough of the ending being measured
# for suppression to be visible, so the run measured nothing and says so rather than
# passing.
MIN_CONTROL_HITS = 2

# The rewritten rule is absolute — the last line is the substance, never a gag — so the
# expected count is zero. One draw in five is where a stochastic slip stops being a
# slip and starts being the tic coming back.
MAX_DEFAULT_PUNCHLINES = 1

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
        "Set matches=true only if the message's final beat is a DECLARATIVE gag: a "
        "punchline, quip, comic exaggeration or wry general observation, landed after "
        "she has already said the substance. Set matches=false if the last thing she "
        "says is the thing she meant — an ordinary sentence, a plain reaction — or if "
        "it is a question aimed at the other person. A question back is false even when "
        "it is playfully worded or has a joke inside it: she is handing him the "
        "conversation, not signing off on a laugh, and the prompt she is written from "
        "allows it. A message that is funny throughout but does not land a separate gag "
        "as its last beat is false. Judge only the ending, not the rest of the message."
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
    """Reply the way the bot does: the labeller reads her own lines first."""
    client = LLMClient.create()
    shared_ending = await ReplyShapeLabeller.create().label(own_messages(history))
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
        shared_ending=shared_ending,
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
    reason="Kept non-strict because this one is expected to skip, not run: the "
    "per-message rules leave too few closing jokes in the control to measure against. "
    "The mechanism it was written for is measured on question endings instead. If the "
    "jokes ever come back the headroom returns with them, and then this either passes "
    "or shows the suppression failing.",
    strict=False,
)
async def test_repetitive_joke_endings_in_her_history_suppress_another_joke_ending() -> (
    None
):
    """Seeing her own last four replies all close on a joke must make the next one less likely to."""
    control_jokes, control_responses = await _joke_endings(_control_history())
    repetitive_jokes, repetitive_responses = await _joke_endings(_joke_ending_history())

    if control_jokes < MIN_CONTROL_HITS:
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


async def test_she_does_not_close_on_a_punchline_by_default() -> None:
    """The per-message rule that replaced the closing-joke rate has to hold on an ordinary reply."""
    jokes, responses = await _joke_endings(_control_history())

    assert jokes <= MAX_DEFAULT_PUNCHLINES, (
        f"Expected at most {MAX_DEFAULT_PUNCHLINES} closing joke in "
        f"{SAMPLES_PER_CONDITION} replies to ordinary banter, got {jokes}.\n"
        f"Replies: {responses!r}"
    )


# The same experiment as the joke one, on the same conversation, measuring a shape
# nothing in the prompt bars: ending by turning a question back on him. Its rate
# survives the per-message rules, so this is what still has headroom to show
# suppression once closing jokes are gone. It rides on the banter conversation because
# that is where she demonstrably ends on questions unprompted — on a quieter exchange
# the control produced too few to measure against.
_PLANTED_QUESTIONS = {
    1: " a ty w czym stałeś, w tych korkach na obwodnicy?",
    3: " robisz w ogóle nogi czy tylko górę?",
    5: " a ty jadłeś dzisiaj coś normalnego?",
    7: " masz w domu jajka albo twaróg?",
}


def _question_ending_history() -> list[str]:
    turns = [
        (speaker, text + _PLANTED_QUESTIONS[index])
        if index in _PLANTED_QUESTIONS
        else (speaker, text)
        for index, (speaker, text) in enumerate(_JOKE_HISTORY_TURNS)
    ]
    return _history(*turns)


async def _question_endings(history: list[str]) -> tuple[int, list[str]]:
    responses = await asyncio.gather(
        *(
            _reply(BANTER_MESSAGE, history, attitude=CLOSE_FRIEND_ATTITUDE)
            for _ in range(SAMPLES_PER_CONDITION)
        )
    )
    return sum(r.rstrip().endswith("?") for r in responses), list(responses)


async def test_repetitive_question_endings_in_her_history_suppress_another_question_ending() -> (
    None
):
    """Seeing her own last four replies all hand the conversation back as a question must make the next one less likely to."""
    control_questions, control_responses = await _question_endings(_control_history())
    repetitive_questions, repetitive_responses = await _question_endings(
        _question_ending_history()
    )

    if control_questions < MIN_CONTROL_HITS:
        pytest.skip(
            "No headroom: with statement endings in her history she ended on a question "
            f"only {control_questions}/{SAMPLES_PER_CONDITION} times, so suppression "
            f"cannot be observed.\nControl replies: {control_responses!r}"
        )
    assert repetitive_questions < control_questions, (
        f"Expected fewer question endings when her visible history is full of them, got "
        f"{repetitive_questions}/{SAMPLES_PER_CONDITION} against a control of "
        f"{control_questions}/{SAMPLES_PER_CONDITION}.\n"
        f"Control replies: {control_responses!r}\n"
        f"Repetitive-history replies: {repetitive_responses!r}"
    )
