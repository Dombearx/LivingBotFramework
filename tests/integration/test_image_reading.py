"""
Integration tests verifying Mugda answers from pictures sent earlier in the channel
rather than making their details up.

Only the messages she is replying to used to carry images, so a photo one message
back — including one she took herself — was invisible by the time anyone asked about
it, and she invented an answer. The reply path now re-attaches the most recent images
from channel history, each labelled with the message it belongs to.

Progression:
  1. A picture she sent herself, one message back — she must describe what is in it
  2. Two pictures from different people — she must answer about the right one

The pictures are flat blocks of colour generated here rather than photographs: the
point is whether the bytes reach her and she reads them off the right message, and a
colour is the one detail a reader of the run can check at a glance.

Run on demand: uv run pytest tests/integration/test_image_reading.py
Requires OPENROUTER_API_KEY in the environment.
"""

import os
import struct
import zlib
from datetime import datetime
from unittest.mock import MagicMock

import pytest
from pydantic_ai import BinaryContent

from livingbot.activity_notes import ActivityNotesStore
from livingbot.calendar import CalendarStore
from livingbot.commitments import CommitmentStore
from livingbot.hobbies import HobbyStore
from livingbot.inventory import InventoryStore
from livingbot.llm import LLMClient
from livingbot.preferences import PreferenceStore
from livingbot.spending import SpendingStore
from livingbot.stories import StoryStore
from livingbot.tools import MessageImage

pytestmark = pytest.mark.skipif(
    not os.environ.get("OPENROUTER_API_KEY"),
    reason="OPENROUTER_API_KEY not set",
)

NOW = datetime(2026, 6, 4, 18, 15)  # Wednesday evening
CHANNEL_ID = 1234

RED = (220, 30, 30)
BLUE = (30, 60, 210)
GREEN = (40, 170, 60)

# Reading a colour off a picture rather than guessing at it means naming the shade,
# and Polish has a word for each of them — she called this one "kobaltowy, wpada w
# granat". Any of these is her having looked; none of them is her inventing.
BLUE_WORDS = ("niebiesk", "granat", "kobalt", "błękit", "szafir", "chabr")


def _png_chunk(tag: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + tag
        + data
        + struct.pack(">I", zlib.crc32(tag + data))
    )


def solid_png(rgb: tuple[int, int, int], size: int = 256) -> bytes:
    """A single-colour PNG, written by hand so the tests need no imaging library."""
    scanline = b"\x00" + bytes(rgb) * size
    header = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", header)
        + _png_chunk(b"IDAT", zlib.compress(scanline * size))
        + _png_chunk(b"IEND", b"")
    )


def message_image(message_id: int, rgb: tuple[int, int, int]) -> MessageImage:
    return MessageImage(
        message_id=message_id,
        content=BinaryContent(data=solid_png(rgb), media_type="image/png"),
    )


@pytest.fixture
def client() -> LLMClient:
    return LLMClient.create()


@pytest.fixture
def calendar_store(tmp_path) -> CalendarStore:
    return CalendarStore(tmp_path, home_location="dom")


@pytest.fixture
def inventory_store(tmp_path) -> InventoryStore:
    return InventoryStore.create(tmp_path / "inventory")


def _complete_kwargs(
    messages: list[str],
    history: list[str],
    images: list[MessageImage],
    calendar_store: CalendarStore,
    activity_notes_store: ActivityNotesStore,
    inventory_store: InventoryStore,
    spending_store: SpendingStore,
    hobby_store: HobbyStore,
    story_store: StoryStore,
    preference_store: PreferenceStore,
    commitment_store: CommitmentStore,
) -> dict:
    return dict(
        user_messages=messages,
        channel=MagicMock(),
        channel_id=CHANNEL_ID,
        calendar_store=calendar_store,
        activity_notes_store=activity_notes_store,
        inventory_store=inventory_store,
        spending_store=spending_store,
        hobby_store=hobby_store,
        story_store=story_store,
        preference_store=preference_store,
        commitment_store=commitment_store,
        now=NOW,
        history=history,
        images=images,
    )


