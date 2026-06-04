from datetime import date, datetime
from unittest.mock import patch

from livingbot.calendar import Calendar, PlanEntry
from livingbot.mood import Mood, apply_interaction_delta, build_mood_block, refresh_mood


def make_gym_entry(end: datetime) -> PlanEntry:
    return PlanEntry(
        activity="gym",
        location="gym",
        start=datetime(end.year, end.month, end.day, end.hour - 1, end.minute),
        end=end,
    )


def empty_calendar() -> Calendar:
    return Calendar(home_location="home")


def calendar_with_gym(end: datetime) -> Calendar:
    return Calendar(home_location="home", entries=[make_gym_entry(end)])


# --- refresh_mood: drift ---


def test_refresh_mood_drifts_high_value_toward_neutral() -> None:
    mood = Mood(value=70.0, last_refreshed_at=datetime(2024, 6, 1, 10, 0))
    now = datetime(2024, 6, 1, 12, 0)  # 2 hours later

    result = refresh_mood(mood, now, empty_calendar())

    assert result.value < 70.0
    assert result.value >= 50.0


def test_refresh_mood_drifts_low_value_toward_neutral() -> None:
    mood = Mood(value=30.0, last_refreshed_at=datetime(2024, 6, 1, 10, 0))
    now = datetime(2024, 6, 1, 12, 0)

    result = refresh_mood(mood, now, empty_calendar())

    assert result.value > 30.0
    assert result.value <= 50.0


def test_refresh_mood_does_not_drift_past_neutral_from_above() -> None:
    mood = Mood(value=51.0, last_refreshed_at=datetime(2024, 6, 1, 10, 0))
    now = datetime(2024, 6, 1, 20, 0)  # 10 hours later, more than enough to overshoot

    result = refresh_mood(mood, now, empty_calendar())

    assert result.value == 50.0


def test_refresh_mood_does_not_drift_past_neutral_from_below() -> None:
    mood = Mood(value=49.0, last_refreshed_at=datetime(2024, 6, 1, 10, 0))
    now = datetime(2024, 6, 1, 20, 0)

    result = refresh_mood(mood, now, empty_calendar())

    assert result.value == 50.0


def test_refresh_mood_no_drift_on_first_refresh() -> None:
    mood = Mood(value=70.0, last_refreshed_at=None)
    now = datetime(2024, 6, 1, 12, 0)

    result = refresh_mood(mood, now, empty_calendar())

    assert result.value == 70.0


# --- refresh_mood: sleep boost ---


@patch("livingbot.mood.random.uniform", return_value=20.0)
def test_refresh_mood_applies_sleep_boost_in_morning_window(mock_uniform) -> None:
    mood = Mood(value=50.0, last_sleep_date=None)
    now = datetime(2024, 6, 1, 8, 0)

    result = refresh_mood(mood, now, empty_calendar())

    assert result.value == 70.0
    assert result.last_sleep_date == date(2024, 6, 1)


def test_refresh_mood_does_not_apply_sleep_boost_outside_morning_window() -> None:
    mood = Mood(value=50.0, last_sleep_date=None)
    now = datetime(2024, 6, 1, 14, 0)

    result = refresh_mood(mood, now, empty_calendar())

    assert result.last_sleep_date is None


def test_refresh_mood_does_not_apply_sleep_boost_twice_same_day() -> None:
    mood = Mood(value=50.0, last_sleep_date=date(2024, 6, 1))
    now = datetime(2024, 6, 1, 8, 30)

    result = refresh_mood(mood, now, empty_calendar())

    assert result.value == 50.0


@patch("livingbot.mood.random.uniform", return_value=20.0)
def test_refresh_mood_applies_sleep_boost_on_new_day(mock_uniform) -> None:
    mood = Mood(value=50.0, last_sleep_date=date(2024, 5, 31))
    now = datetime(2024, 6, 1, 8, 0)

    result = refresh_mood(mood, now, empty_calendar())

    assert result.value == 70.0
    assert result.last_sleep_date == date(2024, 6, 1)


# --- refresh_mood: gym boost ---


@patch("livingbot.mood.random.uniform", return_value=15.0)
def test_refresh_mood_applies_gym_boost_after_session_ends(mock_uniform) -> None:
    gym_end = datetime(2024, 6, 1, 19, 0)
    mood = Mood(value=50.0, last_gym_boost_at=None)
    now = datetime(2024, 6, 1, 19, 30)

    result = refresh_mood(mood, now, calendar_with_gym(gym_end))

    assert result.value == 65.0
    assert result.last_gym_boost_at == gym_end


