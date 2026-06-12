from datetime import datetime, timedelta

from livingbot.timeformat import humanize_ago

NOW = datetime(2026, 6, 12, 12, 0)


def test_humanize_ago_at_zero_seconds_returns_just_now() -> None:
    result = humanize_ago(NOW, NOW)

    assert result == "just now"


def test_humanize_ago_at_59_seconds_returns_just_now() -> None:
    result = humanize_ago(NOW - timedelta(seconds=59), NOW)

    assert result == "just now"


def test_humanize_ago_at_one_minute_returns_singular_minute() -> None:
    result = humanize_ago(NOW - timedelta(minutes=1), NOW)

    assert result == "1 minute ago"


def test_humanize_ago_at_two_minutes_returns_plural_minutes() -> None:
    result = humanize_ago(NOW - timedelta(minutes=2), NOW)

    assert result == "2 minutes ago"


def test_humanize_ago_at_59_minutes_returns_minutes_not_hours() -> None:
    result = humanize_ago(NOW - timedelta(minutes=59), NOW)

    assert result == "59 minutes ago"


def test_humanize_ago_at_one_hour_returns_singular_hour() -> None:
    result = humanize_ago(NOW - timedelta(hours=1), NOW)

    assert result == "1 hour ago"


def test_humanize_ago_at_two_hours_returns_plural_hours() -> None:
    result = humanize_ago(NOW - timedelta(hours=2), NOW)

    assert result == "2 hours ago"


def test_humanize_ago_at_23_hours_returns_hours_not_days() -> None:
    result = humanize_ago(NOW - timedelta(hours=23), NOW)

    assert result == "23 hours ago"


def test_humanize_ago_at_one_day_returns_singular_day() -> None:
    result = humanize_ago(NOW - timedelta(days=1), NOW)

    assert result == "1 day ago"


def test_humanize_ago_at_two_days_returns_plural_days() -> None:
    result = humanize_ago(NOW - timedelta(days=2), NOW)

    assert result == "2 days ago"


def test_humanize_ago_at_six_days_returns_days_not_weeks() -> None:
    result = humanize_ago(NOW - timedelta(days=6), NOW)

    assert result == "6 days ago"


def test_humanize_ago_at_seven_days_returns_singular_week() -> None:
    result = humanize_ago(NOW - timedelta(days=7), NOW)

    assert result == "1 week ago"


def test_humanize_ago_at_14_days_returns_plural_weeks() -> None:
    result = humanize_ago(NOW - timedelta(days=14), NOW)

    assert result == "2 weeks ago"


def test_humanize_ago_at_29_days_returns_weeks_not_months() -> None:
    result = humanize_ago(NOW - timedelta(days=29), NOW)

    assert result == "4 weeks ago"


def test_humanize_ago_at_30_days_returns_singular_month() -> None:
    result = humanize_ago(NOW - timedelta(days=30), NOW)

    assert result == "1 month ago"


def test_humanize_ago_at_60_days_returns_plural_months() -> None:
    result = humanize_ago(NOW - timedelta(days=60), NOW)

    assert result == "2 months ago"
