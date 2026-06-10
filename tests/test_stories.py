from datetime import date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from livingbot.stories import (
    RETIREMENT_PERIOD,
    STORY_TIERS,
    GeneratedStory,
    Story,
    StoryGenerator,
    StoryStore,
    StoryTier,
    _choose_tier,
)


@pytest.fixture
def story_store(tmp_path) -> StoryStore:
    return StoryStore.create(tmp_path / "stories")


def test_story_document_returns_summary() -> None:
    story = Story(summary="A funny incident at the gym", content="Full story here...")

    assert story.document() == "A funny incident at the gym"


async def test_story_store_add_and_untold_returns_added_story(
    story_store: StoryStore,
) -> None:
    story = Story(summary="First story", content="Content of first story")

    await story_store.add(story)
    result = await story_store.untold()

    assert len(result) == 1
    assert result[0].id == story.id
    assert result[0].summary == "First story"


async def test_story_store_untold_excludes_told_stories(
    story_store: StoryStore,
) -> None:
    untold = Story(summary="Not told yet", content="Content")
    told = Story(summary="Already told", content="Content")
    await story_store.add(untold)
    await story_store.add(told)
    await story_store.mark_told(told.id)

    result = await story_store.untold()

    assert len(result) == 1
    assert result[0].id == untold.id


async def test_story_store_untold_respects_limit(story_store: StoryStore) -> None:
    for i in range(5):
        await story_store.add(Story(summary=f"Story {i}", content=f"Content {i}"))

    result = await story_store.untold(limit=3)

    assert len(result) == 3


async def test_story_store_untold_sorted_oldest_first(story_store: StoryStore) -> None:
    earlier = Story(
        summary="Earlier story",
        content="Content",
        created_at=datetime(2026, 1, 1),
    )
    later = Story(
        summary="Later story",
        content="Content",
        created_at=datetime(2026, 6, 1),
    )
    await story_store.add(later)
    await story_store.add(earlier)

    result = await story_store.untold(limit=10)

    assert result[0].id == earlier.id
    assert result[1].id == later.id


async def test_story_store_mark_told_returns_true_and_excludes_from_untold(
    story_store: StoryStore,
) -> None:
    story = Story(summary="A story", content="Content")
    await story_store.add(story)

    success = await story_store.mark_told(story.id)
    remaining = await story_store.untold()

    assert success is True
    assert len(remaining) == 0


async def test_story_store_mark_told_returns_false_when_story_not_found(
    story_store: StoryStore,
) -> None:
    success = await story_store.mark_told("nonexistent_id")

    assert success is False


async def test_story_store_prune_stale_removes_stories_told_beyond_retirement_period(
    story_store: StoryStore,
) -> None:
    now = datetime.now()
    stale = Story(
        summary="Stale told story",
        content="This was told long ago",
        told_at=now - RETIREMENT_PERIOD - timedelta(days=1),
    )
    anchor = Story(summary="Anchor story", content="Keeps collection non-empty")
    await story_store.add(stale)
    await story_store.add(anchor)

    await story_store.prune_stale(now)

    results = await story_store.search("Stale told story", limit=5)
    assert not any(s.id == stale.id for s in results)


async def test_story_store_prune_stale_keeps_untold_stories(
    story_store: StoryStore,
) -> None:
    now = datetime.now()
    untold = Story(summary="Untold story", content="Content")
    await story_store.add(untold)

    await story_store.prune_stale(now)

    result = await story_store.untold(limit=100)
    assert any(s.id == untold.id for s in result)


async def test_story_store_prune_stale_keeps_recently_told_stories(
    story_store: StoryStore,
) -> None:
    now = datetime.now()
    recent = Story(
        summary="Recently told",
        content="Content",
        told_at=now - RETIREMENT_PERIOD + timedelta(days=1),
    )
    anchor = Story(summary="Anchor story", content="Content")
    await story_store.add(recent)
    await story_store.add(anchor)

    await story_store.prune_stale(now)

    results = await story_store.search("Recently told", limit=5)
    assert any(s.id == recent.id for s in results)


def test_story_has_happened_when_occurs_at_is_none_returns_true() -> None:
    story = Story(summary="s", content="c", occurs_at=None)

    assert story.has_happened(datetime(2026, 6, 1)) is True


def test_story_has_happened_when_occurs_at_in_past_returns_true() -> None:
    story = Story(summary="s", content="c", occurs_at=datetime(2026, 6, 1))

    assert story.has_happened(datetime(2026, 6, 2)) is True


def test_story_has_happened_when_occurs_at_in_future_returns_false() -> None:
    story = Story(summary="s", content="c", occurs_at=datetime(2026, 6, 3))

    assert story.has_happened(datetime(2026, 6, 2)) is False


async def test_story_store_untold_excludes_stories_not_yet_happened(
    story_store: StoryStore,
) -> None:
    future = Story(
        summary="Future story",
        content="Content",
        occurs_at=datetime.now() + timedelta(days=1),
    )
    await story_store.add(future)

    result = await story_store.untold()

    assert result == []


