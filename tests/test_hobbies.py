from datetime import datetime, timedelta

from livingbot.hobbies import (
    Hobby,
    HobbyLevel,
    HobbyStore,
    Hobbies,
    LEVEL_UP_THRESHOLDS,
    recent_hobbies,
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
