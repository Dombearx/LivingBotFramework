from datetime import datetime
from unittest.mock import MagicMock

from livingbot.inventory import InventoryItem, InventoryStore


def make_store() -> tuple[InventoryStore, MagicMock]:
    collection = MagicMock()
    return InventoryStore(collection), collection


def test_document_combines_name_and_description_for_embedding() -> None:
    item = InventoryItem(name="strój kąpielowy", description="niebieski jednoczęściowy")

    document = item.document()

    assert document == "strój kąpielowy. niebieski jednoczęściowy"


def test_document_is_name_only_when_description_empty() -> None:
    item = InventoryItem(name="strój kąpielowy")

    document = item.document()

    assert document == "strój kąpielowy"


async def test_add_upserts_item_with_datetimes_serialized_to_isoformat() -> None:
    store, collection = make_store()
    item = InventoryItem(
        id="abc123",
        name="biała spódniczka",
        description="w czerwone kropki",
        acquired_at=datetime(2026, 6, 1, 12, 0),
        last_used_at=datetime(2026, 6, 2, 9, 0),
    )

    await store.add(item)

    collection.upsert.assert_called_once_with(
        ids=["abc123"],
        documents=["biała spódniczka. w czerwone kropki"],
        metadatas=[
            {
                "name": "biała spódniczka",
                "description": "w czerwone kropki",
                "acquired_at": "2026-06-01T12:00:00",
                "last_used_at": "2026-06-02T09:00:00",
            }
        ],
    )


async def test_all_returns_items_sorted_by_acquired_at() -> None:
    store, collection = make_store()
    collection.get.return_value = {
        "ids": ["newer", "older"],
        "metadatas": [
            {
                "name": "kozaki",
                "description": "",
                "acquired_at": "2026-06-02T10:00:00",
                "last_used_at": "2026-06-02T10:00:00",
            },
            {
                "name": "szalik",
                "description": "",
                "acquired_at": "2026-06-01T10:00:00",
                "last_used_at": "2026-06-01T10:00:00",
            },
        ],
    }

    items = await store.all()

    assert [item.name for item in items] == ["szalik", "kozaki"]


async def test_recent_returns_most_recently_used_items_capped_to_limit() -> None:
    store, collection = make_store()
    collection.get.return_value = {
        "ids": ["a", "b", "c"],
        "metadatas": [
            {
                "name": "szalik",
                "description": "",
                "acquired_at": "2026-06-01T10:00:00",
                "last_used_at": "2026-06-01T10:00:00",
            },
            {
                "name": "kozaki",
                "description": "",
                "acquired_at": "2026-06-01T10:00:00",
                "last_used_at": "2026-06-03T10:00:00",
            },
            {
                "name": "torebka",
                "description": "",
                "acquired_at": "2026-06-01T10:00:00",
                "last_used_at": "2026-06-02T10:00:00",
            },
        ],
    }

    items = await store.recent(2)

    assert [item.name for item in items] == ["kozaki", "torebka"]


async def test_recently_acquired_returns_items_since_cutoff_sorted_newest_first() -> (
    None
):
    store, collection = make_store()
    collection.get.return_value = {
        "ids": ["old", "newer", "newest"],
        "metadatas": [
            {
                "name": "stara torebka",
                "description": "",
                "acquired_at": "2026-05-01T10:00:00",
                "last_used_at": "2026-05-01T10:00:00",
            },
            {
                "name": "szalik",
                "description": "",
                "acquired_at": "2026-06-02T10:00:00",
                "last_used_at": "2026-06-02T10:00:00",
            },
            {
                "name": "sukienka",
                "description": "",
                "acquired_at": "2026-06-03T10:00:00",
                "last_used_at": "2026-06-03T10:00:00",
            },
        ],
    }

    items = await store.recently_acquired(since=datetime(2026, 6, 1))

    assert [item.name for item in items] == ["sukienka", "szalik"]


async def test_recently_acquired_respects_limit() -> None:
    store, collection = make_store()
    collection.get.return_value = {
        "ids": ["a", "b", "c"],
        "metadatas": [
            {
                "name": "item1",
                "description": "",
                "acquired_at": "2026-06-01T10:00:00",
                "last_used_at": "2026-06-01T10:00:00",
            },
            {
                "name": "item2",
                "description": "",
                "acquired_at": "2026-06-02T10:00:00",
                "last_used_at": "2026-06-02T10:00:00",
            },
            {
                "name": "item3",
                "description": "",
                "acquired_at": "2026-06-03T10:00:00",
                "last_used_at": "2026-06-03T10:00:00",
            },
        ],
    }

    items = await store.recently_acquired(since=datetime(2026, 5, 1), limit=2)

    assert len(items) == 2


async def test_remove_returns_false_when_item_absent() -> None:
    store, collection = make_store()
    collection.get.return_value = {"ids": []}

    removed = await store.remove("missing")

    assert removed is False
    collection.delete.assert_not_called()


async def test_remove_deletes_and_returns_true_when_item_present() -> None:
    store, collection = make_store()
    collection.get.return_value = {"ids": ["abc123"]}

    removed = await store.remove("abc123")

    assert removed is True
    collection.delete.assert_called_once_with(ids=["abc123"])


async def test_search_maps_query_results_to_items() -> None:
    store, collection = make_store()
    collection.query.return_value = {
        "ids": [["abc123"]],
        "metadatas": [
            [
                {
                    "name": "strój kąpielowy",
                    "description": "niebieski",
                    "acquired_at": "2026-06-01T10:00:00",
                    "last_used_at": "2026-06-01T10:00:00",
                }
            ]
        ],
    }

    items = await store.search("coś na basen")

    assert len(items) == 1
    assert items[0].name == "strój kąpielowy"


async def test_search_bumps_last_used_at_of_returned_items() -> None:
    store, collection = make_store()
    collection.query.return_value = {
        "ids": [["abc123"]],
        "metadatas": [
            [
                {
                    "name": "strój kąpielowy",
                    "description": "niebieski",
                    "acquired_at": "2026-06-01T10:00:00",
                    "last_used_at": "2026-06-01T10:00:00",
                }
            ]
        ],
    }

    items = await store.search("coś na basen")

    collection.update.assert_called_once()
    assert collection.update.call_args.kwargs["ids"] == ["abc123"]
    assert items[0].last_used_at > datetime(2026, 6, 1, 10, 0)
