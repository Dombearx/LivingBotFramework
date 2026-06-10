from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from livingbot.calendar import Calendar, CalendarStore, PlanEntry
from livingbot.hobbies import Hobbies
from livingbot.inventory import InventoryItem
from datetime import date

from livingbot.spending import SpendCategory, SpendingState
from livingbot.tools import (
    BotDeps,
    add_item,
    add_plan,
    buy_item,
    check_budget,
    remove_item,
    remove_plan,
    search_inventory,
    show_story_image,
    take_photo,
)
from livingbot.stories import Story


def make_spending_store() -> MagicMock:
    store = MagicMock()
    store.can_afford = MagicMock(return_value=True)
    store.record = MagicMock()
    store.load = MagicMock()
    return store


def make_ctx(
    calendar_store: CalendarStore | None = None,
    inventory_store: MagicMock | None = None,
    spending_store: MagicMock | None = None,
    hobby_store: MagicMock | None = None,
    story_store: MagicMock | None = None,
) -> SimpleNamespace:
    deps = BotDeps(
        channel=MagicMock(),
        calendar_store=calendar_store or MagicMock(),
        inventory_store=inventory_store or make_inventory_store(),
        spending_store=spending_store or make_spending_store(),
        hobby_store=hobby_store or make_hobby_store(),
        story_store=story_store or make_story_store(),
    )
    return SimpleNamespace(deps=deps)


def make_inventory_store() -> MagicMock:
    store = MagicMock()
    store.add = AsyncMock()
    store.remove = AsyncMock(return_value=True)
    store.search = AsyncMock(return_value=[])
    return store


def make_hobby_store() -> MagicMock:
    store = MagicMock()
    store.load = MagicMock(return_value=Hobbies())
    store.save = MagicMock()
    return store


def make_story_store() -> MagicMock:
    store = MagicMock()
    store.search = AsyncMock(return_value=[])
    store.mark_told = AsyncMock(return_value=True)
    return store


async def test_add_plan_appends_entry_to_calendar(tmp_path) -> None:
    store = CalendarStore(tmp_path, home_location="home")
    ctx = make_ctx(store)

    await add_plan(
        ctx,
        activity="trip to Zakopane",
        location="Zakopane",
        start=datetime(2026, 6, 5, 8, 0),
        end=datetime(2026, 6, 8, 20, 0),
    )

    entries = store.load().entries
    assert len(entries) == 1
    assert entries[0].activity == "trip to Zakopane"
    assert entries[0].location == "Zakopane"


async def test_add_plan_returns_id_of_new_entry(tmp_path) -> None:
    store = CalendarStore(tmp_path, home_location="home")
    ctx = make_ctx(store)

    result = await add_plan(
        ctx,
        activity="gym",
        location="gym",
        start=datetime(2026, 6, 4, 18, 0),
        end=datetime(2026, 6, 4, 19, 30),
    )

    new_id = store.load().entries[0].id
    assert new_id in result


async def test_remove_plan_deletes_matching_entry(tmp_path) -> None:
    store = CalendarStore(tmp_path, home_location="home")
    existing = PlanEntry(
        activity="gym",
        location="gym",
        start=datetime(2026, 6, 4, 18, 0),
        end=datetime(2026, 6, 4, 19, 30),
    )
    store.save(Calendar(home_location="home", entries=[existing]))
    ctx = make_ctx(store)

    await remove_plan(ctx, existing.id)

    assert store.load().entries == []


async def test_remove_plan_when_id_missing_keeps_entries(tmp_path) -> None:
    store = CalendarStore(tmp_path, home_location="home")
    existing = PlanEntry(
        activity="gym",
        location="gym",
        start=datetime(2026, 6, 4, 18, 0),
        end=datetime(2026, 6, 4, 19, 30),
    )
    store.save(Calendar(home_location="home", entries=[existing]))
    ctx = make_ctx(store)

    result = await remove_plan(ctx, "missing-id")

    assert store.load().entries == [existing]
    assert "No calendar entry" in result


async def test_add_item_stores_item_in_inventory() -> None:
    store = make_inventory_store()
    ctx = make_ctx(inventory_store=store)

    await add_item(
        ctx,
        name="biała spódniczka w czerwone kropki",
        description="krótka, letnia",
    )

    stored = store.add.call_args.args[0]
    assert stored.name == "biała spódniczka w czerwone kropki"
    assert stored.description == "krótka, letnia"


async def test_add_item_returns_id_of_new_item() -> None:
    store = make_inventory_store()
    ctx = make_ctx(inventory_store=store)

    result = await add_item(ctx, name="strój kąpielowy")

    stored = store.add.call_args.args[0]
    assert stored.id in result


