from datetime import datetime
from pathlib import Path

from livingbot.activity_notes import (
    ActivityNote,
    ActivityNotes,
    ActivityNotesStore,
    merge_note,
)
from livingbot.calendar import PlanEntry


def _entry(activity: str = "gym session", hobby: str = "gym") -> PlanEntry:
    return PlanEntry(
        activity=activity,
        location="gym",
        start=datetime(2026, 6, 8, 18, 0),
        end=datetime(2026, 6, 8, 19, 30),
        hobby=hobby,
    )


def test_matches_when_activity_equals_entry_hobby_ignoring_case_returns_true() -> None:
    note = ActivityNote(activity="Gym", note="bring dumbbells")
    entry = _entry(activity="evening workout", hobby="gym")

    result = note.matches(entry)

    assert result is True


def test_matches_when_activity_is_substring_of_entry_activity_returns_true() -> None:
    note = ActivityNote(activity="gym", note="bring dumbbells")
    entry = _entry(activity="Gym session with Kasia", hobby="")

    result = note.matches(entry)

    assert result is True


def test_matches_when_activity_unrelated_to_entry_returns_false() -> None:
    note = ActivityNote(activity="pool", note="bring goggles")
    entry = _entry(activity="gym session", hobby="gym")

    result = note.matches(entry)

    assert result is False


def test_apply_to_when_note_matches_sets_entry_note() -> None:
    notes = ActivityNotes(
        entries=[ActivityNote(activity="gym", note="bring dumbbells")]
    )
    entry = _entry()

    notes.apply_to(entry)

    assert entry.note == "bring dumbbells"


def test_apply_to_when_entry_already_has_note_appends_without_duplicating() -> None:
    notes = ActivityNotes(
        entries=[ActivityNote(activity="gym", note="bring dumbbells")]
    )
    entry = _entry()
    entry.note = "leave early"

    notes.apply_to(entry)

    assert entry.note == "leave early; bring dumbbells"


def test_apply_to_when_called_twice_does_not_duplicate_note() -> None:
    notes = ActivityNotes(
        entries=[ActivityNote(activity="gym", note="bring dumbbells")]
    )
    entry = _entry()

    notes.apply_to(entry)
    notes.apply_to(entry)

    assert entry.note == "bring dumbbells"


def test_apply_to_when_note_does_not_match_leaves_entry_note_empty() -> None:
    notes = ActivityNotes(entries=[ActivityNote(activity="pool", note="bring goggles")])
    entry = _entry()

    notes.apply_to(entry)

    assert entry.note == ""


def test_merge_note_when_existing_empty_returns_addition() -> None:
    result = merge_note("", "bring dumbbells")

    assert result == "bring dumbbells"


def test_merge_note_when_addition_already_present_returns_existing_unchanged() -> None:
    result = merge_note("bring dumbbells", "bring dumbbells")

    assert result == "bring dumbbells"


def test_store_save_then_load_round_trips_notes(tmp_path: Path) -> None:
    store = ActivityNotesStore(tmp_path)
    notes = ActivityNotes(
        entries=[ActivityNote(activity="gym", note="bring dumbbells")]
    )

    store.save(notes)
    loaded = store.load()

    assert loaded.entries[0].note == "bring dumbbells"


def test_store_load_when_file_absent_returns_empty_notes(tmp_path: Path) -> None:
    store = ActivityNotesStore(tmp_path)

    loaded = store.load()

    assert loaded.entries == []
