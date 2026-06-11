from unittest.mock import MagicMock

from livingbot.memory import MemoryStore


async def test_all_returns_results_list_when_get_all_returns_dict() -> None:
    memory = MagicMock()
    memory.get_all.return_value = {"results": [{"id": "1", "memory": "likes tea"}]}
    store = MemoryStore(memory)

    result = await store.all("global")

    assert result == [{"id": "1", "memory": "likes tea"}]


async def test_all_returns_list_unchanged_when_get_all_returns_list() -> None:
    memory = MagicMock()
    memory.get_all.return_value = [{"id": "1", "memory": "likes tea"}]
    store = MemoryStore(memory)

    result = await store.all("global")

    assert result == [{"id": "1", "memory": "likes tea"}]


async def test_all_queries_the_requested_user_bank() -> None:
    memory = MagicMock()
    memory.get_all.return_value = {"results": []}
    store = MemoryStore(memory)

    await store.all("222")

    memory.get_all.assert_called_once_with(user_id="222")


async def test_delete_forwards_memory_id_to_backend() -> None:
    memory = MagicMock()
    store = MemoryStore(memory)

    await store.delete("abc123")

    memory.delete.assert_called_once_with("abc123")