async def test_remove_item_when_present_confirms_removal() -> None:
    store = make_inventory_store()
    store.remove = AsyncMock(return_value=True)
    ctx = make_ctx(inventory_store=store)

    result = await remove_item(ctx, "abc123")

    store.remove.assert_awaited_once_with("abc123")
    assert "Removed item abc123" in result


async def test_remove_item_when_id_missing_reports_not_found() -> None:
    store = make_inventory_store()
    store.remove = AsyncMock(return_value=False)
    ctx = make_ctx(inventory_store=store)

    result = await remove_item(ctx, "missing")

    assert "No inventory item with id missing" in result


async def test_search_inventory_returns_matching_items_with_ids() -> None:
    item = InventoryItem(
        name="strój kąpielowy", description="niebieski, jednoczęściowy"
    )
    store = make_inventory_store()
    store.search = AsyncMock(return_value=[item])
    ctx = make_ctx(inventory_store=store)

    result = await search_inventory(ctx, query="coś na basen")

    assert f"[id:{item.id}]" in result
    assert "strój kąpielowy" in result


async def test_search_inventory_when_empty_reports_empty_inventory() -> None:
    store = make_inventory_store()
    store.search = AsyncMock(return_value=[])
    ctx = make_ctx(inventory_store=store)

    result = await search_inventory(ctx, query="cokolwiek")

    assert result == "Your inventory is empty."


# ---------------------------------------------------------------------------
# check_budget
# ---------------------------------------------------------------------------


async def test_check_budget_when_affordable_returns_can_afford_message() -> None:
    spending = make_spending_store()
    spending.load = MagicMock(
        return_value=SpendingState(week_start=date(2026, 6, 1), points_available=4)
    )
    ctx = make_ctx(spending_store=spending)

    result = await check_budget(ctx, SpendCategory.large)

    assert "can afford" in result.lower()
    assert "4" in result


async def test_check_budget_when_unaffordable_returns_cant_afford_message() -> None:
    spending = make_spending_store()
    spending.load = MagicMock(
        return_value=SpendingState(week_start=date(2026, 6, 1), points_available=1)
    )
    ctx = make_ctx(spending_store=spending)

    result = await check_budget(ctx, SpendCategory.large)

    assert "can't afford" in result.lower()
    assert "1" in result


# ---------------------------------------------------------------------------
# buy_item
# ---------------------------------------------------------------------------


async def test_buy_item_when_affordable_records_spend_and_adds_to_inventory() -> None:
    spending = make_spending_store()
    spending.can_afford = MagicMock(return_value=True)
    inventory = make_inventory_store()
    ctx = make_ctx(spending_store=spending, inventory_store=inventory)

    await buy_item(ctx, name="sukienka letnia", category=SpendCategory.medium)

    spending.record.assert_called_once_with("sukienka letnia", SpendCategory.medium)
    inventory.add.assert_awaited_once()


async def test_buy_item_when_affordable_returns_confirmation_with_item_id() -> None:
    spending = make_spending_store()
    spending.can_afford = MagicMock(return_value=True)
    inventory = make_inventory_store()
    ctx = make_ctx(spending_store=spending, inventory_store=inventory)

    result = await buy_item(ctx, name="sukienka letnia", category=SpendCategory.medium)

    stored = inventory.add.call_args.args[0]
    assert stored.id in result
    assert "sukienka letnia" in result


async def test_buy_item_when_unaffordable_returns_refusal() -> None:
    spending = make_spending_store()
    spending.can_afford = MagicMock(return_value=False)
    spending.load = MagicMock(
        return_value=SpendingState(week_start=date(2026, 6, 1), points_available=1)
    )
    ctx = make_ctx(spending_store=spending)

    result = await buy_item(ctx, name="wyjazd górski", category=SpendCategory.large)

    assert "can't buy" in result.lower()
    assert "wyjazd górski" in result


async def test_buy_item_when_unaffordable_does_not_add_to_inventory() -> None:
    spending = make_spending_store()
    spending.can_afford = MagicMock(return_value=False)
    spending.load = MagicMock(
        return_value=SpendingState(week_start=date(2026, 6, 1), points_available=0)
    )
    inventory = make_inventory_store()
    ctx = make_ctx(spending_store=spending, inventory_store=inventory)

    await buy_item(ctx, name="wyjazd górski", category=SpendCategory.large)

    inventory.add.assert_not_awaited()


# ---------------------------------------------------------------------------
# take_photo
# ---------------------------------------------------------------------------


def make_photo_ctx() -> SimpleNamespace:
    deps = BotDeps(
        channel=MagicMock(),
        calendar_store=MagicMock(),
        inventory_store=make_inventory_store(),
        spending_store=make_spending_store(),
        hobby_store=make_hobby_store(),
        story_store=make_story_store(),
    )
    return SimpleNamespace(deps=deps)


