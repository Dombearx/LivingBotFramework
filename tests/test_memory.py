from unittest.mock import MagicMock, patch

from livingbot.memory import MemoryStore

# ---------------------------------------------------------------------------
# MemoryStore.create
# ---------------------------------------------------------------------------


@patch.dict("os.environ", {"OPENROUTER_API_KEY": "test-router-key"})
@patch("livingbot.memory.Memory")
def test_create_points_embedder_at_openrouter_with_the_router_key(
    mock_memory_cls: MagicMock, tmp_path
) -> None:
    MemoryStore.create(tmp_path)

    config = mock_memory_cls.from_config.call_args.args[0]
    assert config["embedder"]["config"]["api_key"] == "test-router-key"
    assert (
        config["embedder"]["config"]["openai_base_url"]
        == "https://openrouter.ai/api/v1"
    )


@patch.dict("os.environ", {"OPENROUTER_API_KEY": "test-router-key"})
@patch("livingbot.memory.Memory")
def test_create_makes_the_data_path_directory(
    mock_memory_cls: MagicMock, tmp_path
) -> None:
    data_path = tmp_path / "memories"

    MemoryStore.create(data_path)

    assert data_path.is_dir()


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

    memory.get_all.assert_called_once_with(filters={"user_id": "222"})


async def test_delete_forwards_memory_id_to_backend() -> None:
    memory = MagicMock()
    store = MemoryStore(memory)

    await store.delete("abc123")

    memory.delete.assert_called_once_with("abc123")


async def test_retrieve_searches_each_message_against_its_author_and_global() -> None:
    memory = MagicMock()
    memory.search.return_value = {"results": []}
    store = MemoryStore(memory)

    await store.retrieve([("hello", "111")])

    memory.search.assert_any_call("hello", filters={"user_id": "111"}, top_k=3)
    memory.search.assert_any_call("hello", filters={"user_id": "global"}, top_k=3)


async def test_retrieve_interleaves_so_each_message_contributes() -> None:
    banks = {
        ("from a", "111"): {
            "results": [{"memory": "a1"}, {"memory": "a2"}, {"memory": "a3"}]
        },
        ("from b", "222"): {"results": [{"memory": "b1"}]},
    }
    memory = MagicMock()
    memory.search.side_effect = lambda query, filters, top_k: banks.get(
        (query, filters["user_id"]), {"results": []}
    )
    store = MemoryStore(memory)

    result = await store.retrieve([("from a", "111"), ("from b", "222")])

    assert result == ["a1", "b1", "a2", "a3"]


async def test_retrieve_dedups_memory_shared_by_author_and_global_bank() -> None:
    memory = MagicMock()
    memory.search.return_value = {"results": [{"memory": "likes tea"}]}
    store = MemoryStore(memory)

    result = await store.retrieve([("query", "111")])

    assert result == ["likes tea"]
