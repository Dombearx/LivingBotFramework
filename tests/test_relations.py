from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel

from livingbot.relations import (
    _ATTITUDE_BEHAVIOURS,
    _ATTITUDE_TOP,
    Relation,
    RelationStore,
    RelationUpdate,
    RelationUpdater,
    apply_attitude_delta,
    apply_update,
    attitude_behaviour,
)


def test_relation_store_all_returns_empty_when_no_relations(tmp_path) -> None:
    store = RelationStore(tmp_path / "relations")

    result = store.all()

    assert result == []


def test_relation_store_all_returns_every_saved_relation(tmp_path) -> None:
    store = RelationStore(tmp_path / "relations")
    store.save(Relation(user_id="111", attitude=10))
    store.save(Relation(user_id="222", attitude=-5))

    result = store.all()

    assert {r.user_id for r in result} == {"111", "222"}


def test_relation_store_all_loads_persisted_fields(tmp_path) -> None:
    store = RelationStore(tmp_path / "relations")
    store.save(Relation(user_id="111", attitude=42, inside_jokes=["banana"]))

    result = store.all()

    assert result[0].attitude == 42
    assert result[0].inside_jokes == ["banana"]


def test_relation_loads_integer_attitude_written_before_the_float_change() -> None:
    stored = '{"user_id": "111", "attitude": 70}'

    relation = Relation.model_validate_json(stored)

    assert relation.attitude == 70.0


def test_apply_attitude_delta_when_delta_is_zero_leaves_attitude_unchanged() -> None:
    result = apply_attitude_delta(37.5, 0)

    assert result == 37.5


def test_apply_attitude_delta_scales_positive_delta_down_by_the_gain() -> None:
    result = apply_attitude_delta(0.0, 2)

    assert result == pytest.approx(0.7)


def test_apply_attitude_delta_damps_positive_delta_as_attitude_rises() -> None:
    result = apply_attitude_delta(60.0, 2)

    assert result == pytest.approx(60.28)


def test_apply_attitude_delta_applies_negative_delta_at_full_weight() -> None:
    result = apply_attitude_delta(20.0, -5)

    assert result == 15.0


def test_apply_attitude_delta_does_not_amplify_gain_while_attitude_is_negative() -> (
    None
):
    result = apply_attitude_delta(-40.0, 2)

    assert result == pytest.approx(-39.3)


def test_apply_attitude_delta_clamps_at_the_hostile_floor() -> None:
    result = apply_attitude_delta(-95.0, -10)

    assert result == -100.0


def test_apply_update_without_a_new_memory_keeps_the_stored_one() -> None:
    relation = Relation(user_id="111", most_important_memory="won a chess tournament")
    update = RelationUpdate(attitude_delta=0, reason="just floated playing a game")

    result = apply_update(relation, update)

    assert result.most_important_memory == "won a chess tournament"


def test_apply_update_with_a_new_memory_replaces_the_stored_one() -> None:
    relation = Relation(user_id="111", most_important_memory="won a chess tournament")
    update = RelationUpdate(
        attitude_delta=0,
        reason="ordinary chat",
        new_most_important_memory="moved to Wroclaw for university",
    )

    result = apply_update(relation, update)

    assert result.most_important_memory == "moved to Wroclaw for university"


def test_apply_update_appends_a_new_inside_joke() -> None:
    relation = Relation(user_id="111", inside_jokes=["the exploding blender"])
    update = RelationUpdate(
        attitude_delta=0, reason="ordinary chat", new_inside_joke="the protein goblin"
    )

    result = apply_update(relation, update)

    assert result.inside_jokes == ["the exploding blender", "the protein goblin"]


def test_apply_update_does_not_append_an_inside_joke_that_is_already_stored() -> None:
    relation = Relation(user_id="111", inside_jokes=["the exploding blender"])
    update = RelationUpdate(
        attitude_delta=0,
        reason="ordinary chat",
        new_inside_joke="the exploding blender",
    )

    result = apply_update(relation, update)

    assert result.inside_jokes == ["the exploding blender"]


