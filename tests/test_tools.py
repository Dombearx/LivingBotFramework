from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import httpx

from livingbot import config
from livingbot.activity_notes import ActivityNotesStore
from livingbot.calendar import Calendar, CalendarStore, PlanEntry
from livingbot.commitments import CommitmentStore
from livingbot.hobbies import Hobbies, Hobby, HobbyLevel
from livingbot.inventory import InventoryItem
from datetime import date

from livingbot.spending import SpendCategory, SpendingState
from livingbot.tools import (
    MAX_ARTICLE_CHARS,
    MAX_EMBED_IMAGE_BYTES,
    MAX_LINK_PREVIEW_LENGTH,
    BotDeps,
    add_activity_note,
    add_commitment,
    add_hobby,
    add_item,
    add_plan,
    buy_item,
    check_budget,
    extract_images,
    fetch_link,
    format_message,
    ignore_message,
    message_images,
    react_to_message,
    recent_message_images,
    remove_activity_note,
    remove_item,
    remove_plan,
    resolve_commitment,
    search_inventory,
    show_story_image,
    take_photo,
)
from livingbot.directory import Directory
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
        channel_id=1,
        calendar_store=calendar_store or MagicMock(),
        activity_notes_store=MagicMock(),
        inventory_store=inventory_store or make_inventory_store(),
        spending_store=spending_store or make_spending_store(),
        hobby_store=hobby_store or make_hobby_store(),
        story_store=story_store or make_story_store(),
        preference_store=MagicMock(),
        commitment_store=MagicMock(),
    )
    return SimpleNamespace(deps=deps)


def make_inventory_store() -> MagicMock:
    store = MagicMock()
    store.add = AsyncMock()
    store.remove = AsyncMock(return_value=True)
    store.search = AsyncMock(return_value=[])
    return store


def make_hobby_store(hobbies: Hobbies | None = None) -> MagicMock:
    store = MagicMock()
    store.load = MagicMock(return_value=hobbies if hobbies is not None else Hobbies())
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


