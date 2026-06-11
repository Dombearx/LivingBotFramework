from datetime import date, timedelta
from unittest.mock import patch

from livingbot.spending import (
    POINTS_CAP,
    Purchase,
    SpendCategory,
    SpendingState,
    SpendingStore,
)

MONDAY = date(2026, 6, 1)
PREV_MONDAY = MONDAY - timedelta(weeks=1)
TWO_WEEKS_AGO = MONDAY - timedelta(weeks=2)


def make_store(tmp_path):
    return SpendingStore(tmp_path / "spending")


def write_state(tmp_path, state: SpendingState) -> None:
    path = tmp_path / "spending" / "spending.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(state.model_dump_json(indent=2))


def with_week(monday: date):
    return patch("livingbot.spending._current_week_start", return_value=monday)


# ---------------------------------------------------------------------------
# SpendingStore.load()
# ---------------------------------------------------------------------------


def test_load_on_first_call_creates_state_with_weekly_points(tmp_path) -> None:
    with with_week(MONDAY), patch("random.randint", return_value=4):
        state = make_store(tmp_path).load()

    assert state.week_start == MONDAY
    assert state.points_available == 4
    assert state.purchases == []


def test_load_with_current_week_returns_state_unchanged(tmp_path) -> None:
    write_state(
        tmp_path,
        SpendingState(week_start=MONDAY, points_available=3),
    )

    with with_week(MONDAY):
        state = make_store(tmp_path).load()

    assert state.week_start == MONDAY
    assert state.points_available == 3


def test_load_when_week_has_passed_adds_new_points_and_clears_purchases(
    tmp_path,
) -> None:
    old_purchase = Purchase(name="sukienka", category=SpendCategory.medium)
    write_state(
        tmp_path,
        SpendingState(
            week_start=PREV_MONDAY, points_available=1, purchases=[old_purchase]
        ),
    )

    with with_week(MONDAY), patch("random.randint", return_value=3):
        state = make_store(tmp_path).load()

    assert state.week_start == MONDAY
    assert state.points_available == 4  # 1 + 3
    assert state.purchases == []


def test_load_when_multiple_weeks_passed_accumulates_points_per_week(
    tmp_path,
) -> None:
    write_state(
        tmp_path,
        SpendingState(week_start=TWO_WEEKS_AGO, points_available=0),
    )

    with with_week(MONDAY), patch("random.randint", return_value=4):
        state = make_store(tmp_path).load()

    assert state.week_start == MONDAY
    assert state.points_available == 8  # 0 + 4 + 4


def test_load_when_rollover_exceeds_cap_clamps_to_cap(tmp_path) -> None:
    write_state(
        tmp_path,
        SpendingState(week_start=PREV_MONDAY, points_available=18),
    )

    with with_week(MONDAY), patch("random.randint", return_value=5):
        state = make_store(tmp_path).load()

    assert state.points_available == POINTS_CAP


# ---------------------------------------------------------------------------
# SpendingStore.save()
# ---------------------------------------------------------------------------


def test_save_persists_points_and_purchases(tmp_path) -> None:
    purchase = Purchase(name="sukienka", category=SpendCategory.medium)
    state = SpendingState(week_start=MONDAY, points_available=7, purchases=[purchase])

    make_store(tmp_path).save(state)

    with with_week(MONDAY):
        loaded = make_store(tmp_path).load()
    assert loaded.points_available == 7
    assert [p.name for p in loaded.purchases] == ["sukienka"]


# ---------------------------------------------------------------------------
# SpendingStore.can_afford()
# ---------------------------------------------------------------------------


def test_can_afford_when_points_sufficient_returns_true(tmp_path) -> None:
    write_state(tmp_path, SpendingState(week_start=MONDAY, points_available=4))

    with with_week(MONDAY):
        result = make_store(tmp_path).can_afford(SpendCategory.large)

    assert result is True


def test_can_afford_when_points_insufficient_returns_false(tmp_path) -> None:
    write_state(tmp_path, SpendingState(week_start=MONDAY, points_available=1))

    with with_week(MONDAY):
        result = make_store(tmp_path).can_afford(SpendCategory.medium)

    assert result is False


def test_can_afford_trivial_always_returns_true(tmp_path) -> None:
    write_state(tmp_path, SpendingState(week_start=MONDAY, points_available=0))

    with with_week(MONDAY):
        result = make_store(tmp_path).can_afford(SpendCategory.trivial)

    assert result is True


# ---------------------------------------------------------------------------
# SpendingStore.record()
# ---------------------------------------------------------------------------


def test_record_deducts_cost_from_points_available(tmp_path) -> None:
    write_state(tmp_path, SpendingState(week_start=MONDAY, points_available=4))

    with with_week(MONDAY):
        make_store(tmp_path).record("buty", SpendCategory.medium)
        state = make_store(tmp_path).load()

    assert state.points_available == 2  # 4 - 2


def test_record_when_cost_exceeds_points_clamps_to_zero(tmp_path) -> None:
    write_state(tmp_path, SpendingState(week_start=MONDAY, points_available=1))

    with with_week(MONDAY):
        make_store(tmp_path).record("wycieczka", SpendCategory.large)
        state = make_store(tmp_path).load()

    assert state.points_available == 0


def test_record_persists_purchase_in_state(tmp_path) -> None:
    write_state(tmp_path, SpendingState(week_start=MONDAY, points_available=4))

    with with_week(MONDAY):
        make_store(tmp_path).record("nowe buty do biegania", SpendCategory.medium)
        state = make_store(tmp_path).load()

    assert len(state.purchases) == 1
    assert state.purchases[0].name == "nowe buty do biegania"
    assert state.purchases[0].category == SpendCategory.medium


# ---------------------------------------------------------------------------
# SpendingStore.summary()
# ---------------------------------------------------------------------------


def test_summary_when_no_purchases_shows_only_points(tmp_path) -> None:
    write_state(tmp_path, SpendingState(week_start=MONDAY, points_available=4))

    with with_week(MONDAY):
        result = make_store(tmp_path).summary()

    assert "4" in result
    assert "bought" not in result


def test_summary_when_purchases_exist_lists_them(tmp_path) -> None:
    purchase = Purchase(name="sukienka", category=SpendCategory.medium)
    write_state(
        tmp_path,
        SpendingState(week_start=MONDAY, points_available=2, purchases=[purchase]),
    )

    with with_week(MONDAY):
        result = make_store(tmp_path).summary()

    assert "2" in result
    assert "sukienka" in result
