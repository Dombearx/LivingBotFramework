from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

from livingbot.calendar import Calendar, CalendarStore, PlanEntry
from livingbot.tools import BotDeps, add_plan, remove_plan


def make_ctx(store: CalendarStore) -> SimpleNamespace:
    deps = BotDeps(channel=MagicMock(), calendar_store=store)
    return SimpleNamespace(deps=deps)


async def test_add_plan_appends_entry_to_calendar(tmp_path) -> None:
    store = CalendarStore(tmp_path, home_location="home")
    ctx = make_ctx(store)

    await add_plan(
        ctx,
        activity="trip to Zakopane",
        location="Zakopane",
        start=datetime(2026, 6, 5, 8, 0),
        end=datetime(2026, 6, 8, 20, 0),
    )

    entries = store.load().entries
    assert len(entries) == 1
    assert entries[0].activity == "trip to Zakopane"
    assert entries[0].location == "Zakopane"


async def test_add_plan_returns_id_of_new_entry(tmp_path) -> None:
    store = CalendarStore(tmp_path, home_location="home")
    ctx = make_ctx(store)

    result = await add_plan(
        ctx,
        activity="gym",
        location="gym",
        start=datetime(2026, 6, 4, 18, 0),
        end=datetime(2026, 6, 4, 19, 30),
    )

    new_id = store.load().entries[0].id
    assert new_id in result


async def test_remove_plan_deletes_matching_entry(tmp_path) -> None:
    store = CalendarStore(tmp_path, home_location="home")
    existing = PlanEntry(
        activity="gym",
        location="gym",
        start=datetime(2026, 6, 4, 18, 0),
        end=datetime(2026, 6, 4, 19, 30),
    )
    store.save(Calendar(home_location="home", entries=[existing]))
    ctx = make_ctx(store)

    await remove_plan(ctx, existing.id)

    assert store.load().entries == []


async def test_remove_plan_when_id_missing_keeps_entries(tmp_path) -> None:
    store = CalendarStore(tmp_path, home_location="home")
    existing = PlanEntry(
        activity="gym",
        location="gym",
        start=datetime(2026, 6, 4, 18, 0),
        end=datetime(2026, 6, 4, 19, 30),
    )
    store.save(Calendar(home_location="home", entries=[existing]))
    ctx = make_ctx(store)

    result = await remove_plan(ctx, "missing-id")

    assert store.load().entries == [existing]
    assert "No calendar entry" in result