async def test_story_store_untold_includes_stories_already_happened(
    story_store: StoryStore,
) -> None:
    past = Story(
        summary="Past story",
        content="Content",
        occurs_at=datetime.now() - timedelta(days=1),
    )
    await story_store.add(past)

    result = await story_store.untold()

    assert [s.id for s in result] == [past.id]


async def test_story_store_search_excludes_stories_not_yet_happened(
    story_store: StoryStore,
) -> None:
    future = Story(
        summary="A surprising encounter",
        content="Content",
        occurs_at=datetime.now() + timedelta(days=1),
    )
    await story_store.add(future)

    results = await story_store.search("a surprising encounter", limit=5)

    assert all(s.id != future.id for s in results)


async def test_story_store_get_returns_story_by_id(story_store: StoryStore) -> None:
    story = Story(summary="Findable", content="Content")
    await story_store.add(story)

    result = await story_store.get(story.id)

    assert result is not None
    assert result.id == story.id


async def test_story_store_get_returns_none_when_id_unknown(
    story_store: StoryStore,
) -> None:
    result = await story_store.get("nonexistent_id")

    assert result is None


async def test_story_store_persists_image_path(story_store: StoryStore) -> None:
    story = Story(summary="With photo", content="Content", image_path="data/x.jpg")
    await story_store.add(story)

    result = await story_store.get(story.id)

    assert result.image_path == "data/x.jpg"


async def test_story_store_recent_summaries_returns_newest_first(
    story_store: StoryStore,
) -> None:
    older = Story(summary="Older", content="c", created_at=datetime(2026, 1, 1))
    newer = Story(summary="Newer", content="c", created_at=datetime(2026, 6, 1))
    await story_store.add(older)
    await story_store.add(newer)

    summaries = await story_store.recent_summaries(limit=10)

    assert summaries == ["Newer", "Older"]


async def test_story_store_recent_summaries_respects_limit(
    story_store: StoryStore,
) -> None:
    for i in range(5):
        await story_store.add(Story(summary=f"Story {i}", content="c"))

    summaries = await story_store.recent_summaries(limit=2)

    assert len(summaries) == 2


@patch("livingbot.stories.random.choices")
def test_choose_tier_weights_match_tier_weights(mock_choices: MagicMock) -> None:
    mock_choices.return_value = [STORY_TIERS[0]]

    _choose_tier()

    assert mock_choices.call_args.kwargs["weights"] == [75, 20, 5]


@patch("livingbot.stories.Agent")
async def test_story_generator_generate_returns_story_with_requested_occurs_at(
    mock_agent_cls: MagicMock,
) -> None:
    generator = StoryGenerator(MagicMock())
    generator._agent.run = AsyncMock(
        return_value=SimpleNamespace(
            output=GeneratedStory(summary="Met a dog", content="A friendly dog.")
        )
    )
    occurs_at = datetime(2026, 6, 4, 15, 0)

    story = await generator.generate(
        date(2026, 6, 1), ["gym"], "home", occurs_at, None, []
    )

    assert story.occurs_at == occurs_at
    assert story.summary == "Met a dog"
    assert story.content == "A friendly dog."


@patch("livingbot.stories._choose_tier")
@patch("livingbot.stories.Agent")
async def test_story_generator_generate_passes_avoid_summaries_in_prompt(
    mock_agent_cls: MagicMock, mock_choose_tier: MagicMock
) -> None:
    mock_choose_tier.return_value = StoryTier(name="normal", weight=75, guidance="g")
    generator = StoryGenerator(MagicMock())
    generator._agent.run = AsyncMock(
        return_value=SimpleNamespace(output=GeneratedStory(summary="s", content="c"))
    )

    await generator.generate(
        date(2026, 6, 1),
        ["gym"],
        "home",
        datetime(2026, 6, 4),
        None,
        ["Fell in a lake"],
    )

    prompt = generator._agent.run.call_args.args[0]
    assert "Fell in a lake" in prompt


@patch("livingbot.stories._choose_tier")
@patch("livingbot.stories.Agent")
async def test_story_generator_generate_passes_anchor_in_prompt(
    mock_agent_cls: MagicMock, mock_choose_tier: MagicMock
) -> None:
    mock_choose_tier.return_value = StoryTier(name="normal", weight=75, guidance="g")
    generator = StoryGenerator(MagicMock())
    generator._agent.run = AsyncMock(
        return_value=SimpleNamespace(output=GeneratedStory(summary="s", content="c"))
    )

    await generator.generate(
        date(2026, 6, 1),
        ["gym"],
        "home",
        datetime(2026, 6, 4),
        "gym session at gym",
        [],
    )

    prompt = generator._agent.run.call_args.args[0]
    assert "gym session at gym" in prompt


@patch("livingbot.stories.Agent")
async def test_story_generator_generate_returns_none_when_agent_fails(
    mock_agent_cls: MagicMock,
) -> None:
    generator = StoryGenerator(MagicMock())
    generator._agent.run = AsyncMock(side_effect=RuntimeError("model down"))

    story = await generator.generate(
        date(2026, 6, 1), ["gym"], "home", datetime(2026, 6, 4), None, []
    )

    assert story is None
