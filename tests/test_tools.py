from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from livingbot.calendar import Calendar, CalendarStore, PlanEntry
from livingbot.inventory import InventoryItem
from livingbot.tools import (
    BotDeps,
    add_item,
    add_plan,
    remove_item,
    remove_plan,
    search_inventory,
)


def make_spending_store() -> MagicMock:
    store = MagicMock()
    store.can_afford = MagicMock(return_value=True)
    store.record = MagicMock()
    store.load = MagicMock()
    return store


def make_ctx(
    calendar_store: CalendarStore | None = None,
    inventory_store: MagicMock | None = None,
    spending_store: MagicMock | None = None,
) -> SimpleNamespace:
    deps = BotDeps(
        channel=MagicMock(),
        calendar_store=calendar_store or MagicMock(),
        inventory_store=inventory_store or make_inventory_store(),
        spending_store=spending_store or make_spending_store(),
    )
    return SimpleNamespace(deps=deps)


def make_inventory_store() -> MagicMock:
    store = MagicMock()
    store.add = AsyncMock()
    store.remove = AsyncMock(return_value=True)
    store.search = AsyncMock(return_value=[])
    return store


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


async def test_add_item_stores_item_in_inventory() -> None:
    store = make_inventory_store()
    ctx = make_ctx(inventory_store=store)

    await add_item(
        ctx,
        name="biała spódniczka w czerwone kropki",
        description="krótka, letnia",
    )

    stored = store.add.call_args.args[0]
    assert stored.name == "biała spódniczka w czerwone kropki"
    assert stored.description == "krótka, letnia"


async def test_add_item_returns_id_of_new_item() -> None:
    store = make_inventory_store()
    ctx = make_ctx(inventory_store=store)

    result = await add_item(ctx, name="strój kąpielowy")

    stored = store.add.call_args.args[0]
    assert stored.id in result


async def test_remove_item_when_present_confirms_removal() -> None:
    store = make_inventory_store()
    store.remove = AsyncMock(return_value=True)
    ctx = make_ctx(inventory_store=store)

    result = await remove_item(ctx, "abc123")

    store.remove.assert_awaited_once_with("abc123")
    assert "Removed item abc123" in result


async def test_remove_item_when_id_missing_reports_not_found() -> None:
    store = make_inventory_store()
    store.remove = AsyncMock(return_value=False)
    ctx = make_ctx(inventory_store=store)

    result = await remove_item(ctx, "missing")

    assert "No inventory item with id missing" in result


async def test_search_inventory_returns_matching_items_with_ids() -> None:
    item = InventoryItem(
        name="strój kąpielowy", description="niebieski, jednoczęściowy"
    )
    store = make_inventory_store()
    store.search = AsyncMock(return_value=[item])
    ctx = make_ctx(inventory_store=store)

    result = await search_inventory(ctx, query="coś na basen")

    assert f"[id:{item.id}]" in result
    assert "strój kąpielowy" in result


async def test_search_inventory_when_empty_reports_empty_inventory() -> None:
    store = make_inventory_store()
    store.search = AsyncMock(return_value=[])
    ctx = make_ctx(inventory_store=store)

    result = await search_inventory(ctx, query="cokolwiek")

    assert result == "Your inventory is empty."