def make_photo_ctx(hobby_store: MagicMock | None = None) -> SimpleNamespace:
    deps = BotDeps(
        channel=MagicMock(),
        channel_id=1,
        calendar_store=MagicMock(),
        activity_notes_store=MagicMock(),
        inventory_store=make_inventory_store(),
        spending_store=make_spending_store(),
        hobby_store=hobby_store or make_hobby_store(),
        story_store=make_story_store(),
        preference_store=MagicMock(),
        commitment_store=MagicMock(),
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
        channel_id=1,
        calendar_store=MagicMock(),
        activity_notes_store=MagicMock(),
        inventory_store=make_inventory_store(),
        spending_store=make_spending_store(),
        hobby_store=make_hobby_store(),
        story_store=story_store,
        preference_store=MagicMock(),
        commitment_store=MagicMock(),
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


# ---------------------------------------------------------------------------
# add_hobby
# ---------------------------------------------------------------------------


@patch("livingbot.tools.clock")
async def test_add_hobby_when_new_saves_hobby_with_acquired_at_now(
    mock_clock: MagicMock,
) -> None:
    now = datetime(2026, 6, 12, 12, 0)
    mock_clock.now.return_value = now
    store = make_hobby_store()
    store.load = MagicMock(return_value=Hobbies(entries=[]))
    ctx = make_ctx(hobby_store=store)

    result = await add_hobby(ctx, "pottery")

    saved = store.save.call_args.args[0]
    assert saved.entries[0].name == "pottery"
    assert saved.entries[0].acquired_at == now
    assert result == "Added pottery to your hobbies."


async def test_add_hobby_when_already_present_returns_message_without_saving() -> None:
    store = make_hobby_store()
    store.load = MagicMock(return_value=Hobbies(entries=[Hobby(name="gym")]))
    ctx = make_ctx(hobby_store=store)

    result = await add_hobby(ctx, "gym")

    assert result == "gym is already one of your hobbies."
    store.save.assert_not_called()


@patch("livingbot.tools.clock")
async def test_add_hobby_within_cooldown_returns_refusal_naming_hobby_and_time(
    mock_clock: MagicMock,
) -> None:
    now = datetime(2026, 6, 12, 12, 0)
    mock_clock.now.return_value = now
    store = make_hobby_store()
    store.load = MagicMock(
        return_value=Hobbies(
            entries=[Hobby(name="pottery", acquired_at=now - timedelta(days=3))]
        )
    )
    ctx = make_ctx(hobby_store=store)

    result = await add_hobby(ctx, "painting")

    assert result == (
        "You took up pottery 3 days ago — it's too soon to take "
        "up something new. Give it a couple of weeks before adding another hobby."
    )


@patch("livingbot.tools.clock")
async def test_add_hobby_within_cooldown_does_not_save(
    mock_clock: MagicMock,
) -> None:
    now = datetime(2026, 6, 12, 12, 0)
    mock_clock.now.return_value = now
    store = make_hobby_store()
    store.load = MagicMock(
        return_value=Hobbies(
            entries=[Hobby(name="pottery", acquired_at=now - timedelta(days=3))]
        )
    )
    ctx = make_ctx(hobby_store=store)

    await add_hobby(ctx, "painting")

    store.save.assert_not_called()


@patch("livingbot.tools.clock")
async def test_add_hobby_after_cooldown_elapsed_adds_new_hobby(
    mock_clock: MagicMock,
) -> None:
    now = datetime(2026, 6, 12, 12, 0)
    mock_clock.now.return_value = now
    store = make_hobby_store()
    store.load = MagicMock(
        return_value=Hobbies(
            entries=[
                Hobby(
                    name="pottery",
                    acquired_at=now - config.HOBBY_COOLDOWN - timedelta(days=1),
                )
            ]
        )
    )
    ctx = make_ctx(hobby_store=store)

    result = await add_hobby(ctx, "painting")

    assert result == "Added painting to your hobbies."
    saved = store.save.call_args.args[0]
    assert [h.name for h in saved.entries] == ["pottery", "painting"]


@patch("livingbot.tools.clock")
async def test_add_hobby_when_existing_hobbies_have_no_acquired_at_ignores_cooldown(
    mock_clock: MagicMock,
) -> None:
    now = datetime(2026, 6, 12, 12, 0)
    mock_clock.now.return_value = now
    store = make_hobby_store()
    store.load = MagicMock(return_value=Hobbies(entries=[Hobby(name="gym")]))
    ctx = make_ctx(hobby_store=store)

    result = await add_hobby(ctx, "pottery")

    assert result == "Added pottery to your hobbies."


def make_activity_ctx(tmp_path) -> SimpleNamespace:
    return SimpleNamespace(
        deps=BotDeps(
            channel=MagicMock(),
            channel_id=1,
            calendar_store=CalendarStore(tmp_path / "calendar", home_location="home"),
            activity_notes_store=ActivityNotesStore(tmp_path / "activity_notes"),
            inventory_store=make_inventory_store(),
            spending_store=make_spending_store(),
            hobby_store=make_hobby_store(),
            story_store=make_story_store(),
            preference_store=MagicMock(),
            commitment_store=MagicMock(),
        )
    )


def _future_gym_entry() -> PlanEntry:
    return PlanEntry(
        activity="gym session",
        location="gym",
        start=datetime(2099, 1, 1, 18, 0),
        end=datetime(2099, 1, 1, 19, 0),
        hobby="gym",
    )


async def test_add_activity_note_persists_note_to_store(tmp_path) -> None:
    ctx = make_activity_ctx(tmp_path)

    await add_activity_note(ctx, "gym", "bring dumbbells")

    saved = ctx.deps.activity_notes_store.load()
    assert saved.entries[0].note == "bring dumbbells"


async def test_add_activity_note_stamps_matching_upcoming_calendar_entry(
    tmp_path,
) -> None:
    ctx = make_activity_ctx(tmp_path)
    ctx.deps.calendar_store.save(
        Calendar(home_location="home", entries=[_future_gym_entry()])
    )

    await add_activity_note(ctx, "gym", "bring dumbbells")

    stamped = ctx.deps.calendar_store.load().entries[0]
    assert stamped.note == "bring dumbbells"


async def test_add_activity_note_reports_number_of_stamped_plans(tmp_path) -> None:
    ctx = make_activity_ctx(tmp_path)
    ctx.deps.calendar_store.save(
        Calendar(home_location="home", entries=[_future_gym_entry()])
    )

    result = await add_activity_note(ctx, "gym", "bring dumbbells")

    assert "Attached it to 1 upcoming plan(s)." in result


async def test_remove_activity_note_when_present_removes_it_from_store(
    tmp_path,
) -> None:
    ctx = make_activity_ctx(tmp_path)
    await add_activity_note(ctx, "gym", "bring dumbbells")
    note_id = ctx.deps.activity_notes_store.load().entries[0].id

    await remove_activity_note(ctx, note_id)

    assert ctx.deps.activity_notes_store.load().entries == []


async def test_remove_activity_note_when_id_missing_returns_not_found(tmp_path) -> None:
    ctx = make_activity_ctx(tmp_path)

    result = await remove_activity_note(ctx, "nope1234")

    assert result == "No activity reminder with id nope1234."


# ---------------------------------------------------------------------------
# add_commitment / resolve_commitment
# ---------------------------------------------------------------------------


def make_commitment_ctx(tmp_path) -> SimpleNamespace:
    return SimpleNamespace(
        deps=BotDeps(
            channel=MagicMock(),
            channel_id=555,
            calendar_store=MagicMock(),
            activity_notes_store=MagicMock(),
            inventory_store=make_inventory_store(),
            spending_store=make_spending_store(),
            hobby_store=make_hobby_store(),
            story_store=make_story_store(),
            preference_store=MagicMock(),
            commitment_store=CommitmentStore(tmp_path / "commitments"),
            directory=Directory({"42": "Kuba"}),
        )
    )


async def test_add_commitment_persists_promise_to_store(tmp_path) -> None:
    ctx = make_commitment_ctx(tmp_path)

    await add_commitment(ctx, "Kuba", "show a screenshot", "next time at her computer")

    saved = ctx.deps.commitment_store.load().entries[0]
    assert saved.user_id == "42"
    assert saved.description == "show a screenshot"
    assert saved.due_hint == "next time at her computer"


async def test_add_commitment_stamps_channel_from_deps(tmp_path) -> None:
    ctx = make_commitment_ctx(tmp_path)

    await add_commitment(ctx, "Kuba", "show a screenshot", "soon")

    saved = ctx.deps.commitment_store.load().entries[0]
    assert saved.channel_id == 555


async def test_add_commitment_defaults_to_open_status(tmp_path) -> None:
    ctx = make_commitment_ctx(tmp_path)

    await add_commitment(ctx, "Kuba", "show a screenshot", "soon")

    saved = ctx.deps.commitment_store.load().entries[0]
    assert saved.status == "open"


async def test_add_commitment_returns_confirmation_with_id(tmp_path) -> None:
    ctx = make_commitment_ctx(tmp_path)

    result = await add_commitment(ctx, "Kuba", "show a screenshot", "soon")

    saved = ctx.deps.commitment_store.load().entries[0]
    assert result == f"Noted [id:{saved.id}] promise to Kuba: show a screenshot."


async def test_resolve_commitment_when_present_marks_it_fulfilled(tmp_path) -> None:
    ctx = make_commitment_ctx(tmp_path)
    await add_commitment(ctx, "Kuba", "show a screenshot", "soon")
    commitment_id = ctx.deps.commitment_store.load().entries[0].id

    await resolve_commitment(ctx, commitment_id)

    assert ctx.deps.commitment_store.load().entries[0].status == "fulfilled"


async def test_resolve_commitment_when_id_missing_returns_not_found(tmp_path) -> None:
    ctx = make_commitment_ctx(tmp_path)

    result = await resolve_commitment(ctx, "nope1234")

    assert result == "No open promise with id nope1234."


# ---------------------------------------------------------------------------
# format_message link previews
# ---------------------------------------------------------------------------


def make_embed(
    embed_type: str = "link",
    title: str | None = None,
    description: str | None = None,
    url: str | None = None,
    thumb_url: str | None = None,
    thumb_proxy: str | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        type=embed_type,
        title=title,
        description=description,
        url=url,
        thumbnail=SimpleNamespace(url=thumb_url, proxy_url=thumb_proxy),
    )


def make_link_message(
    embeds: list, content: str = "check this", attachments: list | None = None
) -> MagicMock:
    msg = MagicMock(spec=discord.Message)
    msg.id = 42
    msg.created_at = datetime(2024, 6, 1, 8, 0, tzinfo=timezone.utc)
    msg.author.display_name = "Ola"
    msg.clean_content = content
    msg.embeds = embeds
    msg.attachments = attachments or []
    return msg


def test_format_message_when_own_marks_the_author_as_her() -> None:
    msg = make_link_message([], content="siema")

    result = format_message(msg, own=True)

    assert "Ola (you): siema" in result


def test_format_message_when_not_own_leaves_the_author_unmarked() -> None:
    msg = make_link_message([], content="siema")

    result = format_message(msg)

    assert "Ola: siema" in result


def test_format_message_includes_link_preview_for_rich_embed() -> None:
    embed = make_embed(title="Deadlift", description="A compound lift.")
    msg = make_link_message([embed])

    result = format_message(msg)

    assert "[link preview: Deadlift — A compound lift.]" in result


def test_format_message_omits_preview_for_image_embed() -> None:
    embed = make_embed(embed_type="image", url="https://example.com/y.jpg")
    msg = make_link_message([embed])

    result = format_message(msg)

    assert "link preview" not in result


def test_format_message_truncates_long_link_preview() -> None:
    embed = make_embed(description="d" * (MAX_LINK_PREVIEW_LENGTH + 50))
    msg = make_link_message([embed])

    preview_line = format_message(msg).splitlines()[-1]

    assert preview_line.endswith("…]")
    assert "d" * MAX_LINK_PREVIEW_LENGTH in preview_line


# ---------------------------------------------------------------------------
# extract_images from embeds
# ---------------------------------------------------------------------------


def set_image_response(
    mock_client_cls: MagicMock, content: bytes, content_type: str
) -> None:
    response = MagicMock()
    response.content = content
    response.headers = {"content-type": content_type}
    response.raise_for_status = MagicMock()
    client = MagicMock()
    client.get = AsyncMock(return_value=response)
    mock_client_cls.return_value.__aenter__.return_value = client


@patch("livingbot.tools.httpx.AsyncClient")
async def test_extract_images_downloads_image_from_image_embed(
    mock_client_cls: MagicMock,
) -> None:
    set_image_response(mock_client_cls, b"jpeg-bytes", "image/jpeg")
    embed = make_embed(embed_type="image", thumb_proxy="https://cdn/x.jpg")
    msg = make_link_message([embed])

    images = await extract_images(msg)

    assert len(images) == 1
    assert images[0].data == b"jpeg-bytes"
    assert images[0].media_type == "image/jpeg"


@patch("livingbot.tools.httpx.AsyncClient")
async def test_extract_images_skips_embed_image_with_non_image_content_type(
    mock_client_cls: MagicMock,
) -> None:
    set_image_response(mock_client_cls, b"<html>", "text/html")
    embed = make_embed(embed_type="image", thumb_proxy="https://cdn/x")
    msg = make_link_message([embed])

    images = await extract_images(msg)

    assert images == []


@patch("livingbot.tools.httpx.AsyncClient")
async def test_extract_images_skips_oversized_embed_image(
    mock_client_cls: MagicMock,
) -> None:
    set_image_response(mock_client_cls, b"x" * (MAX_EMBED_IMAGE_BYTES + 1), "image/png")
    embed = make_embed(embed_type="image", thumb_proxy="https://cdn/x.png")
    msg = make_link_message([embed])

    images = await extract_images(msg)

    assert images == []


@patch("livingbot.tools.httpx.AsyncClient")
async def test_extract_images_skips_embed_image_when_fetch_fails(
    mock_client_cls: MagicMock,
) -> None:
    client = MagicMock()
    client.get = AsyncMock(side_effect=httpx.ConnectError("boom"))
    mock_client_cls.return_value.__aenter__.return_value = client
    embed = make_embed(embed_type="image", thumb_proxy="https://cdn/x.png")
    msg = make_link_message([embed])

    images = await extract_images(msg)

    assert images == []


# ---------------------------------------------------------------------------
# message_images / recent_message_images
# ---------------------------------------------------------------------------


def make_image_attachment(data: bytes) -> MagicMock:
    attachment = MagicMock(spec=discord.Attachment)
    attachment.content_type = "image/png"
    attachment.read = AsyncMock(return_value=data)
    return attachment


def make_image_message(message_id: int, image_count: int) -> MagicMock:
    msg = MagicMock(spec=discord.Message)
    msg.id = message_id
    msg.embeds = []
    msg.attachments = [
        make_image_attachment(f"{message_id}-{i}".encode()) for i in range(image_count)
    ]
    return msg


async def test_message_images_labels_each_image_with_its_message_id() -> None:
    msg = make_image_message(77, image_count=2)

    images = await message_images(msg)

    assert [image.message_id for image in images] == [77, 77]


async def test_recent_message_images_returns_oldest_first() -> None:
    """channel.history yields newest first, but the prompt lists the images in the
    order they were sent, so they have to come back the other way round."""
    newest_first = [make_image_message(30, 1), make_image_message(20, 1)]

    images = await recent_message_images(newest_first, limit=4)

    assert [image.content.data for image in images] == [b"20-0", b"30-0"]


async def test_recent_message_images_keeps_only_the_newest_up_to_the_limit() -> None:
    newest_first = [make_image_message(30, 1), make_image_message(20, 2)]

    images = await recent_message_images(newest_first, limit=2)

    assert [image.content.data for image in images] == [b"20-0", b"30-0"]


async def test_recent_message_images_does_not_read_messages_beyond_the_limit() -> None:
    """Reading an attachment downloads it, so a channel full of old pictures must not
    cost anything once enough of them have been gathered."""
    newest_first = [make_image_message(30, 2), make_image_message(20, 1)]

    await recent_message_images(newest_first, limit=2)

    newest_first[1].attachments[0].read.assert_not_awaited()


async def test_recent_message_images_when_limit_is_zero_returns_nothing() -> None:
    images = await recent_message_images([make_image_message(30, 1)], limit=0)

    assert images == []


# ---------------------------------------------------------------------------
# fetch_link
# ---------------------------------------------------------------------------


def make_page_response(
    text: str = "<html></html>",
    content_type: str = "text/html; charset=utf-8",
) -> MagicMock:
    response = MagicMock()
    response.text = text
    response.headers = {"content-type": content_type}
    response.raise_for_status = MagicMock()
    return response


def set_page_response(mock_client_cls: MagicMock, response: MagicMock) -> None:
    client = MagicMock()
    client.get = AsyncMock(return_value=response)
    mock_client_cls.return_value.__aenter__.return_value = client


@patch(
    "livingbot.tools.trafilatura.extract",
    return_value="Deadlifts build the whole back.",
)
@patch("livingbot.tools.httpx.AsyncClient")
async def test_fetch_link_returns_extracted_article_text(
    mock_client_cls: MagicMock, mock_extract: MagicMock
) -> None:
    set_page_response(mock_client_cls, make_page_response())

    result = await fetch_link("https://example.com/article")

    assert result == "Deadlifts build the whole back."


@patch("livingbot.tools.trafilatura.extract")
@patch("livingbot.tools.httpx.AsyncClient")
async def test_fetch_link_truncates_long_text(
    mock_client_cls: MagicMock, mock_extract: MagicMock
) -> None:
    mock_extract.return_value = "x" * (MAX_ARTICLE_CHARS + 500)
    set_page_response(mock_client_cls, make_page_response())

    result = await fetch_link("https://example.com/long")

    assert len(result) == MAX_ARTICLE_CHARS + 1
    assert result.endswith("…")


@patch("livingbot.tools.httpx.AsyncClient")
async def test_fetch_link_when_content_type_not_html_returns_not_readable_message(
    mock_client_cls: MagicMock,
) -> None:
    set_page_response(
        mock_client_cls, make_page_response(content_type="application/pdf")
    )

    result = await fetch_link("https://example.com/file.pdf")

    assert result == "That link isn't a readable page (application/pdf)."


@patch("livingbot.tools.httpx.AsyncClient")
async def test_fetch_link_when_request_fails_returns_couldnt_open_message(
    mock_client_cls: MagicMock,
) -> None:
    client = MagicMock()
    client.get = AsyncMock(side_effect=httpx.ConnectError("boom"))
    mock_client_cls.return_value.__aenter__.return_value = client

    result = await fetch_link("https://example.com/down")

    assert result == "Couldn't open that link."


@patch("livingbot.tools.trafilatura.extract", return_value=None)
@patch("livingbot.tools.httpx.AsyncClient")
async def test_fetch_link_when_no_readable_text_returns_message(
    mock_client_cls: MagicMock, mock_extract: MagicMock
) -> None:
    set_page_response(mock_client_cls, make_page_response())

    result = await fetch_link("https://example.com/empty")

    assert result == "Opened the link but there was no readable text on it."


async def test_add_commitment_resolves_the_persons_name_to_their_user_id(
    tmp_path,
) -> None:
    ctx = make_commitment_ctx(tmp_path)

    await add_commitment(ctx, "Kuba", "show a screenshot", "soon")

    assert ctx.deps.commitment_store.load().entries[0].user_id == "42"


async def test_add_commitment_for_an_unknown_person_records_nothing(tmp_path) -> None:
    ctx = make_commitment_ctx(tmp_path)

    await add_commitment(ctx, "Zenon", "show a screenshot", "soon")

    assert ctx.deps.commitment_store.load().entries == []


async def test_add_commitment_for_an_unknown_person_says_so(tmp_path) -> None:
    ctx = make_commitment_ctx(tmp_path)

    result = await add_commitment(ctx, "Zenon", "show a screenshot", "soon")

    assert result == "No one called Zenon is here, so there's nothing to record."


def test_format_message_shows_a_mention_as_a_name_not_a_raw_id() -> None:
    msg = make_link_message([], content="@Mugda idziesz?")

    result = format_message(msg)

    assert "@Mugda idziesz?" in result


@patch(
    "livingbot.image.generate_image",
    new_callable=AsyncMock,
    return_value=b"image-bytes",
)
async def test_take_photo_with_a_hobby_passes_that_hobby_to_generate_image(
    mock_gen: AsyncMock,
) -> None:
    painting = Hobby(name="painting", level=HobbyLevel.expert)
    ctx = make_photo_ctx(make_hobby_store(Hobbies(entries=[painting])))

    await take_photo(
        ctx,
        description="the canvas I just finished",
        include_mugda=False,
        hobby="painting",
    )

    assert mock_gen.call_args.kwargs["hobby"] == painting


@patch(
    "livingbot.image.generate_image",
    new_callable=AsyncMock,
    return_value=b"image-bytes",
)
async def test_take_photo_without_a_hobby_passes_none_to_generate_image(
    mock_gen: AsyncMock,
) -> None:
    ctx = make_photo_ctx(make_hobby_store(Hobbies(entries=[Hobby(name="painting")])))

    await take_photo(ctx, description="a quiet park", include_mugda=False)

    assert mock_gen.call_args.kwargs["hobby"] is None


@patch(
    "livingbot.image.generate_image",
    new_callable=AsyncMock,
    return_value=b"image-bytes",
)
async def test_take_photo_with_an_unknown_hobby_does_not_generate_an_image(
    mock_gen: AsyncMock,
) -> None:
    """Generating is slow and costs money, so a bad name is caught before the call."""
    ctx = make_photo_ctx(make_hobby_store(Hobbies(entries=[Hobby(name="gym")])))

    await take_photo(ctx, description="my pot", include_mugda=False, hobby="pottery")

    mock_gen.assert_not_awaited()


@patch(
    "livingbot.image.generate_image",
    new_callable=AsyncMock,
    return_value=b"image-bytes",
)
async def test_take_photo_with_an_unknown_hobby_names_her_actual_hobbies(
    mock_gen: AsyncMock,
) -> None:
    ctx = make_photo_ctx(make_hobby_store(Hobbies(entries=[Hobby(name="gym")])))

    result = await take_photo(
        ctx, description="my pot", include_mugda=False, hobby="pottery"
    )

    assert "Your hobbies are: gym." in result


@patch(
    "livingbot.image.generate_image",
    new_callable=AsyncMock,
    return_value=b"image-bytes",
)
async def test_take_photo_with_an_unknown_hobby_leaves_no_photo_attached(
    mock_gen: AsyncMock,
) -> None:
    ctx = make_photo_ctx(make_hobby_store(Hobbies(entries=[Hobby(name="gym")])))

    await take_photo(ctx, description="my pot", include_mugda=False, hobby="pottery")

    assert ctx.deps.photo_result is None


# ---------------------------------------------------------------------------
# react_to_message / ignore_message
# ---------------------------------------------------------------------------


def make_silence_ctx(
    can_ignore: bool = False, can_react: bool = True
) -> SimpleNamespace:
    deps = BotDeps(
        channel=MagicMock(),
        channel_id=1,
        calendar_store=MagicMock(),
        activity_notes_store=MagicMock(),
        inventory_store=make_inventory_store(),
        spending_store=make_spending_store(),
        hobby_store=make_hobby_store(),
        story_store=make_story_store(),
        preference_store=MagicMock(),
        commitment_store=MagicMock(),
        can_ignore=can_ignore,
        can_react=can_react,
    )
    return SimpleNamespace(deps=deps)


async def test_react_to_message_puts_the_emoji_on_the_message() -> None:
    ctx = make_silence_ctx()
    message = MagicMock()
    message.add_reaction = AsyncMock()
    ctx.deps.channel.fetch_message = AsyncMock(return_value=message)

    await react_to_message(ctx, "77", "🔥")

    message.add_reaction.assert_awaited_once_with("🔥")


async def test_react_to_message_when_it_lands_makes_the_reaction_her_whole_reply() -> (
    None
):
    ctx = make_silence_ctx()
    message = MagicMock()
    message.add_reaction = AsyncMock()
    ctx.deps.channel.fetch_message = AsyncMock(return_value=message)

    await react_to_message(ctx, "77", "🔥")

    assert ctx.deps.reaction == "🔥"


async def test_react_to_message_when_discord_rejects_the_emoji_still_lets_her_reply() -> (
    None
):
    ctx = make_silence_ctx()
    message = MagicMock()
    message.add_reaction = AsyncMock(side_effect=discord.HTTPException(MagicMock(), ""))
    ctx.deps.channel.fetch_message = AsyncMock(return_value=message)

    await react_to_message(ctx, "77", "not-an-emoji")

    assert ctx.deps.reaction is None


async def test_react_to_message_with_an_unknown_message_id_still_lets_her_reply() -> (
    None
):
    ctx = make_silence_ctx()
    ctx.deps.channel.fetch_message = AsyncMock(
        side_effect=discord.HTTPException(MagicMock(), "")
    )

    await react_to_message(ctx, "77", "🔥")

    assert ctx.deps.reaction is None


async def test_react_to_message_with_a_non_numeric_id_reports_the_message_is_missing() -> (
    None
):
    ctx = make_silence_ctx()

    result = await react_to_message(ctx, "the second one", "🔥")

    assert result == "There's no message with id the second one in this channel."


async def test_ignore_message_when_allowed_leaves_them_with_silence() -> None:
    ctx = make_silence_ctx(can_ignore=True)

    await ignore_message(ctx)

    assert ctx.deps.ignored is True


async def test_ignore_message_when_not_allowed_keeps_her_answering() -> None:
    ctx = make_silence_ctx(can_ignore=False)

    await ignore_message(ctx)

    assert ctx.deps.ignored is False


async def test_ignore_message_when_not_allowed_tells_her_to_answer_them() -> None:
    ctx = make_silence_ctx(can_ignore=False)

    result = await ignore_message(ctx)

    assert "Answer them" in result


async def test_react_to_message_when_she_is_not_answering_anyone_leaves_it_alone() -> (
    None
):
    ctx = make_silence_ctx(can_react=False)
    ctx.deps.channel.fetch_message = AsyncMock()

    await react_to_message(ctx, "77", "🔥")

    ctx.deps.channel.fetch_message.assert_not_awaited()


async def test_react_to_message_when_she_is_not_answering_anyone_tells_her_to_speak() -> (
    None
):
    ctx = make_silence_ctx(can_react=False)

    result = await react_to_message(ctx, "77", "🔥")

    assert "nothing to react to here" in result
