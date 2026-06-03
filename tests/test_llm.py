from datetime import datetime

from livingbot.calendar import Calendar, PlanEntry
from livingbot.inventory import InventoryItem
from livingbot.llm import _build_calendar_block, _build_inventory_block

NOW = datetime(2026, 6, 3, 14, 30)


def test_build_calendar_block_when_busy_reports_location_and_end_time() -> None:
    ongoing = PlanEntry(
        activity="gym session",
        location="gym",
        start=datetime(2026, 6, 3, 14, 0),
        end=datetime(2026, 6, 3, 16, 0),
    )
    calendar = Calendar(home_location="home", entries=[ongoing])

    block = _build_calendar_block(calendar, NOW)

    assert "gym" in block
    assert "until 16:00" in block


def test_build_calendar_block_when_free_reports_home_location() -> None:
    calendar = Calendar(home_location="home", entries=[])

    block = _build_calendar_block(calendar, NOW)

    assert "home" in block
    assert "nothing scheduled" in block


def test_build_calendar_block_lists_upcoming_entry_with_id() -> None:
    upcoming = PlanEntry(
        activity="trip",
        location="Zakopane",
        start=datetime(2026, 6, 5, 8, 0),
        end=datetime(2026, 6, 8, 20, 0),
    )
    calendar = Calendar(home_location="home", entries=[upcoming])

    block = _build_calendar_block(calendar, NOW)

    assert f"[id:{upcoming.id}]" in block
    assert "Zakopane" in block


def test_build_inventory_block_lists_owned_item_with_id_and_description() -> None:
    item = InventoryItem(name="biała spódniczka", description="w czerwone kropki")

    block = _build_inventory_block([item])

    assert f"[id:{item.id}]" in block
    assert "biała spódniczka" in block
    assert "w czerwone kropki" in block


def test_build_inventory_block_when_empty_notes_nothing_special() -> None:
    block = _build_inventory_block([])

    assert "nothing special yet" in block
