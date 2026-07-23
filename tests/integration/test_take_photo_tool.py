"""
Integration tests verifying Mugda uses take_photo correctly.

Progression:
  1. Explicit instruction to take a photo with tool name mentioned
  2. Explicit instruction to take a selfie — should use include_mugda=True
  3. Explicit instruction to take a photo of surroundings — include_mugda=False
  4. Natural context (at the gym, asked how she's doing) — should decide to take photo
  5. Natural context asking about a place she's at — photo of scenery, not selfie
  6. Unambiguous "no photo needed" conversation — must NOT call take_photo

Run on demand: uv run pytest tests/integration/test_take_photo_tool.py
Requires OPENROUTER_API_KEY in the environment.
"""

import os
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart

from livingbot.prompts import PHOTO_HINT
from livingbot.activity_notes import ActivityNotesStore
from livingbot.calendar import Calendar, CalendarStore, PlanEntry
from livingbot.hobbies import HobbyStore
from livingbot.inventory import InventoryStore
from livingbot.llm import LLMClient
from livingbot.spending import SpendingStore
from livingbot.stories import StoryStore

pytestmark = pytest.mark.skipif(
    not os.environ.get("OPENROUTER_API_KEY"),
    reason="OPENROUTER_API_KEY not set",
)

NOW = datetime(2026, 6, 4, 18, 15)  # Wednesday evening


def _tool_calls(result, tool_name: str) -> list[ToolCallPart]:
    calls = []
    for message in result.all_messages():
        if isinstance(message, ModelResponse):
            for part in message.parts:
                if isinstance(part, ToolCallPart) and part.tool_name == tool_name:
                    calls.append(part)
    return calls


def _tool_was_called(result, tool_name: str) -> bool:
    return len(_tool_calls(result, tool_name)) > 0


def _take_photo_args(result) -> dict:
    calls = _tool_calls(result, "take_photo")
    assert calls, "take_photo was not called"
    return calls[0].args if isinstance(calls[0].args, dict) else calls[0].args_as_dict()


@pytest.fixture
def client() -> LLMClient:
    return LLMClient.create()


@pytest.fixture
def calendar_store(tmp_path) -> CalendarStore:
    return CalendarStore(tmp_path, home_location="home")


@pytest.fixture
def calendar_store_at_gym(tmp_path) -> CalendarStore:
    store = CalendarStore(tmp_path, home_location="home")
    calendar = Calendar(
        home_location="home",
        entries=[
            PlanEntry(
                activity="trening na siłowni",
                location="siłownia FitPlus",
                start=datetime(2026, 6, 4, 17, 30),
                end=datetime(2026, 6, 4, 19, 30),
            )
        ],
    )
    store.save(calendar)
    return store


@pytest.fixture
def calendar_store_at_park(tmp_path) -> CalendarStore:
    store = CalendarStore(tmp_path, home_location="home")
    calendar = Calendar(
        home_location="home",
        entries=[
            PlanEntry(
                activity="spacer po parku",
                location="Park Łazienkowski",
                start=datetime(2026, 6, 4, 17, 0),
                end=datetime(2026, 6, 4, 19, 30),
            )
        ],
    )
    store.save(calendar)
    return store


@pytest.fixture
def inventory_store(tmp_path) -> InventoryStore:
    return InventoryStore.create(tmp_path / "inventory")


@pytest.fixture
def spending_store(tmp_path) -> SpendingStore:
    return SpendingStore(tmp_path / "spending")


def _make_complete_kwargs(
    client: LLMClient,
    messages: list[str],
    calendar_store: CalendarStore,
    activity_notes_store: ActivityNotesStore,
    inventory_store: InventoryStore,
    spending_store: SpendingStore,
    hobby_store: HobbyStore,
    story_store: StoryStore,
    photo_hint: str = "",
) -> dict:
    return dict(
        user_messages=messages,
        channel=MagicMock(),
        calendar_store=calendar_store,
        activity_notes_store=activity_notes_store,
        inventory_store=inventory_store,
        spending_store=spending_store,
        hobby_store=hobby_store,
        story_store=story_store,
        now=NOW,
        photo_hint=photo_hint,
    )


# ---------------------------------------------------------------------------
# helper — we don't want real RunPod calls; patch generate_image to a no-op
# ---------------------------------------------------------------------------

