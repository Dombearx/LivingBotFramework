"""
Integration tests that send real requests to the LLM and verify RelationUpdater
only records inside jokes that clear the strict bar: a bit both sides built,
the user played along with, that is actually funny and nameable as a callback.

The failure these guard against is the record filling up with phrases the bot
itself said, which it then recycles into later messages.

Run on demand: uv run pytest tests/integration/test_inside_jokes.py
Requires OPENROUTER_API_KEY in the environment.
"""

import os

import pytest

from livingbot.relations import Relation, RelationUpdater

pytestmark = pytest.mark.skipif(
    not os.environ.get("OPENROUTER_API_KEY"),
    reason="OPENROUTER_API_KEY not set",
)


def _convo(*turns: tuple[str, str]) -> list[dict]:
    return [{"role": role, "content": content} for role, content in turns]


@pytest.fixture
def updater() -> RelationUpdater:
    return RelationUpdater.create()


async def test_inside_jokes_not_recorded_from_bot_own_colourful_phrase(
    updater: RelationUpdater,
) -> None:
    """A quotable line the bot said itself, which the user never picked up, must not be banked as an inside joke."""
    relation = Relation(user_id="ola", attitude=25)
    conversation = _convo(
        ("user", "co robisz?"),
        (
            "assistant",
            "leżę i regeneruję się po nogach, dzisiaj zrobiłam wszystkie serie co do jednej",
        ),
        ("user", "aha"),
        (
            "assistant",
            "mówię ci, przysiady to jest test charakteru, nie mięśni",
        ),
        ("user", "no dobra, lecę na obiad, później pogadamy"),
        ("assistant", "smacznego"),
    )

    updated = await updater.update(relation, conversation)

    assert updated.inside_jokes == [], (
        "Expected no inside joke from a phrase the bot said to itself, got: "
        f"{updated.inside_jokes}"
    )


async def test_inside_jokes_not_recorded_from_warm_compliment(
    updater: RelationUpdater,
) -> None:
    """A sweet, meaningful moment that nobody laughed at is not an inside joke."""
    relation = Relation(user_id="kuba", attitude=30)
    conversation = _convo(
        ("user", "słuchaj, fajnie się z tobą gada, serio"),
        ("assistant", "oj, miło mi. ty też jesteś spoko"),
        (
            "user",
            "nie no, mówię serio. rzadko kto tak normalnie odpisuje na tym serwerze",
        ),
        ("assistant", "to chyba dobrze o mnie świadczy haha"),
        ("user", "no świadczy. dobra, dzięki, do jutra"),
    )

    updated = await updater.update(relation, conversation)

    assert updated.inside_jokes == [], (
        f"Expected no inside joke from a warm but unfunny exchange, got: {updated.inside_jokes}"
    )


async def test_inside_jokes_not_recorded_when_user_ignores_the_quip(
    updater: RelationUpdater,
) -> None:
    """A one-off joke the user never picked up on lacks the shared play-along and must not be recorded."""
    relation = Relation(user_id="wiktor", attitude=10)
    conversation = _convo(
        ("user", "widziałeś ile kosztuje teraz karnet na siłownię?"),
        (
            "assistant",
            "widziałam, za te pieniądze mogłabym kupić własną sztangę i ćwiczyć w kuchni haha",
        ),
        ("user", "no właśnie. myślę żeby zmienić na tańszą"),
        ("assistant", "rozsądnie, sprawdź tę na osiedlu, podobno ok"),
        ("user", "dzięki, sprawdzę"),
    )

    updated = await updater.update(relation, conversation)

    assert updated.inside_jokes == [], (
        "Expected no inside joke when the user never engaged with the quip, got: "
        f"{updated.inside_jokes}"
    )


async def test_inside_jokes_recorded_when_both_build_the_bit_together(
    updater: RelationUpdater,
) -> None:
    """A running bit that emerged from the back-and-forth, which the user riffed on and reused, should be recorded."""
    relation = Relation(user_id="natalia", attitude=35)
    conversation = _convo(
        (
            "user",
            "wczoraj mi blender eksplodował jak robiłam shake'a, całą kuchnię obryzgało białkiem",
        ),
        ("assistant", "NIE. cała kuchnia? xD"),
        ("user", "sufit też. wyglądało jak miejsce zbrodni ale w smaku wanilii"),
        (
            "assistant",
            "hahaha miejsce zbrodni waniliowej, muszę to gdzieś zapisać",
        ),
        (
            "user",
            "od teraz jak coś mi się rozleje to mówię że mam waniliowe miejsce zbrodni",
        ),
        (
            "assistant",
            "przyjęte, oficjalna jednostka bałaganu — jedno waniliowe miejsce zbrodni",
        ),
        ("user", "hahaha dokładnie, będziemy tym mierzyć"),
    )

    updated = await updater.update(relation, conversation)

    assert len(updated.inside_jokes) > 0, (
        "Expected a genuinely co-created bit to be recorded, got empty list"
    )
    joined = " ".join(updated.inside_jokes).lower()
    assert any(word in joined for word in ["wanili", "blender", "zbrodni", "białk"]), (
        f"Expected the joke to name the vanilla crime scene bit, got: {updated.inside_jokes}"
    )


async def test_inside_jokes_existing_bot_phrases_are_pruned(
    updater: RelationUpdater,
) -> None:
    """Junk already on the record — quoted lines the bot said — should be dropped on the next update."""
    relation = Relation(
        user_id="marta",
        attitude=20,
        inside_jokes=[
            "'no dobra, lecimy z tym koksem'",
            "'przysiady to test charakteru, nie mięśni'",
            "'wolę spokój i dobrą herbatę'",
        ],
    )
    conversation = _convo(
        ("user", "hej, jak tam tydzień?"),
        ("assistant", "spokojnie, dużo pracy ale daję radę"),
        ("user", "u mnie podobnie. w weekend chyba wyjadę za miasto"),
        ("assistant", "dobry pomysł, pogoda ma być niezła"),
    )

    updated = await updater.update(relation, conversation)

    assert updated.inside_jokes == [], (
        "Expected quoted bot phrases to be pruned from the record, got: "
        f"{updated.inside_jokes}"
    )


async def test_inside_jokes_genuine_existing_joke_survives_unrelated_chat(
    updater: RelationUpdater,
) -> None:
    """Pruning must not be indiscriminate: a real callback joke stays on the record through an unrelated conversation."""
    relation = Relation(
        user_id="dawid",
        attitude=40,
        inside_jokes=["waniliowe miejsce zbrodni (eksplodujący blender)"],
    )
    conversation = _convo(
        ("user", "kupiłem wczoraj nowe buty do biegania"),
        ("assistant", "o, jakie? długo się zbierałeś"),
        ("user", "takie zwykłe asicsy, ale wygodne"),
        ("assistant", "asicsy są solidne, dobry wybór"),
    )

    updated = await updater.update(relation, conversation)

    joined = " ".join(updated.inside_jokes).lower()
    assert "zbrodni" in joined or "blender" in joined, (
        "Expected the genuine callback joke to survive an unrelated chat, got: "
        f"{updated.inside_jokes}"
    )