# ---------------------------------------------------------------------------
# 1. A picture she sent herself, one message back
# ---------------------------------------------------------------------------


async def test_answers_about_the_picture_she_sent_a_message_earlier(
    client: LLMClient,
    calendar_store: CalendarStore,
    activity_notes_store: ActivityNotesStore,
    inventory_store: InventoryStore,
    spending_store: SpendingStore,
    hobby_store: HobbyStore,
    story_store: StoryStore,
    preference_store: PreferenceStore,
    commitment_store: CommitmentStore,
    save_image,
) -> None:
    """She showed a picture one message ago and is now asked what colour is in it.
    She has to read her own picture instead of naming a colour at random."""
    save_image(
        "image_reading_her_wall",
        solid_png(BLUE),
        "shown to her as the wall she painted — she is asked its colour",
        suffix=".png",
    )

    result = await client.complete(
        **_complete_kwargs(
            [
                "[id:11] [2026-06-04 18:15:00] Kuba: no dobra a jaki to dokładnie "
                "kolor jest na tej ścianie? bo na telefonie mi się dziwnie wyświetla"
            ],
            [
                "[id:10] [2026-06-04 18:10:00] Mugda (you): pomalowałam w końcu tę "
                "ścianę, patrzcie"
            ],
            [message_image(10, BLUE)],
            calendar_store,
            activity_notes_store,
            inventory_store,
            spending_store,
            hobby_store,
            story_store,
            preference_store,
            commitment_store,
        )
    )

    output = result.output.lower()
    assert any(word in output for word in BLUE_WORDS), (
        f"Expected her to name the blue she was shown. Response: {result.output}"
    )


# ---------------------------------------------------------------------------
# 2. Two pictures from different people — she must answer about the right one
# ---------------------------------------------------------------------------


async def test_answers_about_the_right_picture_when_two_are_in_history(
    client: LLMClient,
    calendar_store: CalendarStore,
    activity_notes_store: ActivityNotesStore,
    inventory_store: InventoryStore,
    spending_store: SpendingStore,
    hobby_store: HobbyStore,
    story_store: StoryStore,
    preference_store: PreferenceStore,
    commitment_store: CommitmentStore,
    save_image,
) -> None:
    """Two people posted a picture each. Asked about Ola's wall, she must go by Ola's
    picture — the images arrive as a bare list, so getting this right means she used
    the message id each one is labelled with."""
    save_image(
        "image_reading_olas_wall",
        solid_png(RED),
        "posted by Ola as her wall — the picture the question is about",
        suffix=".png",
    )
    save_image(
        "image_reading_her_plant",
        solid_png(GREEN),
        "posted by Mugda as her plant — the distractor she must not answer about",
        suffix=".png",
    )

    result = await client.complete(
        **_complete_kwargs(
            [
                "[id:22] [2026-06-04 18:15:00] Kuba: ej a jaki kolor Ola wybrała "
                "ostatecznie na tę ścianę? nie mogę doscrollować"
            ],
            [
                "[id:20] [2026-06-04 18:05:00] Ola: no i pomalowane, tak wyszło",
                "[id:21] [2026-06-04 18:08:00] Mugda (you): a u mnie nowy kwiatek",
            ],
            [message_image(20, RED), message_image(21, GREEN)],
            calendar_store,
            activity_notes_store,
            inventory_store,
            spending_store,
            hobby_store,
            story_store,
            preference_store,
            commitment_store,
        )
    )

    output = result.output.lower()
    assert "czerwon" in output, (
        f"Expected her to name the red from Ola's picture. Response: {result.output}"
    )
    assert "zielon" not in output, (
        f"Expected her not to answer with the green from her own picture. "
        f"Response: {result.output}"
    )