_PATCH_GENERATE = patch(
    "livingbot.image.generate_image",
    new_callable=lambda: lambda *a, **kw: _async_bytes(),
)


async def _async_bytes() -> bytes:
    return b"\xff\xd8\xff"


# ---------------------------------------------------------------------------
# 1. Explicit: told directly to take a photo using the tool name
# ---------------------------------------------------------------------------


async def test_take_photo_called_when_explicitly_instructed(
    client: LLMClient,
    calendar_store: CalendarStore,
    activity_notes_store: ActivityNotesStore,
    inventory_store: InventoryStore,
    spending_store: SpendingStore,
    hobby_store: HobbyStore,
    story_store: StoryStore,
) -> None:
    """User explicitly names the tool and asks Mugda to use it."""
    with patch(
        "livingbot.image.generate_image", new=AsyncMock(return_value=b"\xff\xd8\xff")
    ):
        result = await client.complete(
            **_make_complete_kwargs(
                client,
                [
                    "[id:100] [2026-06-04 18:15:00] Ola: Mugda użyj take_photo i wyślij mi jakieś zdjęcie, co tam u ciebie słychać"
                ],
                calendar_store,
                activity_notes_store,
                inventory_store,
                spending_store,
                hobby_store,
                story_store,
                photo_hint=PHOTO_HINT,
            )
        )

    assert _tool_was_called(result, "take_photo"), (
        f"Expected take_photo to be called. Response: {result.output}"
    )


# ---------------------------------------------------------------------------
# 2. Explicit selfie request — include_mugda must be True
# ---------------------------------------------------------------------------


async def test_take_photo_include_mugda_true_when_selfie_requested(
    client: LLMClient,
    calendar_store_at_gym: CalendarStore,
    activity_notes_store: ActivityNotesStore,
    inventory_store: InventoryStore,
    spending_store: SpendingStore,
    hobby_store: HobbyStore,
    story_store: StoryStore,
) -> None:
    """User asks for a selfie — Mugda should appear in the photo."""
    with patch(
        "livingbot.image.generate_image", new=AsyncMock(return_value=b"\xff\xd8\xff")
    ):
        result = await client.complete(
            **_make_complete_kwargs(
                client,
                [
                    "[id:200] [2026-06-04 18:15:00] Marek: Mugda zrób sobie selfie na siłowni, chcę zobaczyć jak wyglądasz podczas treningu 💪"
                ],
                calendar_store_at_gym,
                activity_notes_store,
                inventory_store,
                spending_store,
                hobby_store,
                story_store,
                photo_hint=PHOTO_HINT,
            )
        )

    assert _tool_was_called(result, "take_photo"), (
        f"Expected take_photo to be called. Response: {result.output}"
    )
    args = _take_photo_args(result)
    assert args.get("include_mugda") is True, (
        f"Expected include_mugda=True for a selfie request. Got: {args}"
    )


# ---------------------------------------------------------------------------
# 3. Explicit scenery photo request — include_mugda must be False
# ---------------------------------------------------------------------------


async def test_take_photo_include_mugda_false_when_scenery_requested(
    client: LLMClient,
    calendar_store_at_park: CalendarStore,
    activity_notes_store: ActivityNotesStore,
    inventory_store: InventoryStore,
    spending_store: SpendingStore,
    hobby_store: HobbyStore,
    story_store: StoryStore,
) -> None:
    """User asks for a photo of the surroundings, not Mugda herself."""
    with patch(
        "livingbot.image.generate_image", new=AsyncMock(return_value=b"\xff\xd8\xff")
    ):
        result = await client.complete(
            **_make_complete_kwargs(
                client,
                [
                    "[id:300] [2026-06-04 18:15:00] Kasia: Mugda zrób zdjęcie parku, tak żeby nie było ciebie na nim — chcę zobaczyć jak wygląda Łazienkowski o tej porze roku"
                ],
                calendar_store_at_park,
                activity_notes_store,
                inventory_store,
                spending_store,
                hobby_store,
                story_store,
                photo_hint=PHOTO_HINT,
            )
        )

    assert _tool_was_called(result, "take_photo"), (
        f"Expected take_photo to be called. Response: {result.output}"
    )
    args = _take_photo_args(result)
    assert args.get("include_mugda") is False, (
        f"Expected include_mugda=False for a scenery-only request. Got: {args}"
    )