def test_refresh_mood_does_not_apply_gym_boost_before_session_ends() -> None:
    gym_end = datetime(2024, 6, 1, 20, 0)
    mood = Mood(value=50.0, last_gym_boost_at=None)
    now = datetime(2024, 6, 1, 19, 0)

    result = refresh_mood(mood, now, calendar_with_gym(gym_end))

    assert result.last_gym_boost_at is None


def test_refresh_mood_does_not_apply_gym_boost_already_credited() -> None:
    gym_end = datetime(2024, 6, 1, 19, 0)
    mood = Mood(value=70.0, last_gym_boost_at=gym_end)
    now = datetime(2024, 6, 1, 20, 0)

    result = refresh_mood(mood, now, calendar_with_gym(gym_end))

    assert result.value == 70.0


def test_refresh_mood_updates_last_refreshed_at() -> None:
    mood = Mood(value=50.0)
    now = datetime(2024, 6, 1, 12, 0)

    result = refresh_mood(mood, now, empty_calendar())

    assert result.last_refreshed_at == now


# --- apply_interaction_delta ---


def test_apply_interaction_delta_positive_increases_mood() -> None:
    mood = Mood(value=50.0)

    result = apply_interaction_delta(mood, 10)

    assert result.value > 50.0


def test_apply_interaction_delta_negative_decreases_mood() -> None:
    mood = Mood(value=50.0)

    result = apply_interaction_delta(mood, -10)

    assert result.value < 50.0


def test_apply_interaction_delta_zero_leaves_mood_unchanged() -> None:
    mood = Mood(value=60.0)

    result = apply_interaction_delta(mood, 0)

    assert result.value == 60.0


def test_apply_interaction_delta_does_not_exceed_100() -> None:
    mood = Mood(value=98.0)

    result = apply_interaction_delta(mood, 10)

    assert result.value <= 100.0


def test_apply_interaction_delta_does_not_go_below_0() -> None:
    mood = Mood(value=2.0)

    result = apply_interaction_delta(mood, -10)

    assert result.value >= 0.0


@patch("livingbot.mood.random.uniform", return_value=8.0)
def test_apply_interaction_delta_large_positive_scales_to_max_boost(
    mock_uniform,
) -> None:
    mood = Mood(value=50.0)

    result = apply_interaction_delta(mood, 100)

    assert result.value == 58.0


@patch("livingbot.mood.random.uniform", return_value=10.0)
def test_apply_interaction_delta_large_negative_scales_to_max_drop(
    mock_uniform,
) -> None:
    mood = Mood(value=50.0)

    result = apply_interaction_delta(mood, -100)

    assert result.value == 40.0


# --- build_mood_block ---


def test_build_mood_block_includes_numeric_score() -> None:
    mood = Mood(value=72.0)
    now = datetime(2024, 6, 1, 15, 0)

    result = build_mood_block(mood, now)

    assert "72/100" in result


def test_build_mood_block_includes_gym_hint_when_recently_boosted() -> None:
    mood = Mood(value=80.0, last_gym_boost_at=datetime(2024, 6, 1, 13, 0))
    now = datetime(2024, 6, 1, 15, 0)  # 2 hours after gym

    result = build_mood_block(mood, now)

    assert "gym" in result.lower()


def test_build_mood_block_omits_gym_hint_when_boost_was_long_ago() -> None:
    mood = Mood(value=80.0, last_gym_boost_at=datetime(2024, 6, 1, 9, 0))
    now = datetime(2024, 6, 1, 15, 0)  # 6 hours after gym

    result = build_mood_block(mood, now)

    assert "gym" not in result.lower()


def test_build_mood_block_includes_sleep_hint_when_woke_up_today() -> None:
    mood = Mood(value=70.0, last_sleep_date=date(2024, 6, 1))
    now = datetime(2024, 6, 1, 10, 0)

    result = build_mood_block(mood, now)

    assert "refreshed" in result.lower()


def test_build_mood_block_omits_sleep_hint_in_afternoon() -> None:
    mood = Mood(value=70.0, last_sleep_date=date(2024, 6, 1))
    now = datetime(2024, 6, 1, 15, 0)

    result = build_mood_block(mood, now)

    assert "refreshed" not in result.lower()


def test_build_mood_block_gym_hint_takes_priority_over_sleep_hint() -> None:
    mood = Mood(
        value=80.0,
        last_gym_boost_at=datetime(2024, 6, 1, 9, 30),
        last_sleep_date=date(2024, 6, 1),
    )
    now = datetime(2024, 6, 1, 10, 0)

    result = build_mood_block(mood, now)

    assert "gym" in result.lower()
    assert "refreshed" not in result.lower()