def test_apply_update_drops_the_inside_jokes_marked_for_removal() -> None:
    relation = Relation(
        user_id="111",
        inside_jokes=["the exploding blender", "you always say that"],
    )
    update = RelationUpdate(
        attitude_delta=0,
        reason="ordinary chat",
        remove_inside_jokes=["you always say that"],
    )

    result = apply_update(relation, update)

    assert result.inside_jokes == ["the exploding blender"]


def test_apply_update_keeps_the_newest_five_inside_jokes() -> None:
    relation = Relation(
        user_id="111", inside_jokes=["one", "two", "three", "four", "five"]
    )
    update = RelationUpdate(
        attitude_delta=0, reason="ordinary chat", new_inside_joke="six"
    )

    result = apply_update(relation, update)

    assert result.inside_jokes == ["two", "three", "four", "five", "six"]


def test_apply_update_appends_only_topics_that_are_not_already_stored() -> None:
    relation = Relation(user_id="111", topics_of_interest=["muzyka"])
    update = RelationUpdate(
        attitude_delta=0,
        reason="ordinary chat",
        new_topics_of_interest=["muzyka", "wspinaczka"],
    )

    result = apply_update(relation, update)

    assert result.topics_of_interest == ["muzyka", "wspinaczka"]


def test_apply_update_records_the_reason_when_attitude_moved() -> None:
    relation = Relation(user_id="111")
    update = RelationUpdate(attitude_delta=2, reason="asked about her training")

    result = apply_update(relation, update)

    assert result.last_attitude_reason == "asked about her training"


def test_apply_update_keeps_the_previous_reason_when_attitude_did_not_move() -> None:
    relation = Relation(user_id="111", last_attitude_reason="asked about her training")
    update = RelationUpdate(attitude_delta=0, reason="nothing notable")

    result = apply_update(relation, update)

    assert result.last_attitude_reason == "asked about her training"


@patch.object(Agent, "run", new_callable=AsyncMock)
async def test_relation_updater_puts_mugdas_interests_in_the_prompt(
    mock_run: AsyncMock,
) -> None:
    mock_run.return_value = MagicMock(
        output=RelationUpdate(attitude_delta=0, reason="ordinary chat")
    )
    updater = RelationUpdater(TestModel())

    await updater.update(
        Relation(user_id="111"),
        [{"role": "user", "content": "hej"}],
        ["gym", "horror films: loves them"],
    )

    prompt = mock_run.call_args.args[0]
    assert "- gym\n- horror films: loves them" in prompt


@patch.object(Agent, "run", new_callable=AsyncMock, side_effect=RuntimeError("boom"))
async def test_relation_updater_returns_none_when_the_model_call_fails(
    mock_run: AsyncMock,
) -> None:
    updater = RelationUpdater(TestModel())

    result = await updater.update(
        Relation(user_id="111"), [{"role": "user", "content": "hej"}], ["gym"]
    )

    assert result is None


def test_attitude_behaviour_at_the_default_starting_attitude_is_the_newcomer_band() -> (
    None
):
    result = attitude_behaviour(4.0)

    assert result == _ATTITUDE_BEHAVIOURS[4][1]


def test_attitude_behaviour_at_a_band_threshold_returns_the_band_above_it() -> None:
    threshold = _ATTITUDE_BEHAVIOURS[4][0]

    result = attitude_behaviour(threshold)

    assert result == _ATTITUDE_BEHAVIOURS[5][1]


def test_attitude_behaviour_at_the_hostile_floor_is_the_lowest_band() -> None:
    result = attitude_behaviour(-100.0)

    assert result == _ATTITUDE_BEHAVIOURS[0][1]


def test_attitude_behaviour_above_the_highest_threshold_is_the_top_band() -> None:
    result = attitude_behaviour(100.0)

    assert result == _ATTITUDE_TOP


def test_attitude_behaviour_bands_are_ordered_by_ascending_threshold() -> None:
    thresholds = [threshold for threshold, _ in _ATTITUDE_BEHAVIOURS]

    assert thresholds == sorted(thresholds)
