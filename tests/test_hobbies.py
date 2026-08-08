import logging
from datetime import datetime, timedelta

import pytest
from pydantic_ai import ModelRetry

from livingbot.hobbies import (
    Hobby,
    HobbyLevel,
    HobbyStore,
    Hobbies,
    LEVEL_UP_THRESHOLDS,
    experience_progress,
    find_hobby,
    recent_hobbies,
    reject_unknown_hobbies,
)

NOW = datetime(2026, 6, 12, 12, 0)


def test_gain_experience_below_threshold_stays_at_novice() -> None:
    hobby = Hobby(name="gym")

    hobby.gain_experience(LEVEL_UP_THRESHOLDS["novice"] - 1)

    assert hobby.level == HobbyLevel.novice
    assert hobby.experience == LEVEL_UP_THRESHOLDS["novice"] - 1


def test_gain_experience_at_threshold_levels_up_to_beginner() -> None:
    hobby = Hobby(name="gym")

    hobby.gain_experience(LEVEL_UP_THRESHOLDS["novice"])

    assert hobby.level == HobbyLevel.beginner
    assert hobby.experience == 0


def test_gain_experience_remainder_carries_over_after_level_up() -> None:
    hobby = Hobby(name="gym")

    hobby.gain_experience(LEVEL_UP_THRESHOLDS["novice"] + 50)

    assert hobby.level == HobbyLevel.beginner
    assert hobby.experience == 50


def test_gain_experience_levels_up_multiple_times_in_single_call() -> None:
    hobby = Hobby(name="gym")
    total = LEVEL_UP_THRESHOLDS["novice"] + LEVEL_UP_THRESHOLDS["beginner"]

    hobby.gain_experience(total)

    assert hobby.level == HobbyLevel.intermediate
    assert hobby.experience == 0


def test_gain_experience_at_expert_accumulates_without_leveling() -> None:
    hobby = Hobby(name="gym", level=HobbyLevel.expert, experience=0)

    hobby.gain_experience(500)

    assert hobby.level == HobbyLevel.expert
    assert hobby.experience == 500


def test_hobby_store_load_seeds_default_hobbies_when_file_missing(tmp_path) -> None:
    store = HobbyStore(tmp_path / "data", default_hobbies=["gym", "reading"])

    hobbies = store.load()

    assert [h.name for h in hobbies.entries] == ["gym", "reading"]
    assert all(h.level == HobbyLevel.novice for h in hobbies.entries)


def test_hobby_store_load_returns_saved_data_after_save(tmp_path) -> None:
    store = HobbyStore(tmp_path / "data", default_hobbies=[])
    original = Hobbies(
        entries=[Hobby(name="yoga", level=HobbyLevel.intermediate, experience=42)]
    )
    store.save(original)

    loaded = store.load()

    assert loaded.entries[0].name == "yoga"
    assert loaded.entries[0].level == HobbyLevel.intermediate
    assert loaded.entries[0].experience == 42


def test_hobby_store_gain_experience_levels_up_and_persists(tmp_path) -> None:
    store = HobbyStore(tmp_path / "data", default_hobbies=["gym"])

    store.gain_experience("gym", LEVEL_UP_THRESHOLDS["novice"])

    reloaded = store.load()
    gym = next(h for h in reloaded.entries if h.name == "gym")
    assert gym.level == HobbyLevel.beginner


def test_hobby_store_gain_experience_does_nothing_when_hobby_not_found(
    tmp_path,
) -> None:
    store = HobbyStore(tmp_path / "data", default_hobbies=["gym"])

    store.gain_experience("yoga", 999)

    hobbies = store.load()
    assert len(hobbies.entries) == 1
    assert hobbies.entries[0].name == "gym"


def test_hobby_store_gain_experience_warns_when_hobby_not_found(
    tmp_path, caplog
) -> None:
    store = HobbyStore(tmp_path / "data", default_hobbies=["gym"])

    with caplog.at_level(logging.WARNING, logger="livingbot.hobbies"):
        store.gain_experience("Gym", 10)

    assert "Dropped 10 xp: no hobby named 'Gym'. Her hobbies are: gym" in caplog.text


def test_experience_progress_below_expert_shows_threshold_and_next_level() -> None:
    hobby = Hobby(name="gym", level=HobbyLevel.novice, experience=20)

    progress = experience_progress(hobby)

    assert progress == "20 / 100 xp → beginner"


def test_experience_progress_at_expert_shows_bare_total() -> None:
    hobby = Hobby(name="gym", level=HobbyLevel.expert, experience=500)

    progress = experience_progress(hobby)

    assert progress == "500 xp"


def test_recent_hobbies_includes_hobby_acquired_within_window() -> None:
    hobby = Hobby(name="pottery", acquired_at=NOW - timedelta(days=8))
    hobbies = Hobbies(entries=[hobby])

    result = recent_hobbies(hobbies, NOW, timedelta(days=14))

    assert result == [hobby]


def test_recent_hobbies_excludes_hobby_acquired_before_window() -> None:
    hobby = Hobby(name="pottery", acquired_at=NOW - timedelta(days=15))
    hobbies = Hobbies(entries=[hobby])

    result = recent_hobbies(hobbies, NOW, timedelta(days=14))

    assert result == []


def test_recent_hobbies_excludes_hobby_with_no_acquired_at() -> None:
    hobby = Hobby(name="gym", acquired_at=None)
    hobbies = Hobbies(entries=[hobby])

    result = recent_hobbies(hobbies, NOW, timedelta(days=14))

    assert result == []


def test_find_hobby_returns_the_hobby_with_that_name() -> None:
    painting = Hobby(name="painting")
    hobbies = Hobbies(entries=[Hobby(name="gym"), painting])

    result = find_hobby(hobbies, "painting")

    assert result is painting


def test_find_hobby_when_no_hobby_has_that_name_returns_none() -> None:
    hobbies = Hobbies(entries=[Hobby(name="gym")])

    result = find_hobby(hobbies, "painting")

    assert result is None


def test_find_hobby_is_case_sensitive() -> None:
    hobbies = Hobbies(entries=[Hobby(name="gym")])

    result = find_hobby(hobbies, "Gym")

    assert result is None


def test_reject_unknown_hobbies_raises_when_a_name_is_not_hers() -> None:
    with pytest.raises(ModelRetry):
        reject_unknown_hobbies(["pottery"], ["gym"])


def test_reject_unknown_hobbies_retry_message_names_her_actual_hobbies() -> None:
    with pytest.raises(ModelRetry) as error:
        reject_unknown_hobbies(["pottery"], ["gym", "painting"])

    assert "gym, painting" in str(error.value)


def test_reject_unknown_hobbies_accepts_names_that_are_hers() -> None:
    reject_unknown_hobbies(["gym", "painting"], ["gym", "painting"])


def test_reject_unknown_hobbies_ignores_empty_names() -> None:
    reject_unknown_hobbies(["", "gym"], ["gym"])


def test_gain_experience_for_unknown_hobby_saves_nothing(tmp_path) -> None:
    store = HobbyStore(tmp_path, default_hobbies=["gym"])
    store.save(Hobbies(entries=[Hobby(name="gym")]))

    store.gain_experience("pottery", 10)

    assert store.load().entries[0].experience == 0
