from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic_ai import ModelRetry

from livingbot.calendar import (
    Calendar,
    CalendarStore,
    PlanEntry,
    PlannedActivity,
    WeekPlan,
    WeekPlanner,
    _reject_unknown_hobbies,
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


def test_upcoming_excludes_past_and_sorts_by_start() -> None:
    past = entry(start=datetime(2026, 6, 2, 8, 0), end=datetime(2026, 6, 2, 9, 0))
    later = entry(start=datetime(2026, 6, 5, 18, 0), end=datetime(2026, 6, 5, 19, 0))
    sooner = entry(start=datetime(2026, 6, 4, 18, 0), end=datetime(2026, 6, 4, 19, 0))
    calendar = Calendar(home_location="home", entries=[past, later, sooner])

    result = calendar.upcoming(NOW)

    assert result == [sooner, later]


def test_prune_past_removes_entries_older_than_30_days_keeps_recent() -> None:
    old = entry(start=datetime(2026, 5, 1, 8, 0), end=datetime(2026, 5, 1, 9, 0))
    recent_finished = entry(
        start=datetime(2026, 6, 2, 8, 0), end=datetime(2026, 6, 2, 9, 0)
    )
    ongoing = entry(start=datetime(2026, 6, 3, 14, 0), end=datetime(2026, 6, 3, 16, 0))
    future = entry(start=datetime(2026, 6, 5, 18, 0), end=datetime(2026, 6, 5, 19, 0))
    calendar = Calendar(
        home_location="home", entries=[old, recent_finished, ongoing, future]
    )

    calendar.prune_past(NOW)

    assert calendar.entries == [recent_finished, ongoing, future]


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
async def test_week_planner_returns_empty_list_when_agent_raises(
    mock_agent_class: MagicMock,
) -> None:
    agent = mock_agent_class.return_value
    agent.run = AsyncMock(side_effect=RuntimeError("model error"))
    planner = WeekPlanner("openai:gpt-4o")

    result = await planner.plan(datetime(2026, 6, 1).date(), ["gym"], "home")

    assert result == []


@patch("livingbot.calendar.Agent")
async def test_week_planner_includes_new_hobbies_note_in_prompt(
    mock_agent_class: MagicMock,
) -> None:
    agent = mock_agent_class.return_value
    agent.run = AsyncMock(return_value=MagicMock(output=WeekPlan(activities=[])))
    planner = WeekPlanner("openai:gpt-4o")

    await planner.plan(
        datetime(2026, 6, 1).date(),
        ["gym", "pottery"],
        "home",
        ["pottery (took up 8 days ago)"],
    )

    prompt = agent.run.call_args.args[0]
    assert "pottery (took up 8 days ago)" in prompt


@patch("livingbot.calendar.Agent")
async def test_week_planner_without_new_hobbies_omits_recent_mention(
    mock_agent_class: MagicMock,
) -> None:
    agent = mock_agent_class.return_value
    agent.run = AsyncMock(return_value=MagicMock(output=WeekPlan(activities=[])))
    planner = WeekPlanner("openai:gpt-4o")

    await planner.plan(datetime(2026, 6, 1).date(), ["gym"], "home")

    prompt = agent.run.call_args.args[0]
    assert "recently took up" not in prompt


@patch("livingbot.calendar.Agent")
async def test_week_planner_passes_hobbies_as_deps(
    mock_agent_class: MagicMock,
) -> None:
    agent = mock_agent_class.return_value
    agent.run = AsyncMock(return_value=MagicMock(output=WeekPlan(activities=[])))
    planner = WeekPlanner("openai:gpt-4o")

    await planner.plan(datetime(2026, 6, 1).date(), ["gym", "pottery"], "home")

    assert agent.run.call_args.kwargs["deps"] == ["gym", "pottery"]


def planned(activity: str = "gym session", hobby: str = "") -> PlannedActivity:
    return PlannedActivity(
        activity=activity,
        location="gym",
        start=datetime(2026, 6, 4, 18, 0),
        end=datetime(2026, 6, 4, 19, 30),
        hobby=hobby,
    )


def test_reject_unknown_hobbies_raises_when_hobby_is_not_hers() -> None:
    plan = WeekPlan(activities=[planned(hobby="Gym")])

    with pytest.raises(ModelRetry):
        _reject_unknown_hobbies(MagicMock(deps=["gym"]), plan)


def test_reject_unknown_hobbies_retry_message_names_her_actual_hobbies() -> None:
    plan = WeekPlan(activities=[planned(hobby="Gym")])

    with pytest.raises(ModelRetry) as error:
        _reject_unknown_hobbies(MagicMock(deps=["gym", "pottery"]), plan)

    assert "gym, pottery" in str(error.value)


def test_reject_unknown_hobbies_returns_plan_when_every_hobby_is_hers() -> None:
    plan = WeekPlan(activities=[planned(hobby="gym")])

    result = _reject_unknown_hobbies(MagicMock(deps=["gym"]), plan)

    assert result is plan


def test_reject_unknown_hobbies_allows_activities_with_no_hobby() -> None:
    plan = WeekPlan(activities=[planned(activity="groceries", hobby="")])

    result = _reject_unknown_hobbies(MagicMock(deps=["gym"]), plan)

    assert result is plan
