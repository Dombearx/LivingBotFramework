import pytest

from livingbot.spending import SpendingStore


@pytest.fixture
def spending_store(tmp_path) -> SpendingStore:
    return SpendingStore(tmp_path / "spending")