# ---------------------------------------------------------------------------
# 4. Natural context: asked how she's doing while at the gym + hint present
#    She should decide to take a photo on her own
# ---------------------------------------------------------------------------


async def test_take_photo_called_naturally_when_at_gym_and_hint_present(
    client: LLMClient,
    calendar_store_at_gym: CalendarStore,
    activity_notes_store: ActivityNotesStore,
    inventory_store: InventoryStore,
    spending_store: SpendingStore,
    hobby_store: HobbyStore,
    story_store: StoryStore,
) -> None:
    """Natural trigger: someone asks how she's doing while she's mid-workout.
    The hint is present, so she should choose to take a gym photo."""
    with patch(
        "livingbot.image.generate_image", new=AsyncMock(return_value=b"\xff\xd8\xff")
    ):
        result = await client.complete(
            **_make_complete_kwargs(
                client,
                [
                    "[id:400] [2026-06-04 18:15:00] Piotrek: hej Mugda, co tam robisz? wszystko ok? 😊"
                ],
                calendar_store_at_gym,
                activity_notes_store,
                inventory_store,
                spending_store,
                hobby_store,
                story_store,
                photo_hint=PHOTO_HINT,
            )
        )

    assert _tool_was_called(result, "take_photo"), (
        f"Expected take_photo to be called spontaneously at the gym with hint. "
        f"Response: {result.output}"
    )


# ---------------------------------------------------------------------------
# 5. Natural context: asked about a place — scenery photo, not selfie
# ---------------------------------------------------------------------------


async def test_take_photo_include_mugda_false_when_asked_about_place(
    client: LLMClient,
    calendar_store_at_park: CalendarStore,
    activity_notes_store: ActivityNotesStore,
    inventory_store: InventoryStore,
    spending_store: SpendingStore,
    hobby_store: HobbyStore,
    story_store: StoryStore,
) -> None:
    """Someone asks what the park looks like — Mugda should photograph the scenery,
    not take a selfie."""
    with patch(
        "livingbot.image.generate_image", new=AsyncMock(return_value=b"\xff\xd8\xff")
    ):
        result = await client.complete(
            **_make_complete_kwargs(
                client,
                [
                    "[id:500] [2026-06-04 18:15:00] Bartek: Mugda jak tam w Łazienkach dziś wygląda? warto wpaść?"
                ],
                calendar_store_at_park,
                activity_notes_store,
                inventory_store,
                spending_store,
                hobby_store,
                story_store,
                photo_hint=PHOTO_HINT,
            )
        )

    assert _tool_was_called(result, "take_photo"), (
        f"Expected take_photo for a scenery question. Response: {result.output}"
    )
    args = _take_photo_args(result)
    assert args.get("include_mugda") is False, (
        f"Expected include_mugda=False when photographing a place. Got: {args}"
    )


# ---------------------------------------------------------------------------
# 6. No photo needed — purely conversational exchange
# ---------------------------------------------------------------------------


async def test_take_photo_not_called_for_routine_conversation(
    client: LLMClient,
    calendar_store: CalendarStore,
    activity_notes_store: ActivityNotesStore,
    inventory_store: InventoryStore,
    spending_store: SpendingStore,
    hobby_store: HobbyStore,
    story_store: StoryStore,
) -> None:
    """Routine chat at home with no hint present — no photo should be taken."""
    with patch(
        "livingbot.image.generate_image", new=AsyncMock(return_value=b"\xff\xd8\xff")
    ):
        result = await client.complete(
            **_make_complete_kwargs(
                client,
                [
                    "[id:600] [2026-06-04 18:15:00] Ola: Mugda pamiętasz jak się nazywał ten serial co go razem oglądałyśmy w zeszłym roku?"
                ],
                calendar_store,
                activity_notes_store,
                inventory_store,
                spending_store,
                hobby_store,
                story_store,
                photo_hint="",  # no hint — below cooldown threshold
            )
        )

    assert not _tool_was_called(result, "take_photo"), (
        f"Expected take_photo NOT to be called for routine chat. Response: {result.output}"
    )
