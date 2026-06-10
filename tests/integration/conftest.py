import pytest

from livingbot.hobbies import HobbyStore
from livingbot.spending import SpendingStore
from livingbot.stories import StoryStore


@pytest.fixture
def spending_store(tmp_path) -> SpendingStore:
    return SpendingStore(tmp_path / "spending")


@pytest.fixture
def hobby_store(tmp_path) -> HobbyStore:
    return HobbyStore(tmp_path / "hobbies", default_hobbies=[])


@pytest.fixture
def story_store(tmp_path) -> StoryStore:
    return StoryStore.create(tmp_path / "stories")
