from livingbot.relations import Relation, RelationStore


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
