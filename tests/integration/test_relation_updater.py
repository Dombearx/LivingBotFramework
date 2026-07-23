"""
Integration tests that send real requests to the LLM and verify RelationUpdater
produces sensible relation updates given realistic Discord conversations in Polish.

Run on demand: uv run pytest tests/integration/
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


async def test_attitude_increases_after_warm_friendly_exchange(
    updater: RelationUpdater,
) -> None:
    """Attitude should rise when the user is consistently warm and appreciative."""
    relation = Relation(user_id="marek", attitude=0)
    conversation = _convo(
        (
            "user",
            "hej! dzięki za wczoraj, naprawdę pomogłeś mi z tym zadaniem, byłeś super",
        ),
        ("assistant", "nie ma za co, zawsze mogę pomóc :)"),
        (
            "user",
            "serio, bez ciebie bym nie dał rady. jesteś najlepszy na tym serwerze",
        ),
        ("assistant", "haha no może trochę przesadzasz, ale miło słyszeć"),
        ("user", "nie przesadzam! następnym razem stawiam wirtualną kawę"),
    )

    updated = await updater.update(relation, conversation)

    assert updated.attitude > 0, (
        f"Expected positive attitude after warm exchange, got {updated.attitude}"
    )


async def test_attitude_decreases_after_hostile_confrontation(
    updater: RelationUpdater,
) -> None:
    """Attitude should drop when the user is rude and aggressive."""
    relation = Relation(user_id="bartek", attitude=20)
    conversation = _convo(
        (
            "user",
            "ty i twoje odpowiedzi to totalna strata czasu, nie masz pojęcia o niczym",
        ),
        ("assistant", "przepraszam, mogę spróbować inaczej wyjaśnić"),
        (
            "user",
            "nie przepraszaj tylko wreszcie zacznij ogarniać. jesteś bezużyteczny",
        ),
        ("assistant", "okej, powiedz mi co konkretnie jest niejasne"),
        ("user", "wszystko. dosłownie wszystko co piszesz to bzdury"),
    )

    updated = await updater.update(relation, conversation)

    assert updated.attitude < 20, (
        f"Expected attitude to drop after hostility, got {updated.attitude} (was 20)"
    )


async def test_inside_joke_is_added_after_shared_funny_moment(
    updater: RelationUpdater,
) -> None:
    """An inside joke should be recorded when a clear running joke is established."""
    relation = Relation(user_id="kasia", attitude=30)
    conversation = _convo(
        ("user", "hej, znowu ten serwer padł w środku raidu xD"),
        ("assistant", "klasyka, jak zawsze w najlepszym momencie"),
        (
            "user",
            "już za trzecim razem jak to się stało to postanowiliśmy to nazwać — 'błogosławieństwo Łagodnego Serwera'",
        ),
        ("assistant", "hahaha idealna nazwa, pasuje w sto procent"),
        (
            "user",
            "od teraz każdy lag to 'błogosławieństwo' — już to weszło do słownika gildii",
        ),
        (
            "assistant",
            "będę pamiętać, następnym razem jak coś padnie powiem że dostaliśmy kolejne błogosławieństwo",
        ),
    )

    updated = await updater.update(relation, conversation)

    assert len(updated.inside_jokes) > 0, (
        f"Expected inside joke to be recorded, got empty list. attitude={updated.attitude}"
    )
    joined = " ".join(updated.inside_jokes).lower()
    assert any(word in joined for word in ["błogosław", "serwer", "lag"]), (
        f"Expected joke about the server blessing, got: {updated.inside_jokes}"
    )


async def test_most_important_memory_captures_significant_personal_event(
    updater: RelationUpdater,
) -> None:
    """A major personal milestone shared by the user should land in most_important_memory."""
    relation = Relation(user_id="piotrek", attitude=15)
    conversation = _convo(
        (
            "user",
            "hej, właśnie dostałem wyniki — dostałem się na studia do Wrocławia! informatyka na PWr",
        ),
        ("assistant", "wow, gratulacje!! to ogromna sprawa, ciężko pracowałeś na to"),
        ("user", "tak, trzy lata przygotowań i w końcu się udało. nie mogę uwierzyć"),
        ("assistant", "zasłużone, na pewno sobie poradzisz tam świetnie"),
        (
            "user",
            "dzięki, właśnie cała rodzina się dowiedziała, wszyscy są mega szczęśliwi",
        ),
    )

    updated = await updater.update(relation, conversation)

    assert updated.most_important_memory != "", (
        "Expected most_important_memory to be set, got empty string"
    )
    memory_lower = updated.most_important_memory.lower()
    assert any(
        word in memory_lower
        for word in ["studia", "wrocław", "pwr", "informatyk", "dostał"]
    ), (
        f"Expected memory about university admission, got: '{updated.most_important_memory}'"
    )


async def test_topics_of_interest_captured_from_passionate_gaming_talk(
    updater: RelationUpdater,
) -> None:
    """Topics a user clearly cares about should be added to topics_of_interest."""
    relation = Relation(user_id="tomek", attitude=10)
    conversation = _convo(
        (
            "user",
            "grasz w League of Legends? właśnie wbijam do diamentu, zostało mi 20lp",
        ),
        ("assistant", "niezły progres, jak długo grasz?"),
        (
            "user",
            "od trzech lat, gram głównie jungle — Vi i Hecarim. wcześniej grałem w CS ale lol mnie wciągnął",
        ),
        ("assistant", "jungle to trudna rola, musisz ogarniać całą mapę"),
        (
            "user",
            "właśnie o to chodzi, lubię kontrolować grę. oglądam też dużo streamów pro graczy żeby się uczyć",
        ),
        ("assistant", "widać że traktujesz to poważnie"),
        (
            "user",
            "tak, marzę o tym żeby kiedyś zagrać na challenie. to mój główny cel w tym roku",
        ),
    )

    updated = await updater.update(relation, conversation)

    assert len(updated.topics_of_interest) > 0, (
        "Expected topics_of_interest to be set, got empty list"
    )
    joined = " ".join(updated.topics_of_interest).lower()
    assert any(
        word in joined for word in ["league", "lol", "gry", "gaming", "jungle", "cs"]
    ), f"Expected gaming-related topics, got: {updated.topics_of_interest}"


async def test_relation_stays_stable_after_short_neutral_small_talk(
    updater: RelationUpdater,
) -> None:
    """Shallow small talk should not significantly move attitude or add noise to the relation."""
    relation = Relation(user_id="ania", attitude=5, topics_of_interest=["muzyka"])
    conversation = _convo(
        ("user", "hej"),
        ("assistant", "hej, co słychać?"),
        ("user", "nic takiego, po prostu wpadłam sprawdzić co na serwerze"),
        ("assistant", "spokojnie u nas, nic nowego"),
        ("user", "okej, dobra nara"),
        ("assistant", "nara!"),
    )

    updated = await updater.update(relation, conversation)

    assert abs(updated.attitude - 5) <= 15, (
        f"Expected attitude to stay near 5 after neutral chat, got {updated.attitude}"
    )
    assert (
        updated.topics_of_interest == ["muzyka"]
        or "muzyka" in updated.topics_of_interest
    ), f"Expected existing topics to be preserved, got: {updated.topics_of_interest}"


async def test_multiple_fields_update_after_rich_conversation(
    updater: RelationUpdater,
) -> None:
    """A detailed, emotionally rich conversation should update attitude, memory and topics together."""
    relation = Relation(user_id="michal", attitude=-10)
    conversation = _convo(
        (
            "user",
            "hej, przepraszam za ostatnim razem że byłem agresywny. miałem ciężki dzień",
        ),
        ("assistant", "spoko, rozumiem, zdarza się"),
        (
            "user",
            "właśnie wróciłem z turnieju szachowego — wygrałem! pierwsze miejsce w województwie",
        ),
        ("assistant", "nie wiedziałem że grasz w szachy! to świetny wynik, gratulacje"),
        (
            "user",
            "tak, od dziecka gram. to moja największa pasja obok programowania. btw — w pracy właśnie awansowałem na seniora",
        ),
        ("assistant", "kurde, to podwójny sukces! dobrze ci idzie ostatnio"),
        (
            "user",
            "no tak, może dlatego jestem dziś w lepszym humorze haha. i faktycznie przepraszam jeszcze raz",
        ),
        ("assistant", "nie ma za co, teraz widzę cię z lepszej strony"),
    )

    updated = await updater.update(relation, conversation)

    assert updated.attitude > -10, (
        f"Expected attitude to improve after apology and positive conversation, got {updated.attitude}"
    )
    assert updated.most_important_memory != "", (
        "Expected most_important_memory to capture a key event"
    )
    assert len(updated.topics_of_interest) > 0, (
        "Expected topics_of_interest to be populated from the conversation"
    )
