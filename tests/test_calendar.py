from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from livingbot.calendar import (
    Busyness,
    Calendar,
    CalendarStore,
    PlanEntry,
    PlannedActivity,
    WeekPlan,
    WeekPlanner,
)

NOW = datetime(2026, 6, 3, 14, 30)


def entry(
    activity: str = "gym",
    location: str = "gym",
    start: datetime = datetime(2026, 6, 3, 14, 0),
    end: datetime = datetime(2026, 6, 3, 16, 0),
) -> PlanEntry:
    return PlanEntry(activity=activity, location=location, start=start, end=end)


def test_current_entry_returns_entry_covering_now() -> None:
    ongoing = entry(start=datetime(2026, 6, 3, 14, 0), end=datetime(2026, 6, 3, 16, 0))
    calendar = Calendar(home_location="home", entries=[ongoing])

    result = calendar.current_entry(NOW)

    assert result == ongoing


def test_current_entry_when_nothing_covers_now_returns_none() -> None:
    past = entry(start=datetime(2026, 6, 3, 8, 0), end=datetime(2026, 6, 3, 9, 0))
    calendar = Calendar(home_location="home", entries=[past])

    result = calendar.current_entry(NOW)

    assert result is None


def test_current_entry_when_entries_overlap_returns_latest_start() -> None:
    broad = entry(
        activity="trip",
        location="Zakopane",
        start=datetime(2026, 6, 1, 0, 0),
        end=datetime(2026, 6, 5, 0, 0),
    )
    specific = entry(start=datetime(2026, 6, 3, 14, 0), end=datetime(2026, 6, 3, 16, 0))
    calendar = Calendar(home_location="home", entries=[broad, specific])

    result = calendar.current_entry(NOW)

    assert result == specific


def test_current_location_returns_entry_location_when_busy() -> None:
    calendar = Calendar(home_location="home", entries=[entry(location="gym")])

    assert calendar.current_location(NOW) == "gym"


def test_current_location_returns_home_when_free() -> None:
    calendar = Calendar(home_location="home", entries=[])

    assert calendar.current_location(NOW) == "home"


def test_upcoming_excludes_past_and_sorts_by_start() -> None:
    past = entry(start=datetime(2026, 6, 2, 8, 0), end=datetime(2026, 6, 2, 9, 0))
    later = entry(start=datetime(2026, 6, 5, 18, 0), end=datetime(2026, 6, 5, 19, 0))
    sooner = entry(start=datetime(2026, 6, 4, 18, 0), end=datetime(2026, 6, 4, 19, 0))
    calendar = Calendar(home_location="home", entries=[past, later, sooner])

    result = calendar.upcoming(NOW)

    assert result == [sooner, later]


def test_prune_past_removes_finished_keeps_ongoing_and_future() -> None:
    finished = entry(start=datetime(2026, 6, 2, 8, 0), end=datetime(2026, 6, 2, 9, 0))
    ongoing = entry(start=datetime(2026, 6, 3, 14, 0), end=datetime(2026, 6, 3, 16, 0))
    future = entry(start=datetime(2026, 6, 5, 18, 0), end=datetime(2026, 6, 5, 19, 0))
    calendar = Calendar(home_location="home", entries=[finished, ongoing, future])

    calendar.prune_past(NOW)

    assert calendar.entries == [ongoing, future]


def test_plan_entry_generates_distinct_ids() -> None:
    first = entry()
    second = entry()

    assert first.id != second.id


def test_calendar_store_load_when_file_missing_returns_default_home(
    tmp_path,
) -> None:
    store = CalendarStore(tmp_path, home_location="Warsaw flat")

    calendar = store.load()

    assert calendar.home_location == "Warsaw flat"
    assert calendar.entries == []


def test_calendar_store_round_trips_entries(tmp_path) -> None:
    store = CalendarStore(tmp_path, home_location="home")
    saved = Calendar(home_location="home", entries=[entry(activity="gym")])
    store.save(saved)

    loaded = CalendarStore(tmp_path, home_location="home").load()

    assert loaded.entries == saved.entries


def test_plan_entry_defaults_to_moderate_busyness() -> None:
    assert entry().busyness == Busyness.moderate


def test_calendar_store_round_trips_busyness(tmp_path) -> None:
    store = CalendarStore(tmp_path, home_location="home")
    deep = PlanEntry(
        activity="gym",
        location="gym",
        start=datetime(2026, 6, 3, 18, 0),
        end=datetime(2026, 6, 3, 19, 30),
        busyness=Busyness.deep,
    )
    store.save(Calendar(home_location="home", entries=[deep]))

    loaded = CalendarStore(tmp_path, home_location="home").load()

    assert loaded.entries[0].busyness == Busyness.deep


def test_entry_without_busyness_field_defaults_to_moderate() -> None:
    raw = (
        '{"home_location":"home","entries":[{"id":"x","activity":"a",'
        '"location":"l","start":"2026-06-03T10:00:00","end":"2026-06-03T11:00:00"}]}'
    )

    calendar = Calendar.model_validate_json(raw)

    assert calendar.entries[0].busyness == Busyness.moderate


@patch("livingbot.calendar.Agent")
async def test_week_planner_converts_activities_to_entries(
    mock_agent_class: MagicMock,
) -> None:
    activity = PlannedActivity(
        activity="gym",
        location="gym",
        start=datetime(2026, 6, 4, 18, 0),
        end=datetime(2026, 6, 4, 19, 30),
    )
    agent = mock_agent_class.return_value
    agent.run = AsyncMock(
        return_value=MagicMock(output=WeekPlan(activities=[activity]))
    )
    planner = WeekPlanner("openai:gpt-4o")

    result = await planner.plan(datetime(2026, 6, 1).date(), ["gym"], "home")

    assert len(result) == 1
    assert result[0].activity == "gym"
    assert result[0].start == datetime(2026, 6, 4, 18, 0)


@patch("livingbot.calendar.Agent")
async def test_week_planner_carries_busyness_from_activity(
    mock_agent_class: MagicMock,
) -> None:
    activity = PlannedActivity(
        activity="gym",
        location="gym",
        start=datetime(2026, 6, 4, 18, 0),
        end=datetime(2026, 6, 4, 19, 30),
        busyness=Busyness.deep,
    )
    agent = mock_agent_class.return_value
    agent.run = AsyncMock(
        return_value=MagicMock(output=WeekPlan(activities=[activity]))
    )
    planner = WeekPlanner("openai:gpt-4o")

    result = await planner.plan(datetime(2026, 6, 1).date(), ["gym"], "home")

    assert result[0].busyness == Busyness.deep


@patch("livingbot.calendar.Agent")
async def test_week_planner_returns_empty_list_when_agent_raises(
    mock_agent_class: MagicMock,
) -> None:
    agent = mock_agent_class.return_value
    agent.run = AsyncMock(side_effect=RuntimeError("model error"))
    planner = WeekPlanner("openai:gpt-4o")

    result = await planner.plan(datetime(2026, 6, 1).date(), ["gym"], "home")

    assert result == []
