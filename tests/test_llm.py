from datetime import datetime, timedelta

from livingbot import config
from livingbot.calendar import Calendar, PlanEntry
from livingbot.commitments import Commitment
from livingbot.hobbies import Hobby, Hobbies
from livingbot.inventory import InventoryItem
from livingbot.llm import (
    _build_calendar_block,
    _build_commitments_block,
    _build_history_block,
    _build_inventory_block,
    _build_new_messages_block,
    _build_recent_block,
    _build_stories_block,
)
from livingbot.stories import Story

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


def test_build_inventory_block_directs_to_search_for_items_not_shown() -> None:
    item = InventoryItem(name="biała spódniczka")

    block = _build_inventory_block([item])

    assert "search_inventory" in block


def test_build_stories_block_marks_story_that_has_a_photo() -> None:
    story = Story(summary="Met a dog", content="c", image_path="data/x.jpg")

    block = _build_stories_block([story])

    assert "(has a photo)" in block


def test_build_stories_block_omits_photo_marker_when_no_image() -> None:
    story = Story(summary="Met a dog", content="c", image_path=None)

    block = _build_stories_block([story])

    assert "(has a photo)" not in block


def test_build_stories_block_mentions_show_story_image_tool() -> None:
    story = Story(summary="Met a dog", content="c", image_path="data/x.jpg")

    block = _build_stories_block([story])

    assert "show_story_image" in block


def test_build_recent_block_when_nothing_recent_returns_empty_string() -> None:
    hobbies = Hobbies(entries=[Hobby(name="gym")])

    block = _build_recent_block(hobbies, [], NOW)

    assert block == ""


def test_build_recent_block_includes_recently_acquired_hobby() -> None:
    hobby = Hobby(name="pottery", acquired_at=NOW - timedelta(days=2))
    hobbies = Hobbies(entries=[hobby])

    block = _build_recent_block(hobbies, [], NOW)

    assert "You took up pottery 2 days ago." in block


def test_build_recent_block_excludes_hobby_acquired_outside_window() -> None:
    hobby = Hobby(
        name="pottery",
        acquired_at=NOW - config.RECENT_HOBBY_WINDOW - timedelta(days=1),
    )
    hobbies = Hobbies(entries=[hobby])

    block = _build_recent_block(hobbies, [], NOW)

    assert block == ""


def test_build_recent_block_excludes_hobby_with_no_acquired_at() -> None:
    hobbies = Hobbies(entries=[Hobby(name="gym", acquired_at=None)])

    block = _build_recent_block(hobbies, [], NOW)

    assert block == ""


def test_build_recent_block_includes_recently_acquired_item() -> None:
    item = InventoryItem(name="sukienka", acquired_at=NOW - timedelta(days=1))

    block = _build_recent_block(Hobbies(), [item], NOW)

    assert "You got sukienka 1 day ago." in block


def test_build_recent_block_sorts_entries_newest_first() -> None:
    hobby = Hobby(name="pottery", acquired_at=NOW - timedelta(days=5))
    item = InventoryItem(name="sukienka", acquired_at=NOW - timedelta(days=1))
    hobbies = Hobbies(entries=[hobby])

    block = _build_recent_block(hobbies, [item], NOW)

    lines = block.strip().splitlines()
    assert "sukienka" in lines[1]
    assert "pottery" in lines[2]


def test_build_commitments_block_lists_promise_with_id_and_recipient() -> None:
    commitment = Commitment(
        user_id="42",
        channel_id=1,
        description="show a screenshot",
        due_hint="next time at her computer",
        made_at=NOW - timedelta(hours=3),
    )

    block = _build_commitments_block([commitment], NOW)

    assert f"[id:{commitment.id}]" in block
    assert "<@42>" in block
    assert "show a screenshot" in block
    assert "next time at her computer" in block


def test_build_commitments_block_mentions_resolve_commitment_tool() -> None:
    commitment = Commitment(
        user_id="42",
        channel_id=1,
        description="show a screenshot",
        due_hint="soon",
        made_at=NOW,
    )

    block = _build_commitments_block([commitment], NOW)

    assert "resolve_commitment" in block


def test_build_history_block_labels_it_as_earlier_conversation() -> None:
    block = _build_history_block(["[id:1] alice: hey", "[id:2] bob: yo"])

    assert block.startswith("Earlier in the conversation:\n")
    assert "[id:1] alice: hey" in block
    assert "[id:2] bob: yo" in block


def test_build_new_messages_block_labels_messages_to_respond_to() -> None:
    block = _build_new_messages_block(["[id:3] alice: are you there?"])

    assert block == "New message(s) to respond to:\n[id:3] alice: are you there?"
