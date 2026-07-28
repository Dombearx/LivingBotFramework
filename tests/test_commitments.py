from datetime import datetime
from pathlib import Path

from livingbot.commitments import Commitment, Commitments, CommitmentStore


def _commitment(status: str = "open") -> Commitment:
    return Commitment(
        user_id="42",
        channel_id=1,
        description="show a screenshot",
        due_hint="next time at her computer",
        made_at=datetime(2026, 6, 1, 12, 0),
        status=status,
    )


def test_open_entries_includes_only_open_commitments() -> None:
    open_commitment = _commitment(status="open")
    fulfilled_commitment = _commitment(status="fulfilled")
    commitments = Commitments(entries=[open_commitment, fulfilled_commitment])

    result = commitments.open_entries()

    assert result == [open_commitment]


def test_open_entries_when_none_open_returns_empty_list() -> None:
    commitments = Commitments(entries=[_commitment(status="fulfilled")])

    result = commitments.open_entries()

    assert result == []


def test_store_save_then_load_round_trips_commitments(tmp_path: Path) -> None:
    store = CommitmentStore(tmp_path)
    commitments = Commitments(entries=[_commitment()])

    store.save(commitments)
    loaded = store.load()

    assert loaded.entries[0].description == "show a screenshot"
    assert loaded.entries[0].user_id == "42"


def test_store_load_when_file_absent_returns_empty_commitments(tmp_path: Path) -> None:
    store = CommitmentStore(tmp_path)

    loaded = store.load()

    assert loaded.entries == []


def test_commitment_id_defaults_to_a_generated_value() -> None:
    first = _commitment()
    second = _commitment()

    assert first.id != second.id


def test_commitment_nudged_at_defaults_to_none() -> None:
    commitment = _commitment()

    assert commitment.nudged_at is None
