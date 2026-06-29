import pytest

from livingbot.activity_notes import ActivityNotesStore
from livingbot.hobbies import HobbyStore
from livingbot.spending import SpendingStore
from livingbot.stories import StoryStore


@pytest.fixture
def activity_notes_store(tmp_path) -> ActivityNotesStore:
    return ActivityNotesStore(tmp_path / "activity_notes")


@pytest.fixture
def spending_store(tmp_path) -> SpendingStore:
    return SpendingStore(tmp_path / "spending")


@pytest.fixture
def hobby_store(tmp_path) -> HobbyStore:
    return HobbyStore(tmp_path / "hobbies", default_hobbies=[])


@pytest.fixture
def story_store(tmp_path) -> StoryStore:
    return StoryStore.create(tmp_path / "stories")
