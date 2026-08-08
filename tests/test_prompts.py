from datetime import datetime, timedelta

from livingbot.hobbies import Hobbies, Hobby, HobbyLevel
from livingbot.prompts import (
    HOBBY_IMAGE_SCOPE,
    HOBBY_LEVEL_IN_IMAGE,
    HOBBY_LEVEL_TONE,
    build_hobby_context,
    build_hobby_image_clause,
    build_scheduled_post_trigger,
)


def test_build_scheduled_post_trigger_includes_the_topic() -> None:
    result = build_scheduled_post_trigger("her new gym shoes")

    assert "her new gym shoes" in result


def test_build_scheduled_post_trigger_differs_per_topic() -> None:
    first = build_scheduled_post_trigger("her new gym shoes")
    second = build_scheduled_post_trigger("the trip to the mountains")

    assert first != second


def test_build_scheduled_post_trigger_without_mention_has_no_mention_instruction() -> (
    None
):
    result = build_scheduled_post_trigger("her new gym shoes")

    assert "@" not in result


def test_build_scheduled_post_trigger_with_mention_includes_the_persons_name() -> None:
    result = build_scheduled_post_trigger("her new gym shoes", mention_name="Kuba")

    assert "@Kuba" in result


NOW = datetime(2026, 6, 8, 12, 0)


def test_build_hobby_context_names_each_hobby_with_its_level() -> None:
    hobbies = Hobbies(
        entries=[
            Hobby(name="gym", level=HobbyLevel.expert),
            Hobby(name="painting", level=HobbyLevel.novice),
        ]
    )

    result = build_hobby_context(hobbies, NOW)

    assert "gym — expert:" in result
    assert "painting — novice:" in result


def test_build_hobby_context_describes_how_good_she_is_at_each_level() -> None:
    hobbies = Hobbies(entries=[Hobby(name="painting", level=HobbyLevel.novice)])

    result = build_hobby_context(hobbies, NOW)

    assert HOBBY_LEVEL_TONE[HobbyLevel.novice] in result


def test_build_hobby_context_mentions_a_hobby_she_only_just_took_up() -> None:
    hobbies = Hobbies(
        entries=[Hobby(name="painting", acquired_at=NOW - timedelta(days=3))]
    )

    result = build_hobby_context(hobbies, NOW)

    assert "She only recently took up: painting (3 days ago)." in result


def test_build_hobby_context_omits_recent_note_for_a_long_held_hobby() -> None:
    hobbies = Hobbies(entries=[Hobby(name="gym")])

    result = build_hobby_context(hobbies, NOW)

    assert "recently took up" not in result


def test_build_hobby_context_without_hobbies_says_she_has_none() -> None:
    result = build_hobby_context(Hobbies(), NOW)

    assert result == "She has no particular hobbies right now."


def test_build_hobby_image_clause_names_the_hobby() -> None:
    hobby = Hobby(name="painting", level=HobbyLevel.novice)

    result = build_hobby_image_clause(hobby)

    assert "made or did with painting" in result


def test_build_hobby_image_clause_describes_a_novices_work_as_bad() -> None:
    hobby = Hobby(name="painting", level=HobbyLevel.novice)

    result = build_hobby_image_clause(hobby)

    assert HOBBY_LEVEL_IN_IMAGE[HobbyLevel.novice] in result


def test_build_hobby_image_clause_describes_an_experts_work_as_masterful() -> None:
    hobby = Hobby(name="painting", level=HobbyLevel.expert)

    result = build_hobby_image_clause(hobby)

    assert HOBBY_LEVEL_IN_IMAGE[HobbyLevel.expert] in result


def test_build_hobby_image_clause_keeps_the_skill_off_the_illustration_itself() -> None:
    """Without this the whole picture degrades, instead of the thing she painted."""
    hobby = Hobby(name="painting", level=HobbyLevel.novice)

    result = build_hobby_image_clause(hobby)

    assert HOBBY_IMAGE_SCOPE in result