@patch(
    "livingbot.image.generate_image",
    new_callable=AsyncMock,
    return_value=b"image-bytes",
)
async def test_take_photo_stores_image_bytes_in_deps(mock_gen: AsyncMock) -> None:
    ctx = make_photo_ctx()

    await take_photo(ctx, description="at the gym", include_mugda=True)

    assert ctx.deps.photo_result == b"image-bytes"


@patch(
    "livingbot.image.generate_image",
    new_callable=AsyncMock,
    return_value=b"image-bytes",
)
async def test_take_photo_returns_confirmation_message(mock_gen: AsyncMock) -> None:
    ctx = make_photo_ctx()

    result = await take_photo(ctx, description="sunny park", include_mugda=False)

    assert "ready" in result.lower()


@patch(
    "livingbot.image.generate_image",
    new_callable=AsyncMock,
    return_value=b"image-bytes",
)
async def test_take_photo_passes_description_and_include_mugda_to_generate_image(
    mock_gen: AsyncMock,
) -> None:
    ctx = make_photo_ctx()

    await take_photo(ctx, description="beach at sunset", include_mugda=True)

    mock_gen.assert_awaited_once()
    call_kwargs = mock_gen.call_args.kwargs
    assert call_kwargs["description"] == "beach at sunset"
    assert call_kwargs["include_mugda"] is True


@patch(
    "livingbot.image.generate_image",
    new_callable=AsyncMock,
    return_value=b"image-bytes",
)
async def test_take_photo_passes_outfit_description_to_generate_image(
    mock_gen: AsyncMock,
) -> None:
    ctx = make_photo_ctx()

    await take_photo(
        ctx,
        description="at the gym",
        include_mugda=True,
        outfit_description="black sports bra, grey leggings",
    )

    assert (
        mock_gen.call_args.kwargs["outfit_description"]
        == "black sports bra, grey leggings"
    )


@patch(
    "livingbot.image.generate_image",
    new_callable=AsyncMock,
    return_value=b"image-bytes",
)
async def test_take_photo_default_outfit_description_is_empty(
    mock_gen: AsyncMock,
) -> None:
    ctx = make_photo_ctx()

    await take_photo(ctx, description="a park", include_mugda=False)

    assert mock_gen.call_args.kwargs["outfit_description"] == ""


@patch(
    "livingbot.image.generate_image",
    new_callable=AsyncMock,
    side_effect=RuntimeError("endpoint down"),
)
async def test_take_photo_when_generation_fails_returns_error_message(
    mock_gen: AsyncMock,
) -> None:
    ctx = make_photo_ctx()

    result = await take_photo(ctx, description="a park", include_mugda=False)

    assert "failed" in result.lower()


@patch(
    "livingbot.image.generate_image",
    new_callable=AsyncMock,
    side_effect=RuntimeError("endpoint down"),
)
async def test_take_photo_when_generation_fails_photo_result_stays_none(
    mock_gen: AsyncMock,
) -> None:
    ctx = make_photo_ctx()

    await take_photo(ctx, description="a park", include_mugda=False)

    assert ctx.deps.photo_result is None


# ---------------------------------------------------------------------------
# show_story_image
# ---------------------------------------------------------------------------


def make_story_image_ctx(story: Story | None) -> SimpleNamespace:
    story_store = MagicMock()
    story_store.get = AsyncMock(return_value=story)
    deps = BotDeps(
        channel=MagicMock(),
        calendar_store=MagicMock(),
        inventory_store=make_inventory_store(),
        spending_store=make_spending_store(),
        hobby_store=make_hobby_store(),
        story_store=story_store,
    )
    return SimpleNamespace(deps=deps)


async def test_show_story_image_attaches_image_bytes(tmp_path) -> None:
    image_file = tmp_path / "story.jpg"
    image_file.write_bytes(b"story-image")
    story = Story(summary="s", content="c", image_path=str(image_file))
    ctx = make_story_image_ctx(story)

    await show_story_image(ctx, story.id)

    assert ctx.deps.photo_result == b"story-image"


async def test_show_story_image_when_story_unknown_returns_message(tmp_path) -> None:
    ctx = make_story_image_ctx(None)

    result = await show_story_image(ctx, "nope")

    assert "no story" in result.lower()
    assert ctx.deps.photo_result is None


async def test_show_story_image_when_story_has_no_image_returns_message() -> None:
    story = Story(summary="s", content="c", image_path=None)
    ctx = make_story_image_ctx(story)

    result = await show_story_image(ctx, story.id)

    assert "no photo" in result.lower()
    assert ctx.deps.photo_result is None


async def test_show_story_image_when_file_missing_returns_message(tmp_path) -> None:
    story = Story(summary="s", content="c", image_path=str(tmp_path / "gone.jpg"))
    ctx = make_story_image_ctx(story)

    result = await show_story_image(ctx, story.id)

    assert "missing" in result.lower()
    assert ctx.deps.photo_result is None
