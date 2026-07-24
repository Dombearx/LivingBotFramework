"""
Integration tests verifying Mugda uses fetch_link correctly: she opens a shared
link when her reply depends on what's on the page, and leaves it alone when it
doesn't. The network is patched so the real tool runs deterministically without
making an outbound request.

Run on demand: uv run pytest tests/integration/test_fetch_link_tool.py
Requires OPENROUTER_API_KEY in the environment.
"""

import os
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart

from livingbot.activity_notes import ActivityNotesStore
from livingbot.calendar import CalendarStore
from livingbot.hobbies import HobbyStore
from livingbot.inventory import InventoryStore
from livingbot.llm import LLMClient
from livingbot.spending import SpendingStore
from livingbot.stories import StoryStore

pytestmark = pytest.mark.skipif(
    not os.environ.get("OPENROUTER_API_KEY"),
    reason="OPENROUTER_API_KEY not set",
)

NOW = datetime(2026, 6, 6, 15, 0)

ARTICLE_HTML = """
<html><head><title>Kreatyna: fakty i mity</title></head><body>
<nav>strona główna · o nas · kontakt</nav>
<article>
<h1>Kreatyna: fakty i mity</h1>
<p>Kreatyna monohydrat to jeden z najlepiej przebadanych suplementów w historii
sportu. Dziesiątki badań pokazują, że pomaga zwiększyć siłę i masę mięśniową przy
regularnym treningu oporowym.</p>
<p>Typowa dawka to około 5 gramów dziennie. Nie trzeba robić fazy ładowania —
wystarczy brać ją codziennie, a poziom w mięśniach i tak się nasyci po kilku
tygodniach.</p>
<p>Wbrew mitom kreatyna nie niszczy nerek u zdrowych osób i nie powoduje odwodnienia.
Lekki przyrost wody w mięśniach jest normalny i pożądany.</p>
</article>
<footer>© 2026 fitblog</footer>
</body></html>
"""


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


def _fetch_link_args(result) -> dict:
    calls = _tool_calls(result, "fetch_link")
    assert calls, "fetch_link was not called"
    return calls[0].args if isinstance(calls[0].args, dict) else calls[0].args_as_dict()


def _patched_network(html: str = ARTICLE_HTML):
    response = MagicMock()
    response.text = html
    response.headers = {"content-type": "text/html; charset=utf-8"}
    response.raise_for_status = MagicMock()
    client = MagicMock()
    client.get = AsyncMock(return_value=response)
    client_cls = MagicMock()
    client_cls.return_value.__aenter__.return_value = client
    return patch("livingbot.tools.httpx.AsyncClient", new=client_cls)


@pytest.fixture
def client() -> LLMClient:
    return LLMClient.create()


@pytest.fixture
def calendar_store(tmp_path) -> CalendarStore:
    return CalendarStore(tmp_path, home_location="home")


@pytest.fixture
def inventory_store(tmp_path) -> InventoryStore:
    return InventoryStore.create(tmp_path / "inventory")


async def _complete(
    client: LLMClient,
    messages: list[str],
    calendar_store: CalendarStore,
    activity_notes_store: ActivityNotesStore,
    inventory_store: InventoryStore,
    spending_store: SpendingStore,
    hobby_store: HobbyStore,
    story_store: StoryStore,
):
    with _patched_network():
        return await client.complete(
            messages,
            MagicMock(),
            calendar_store,
            activity_notes_store,
            inventory_store,
            spending_store,
            hobby_store,
            story_store,
            NOW,
        )


# ---------------------------------------------------------------------------
# Calls fetch_link when the reply depends on what's on the page
# ---------------------------------------------------------------------------


async def test_fetch_link_called_when_asked_to_read_shared_article(
    client: LLMClient,
    calendar_store: CalendarStore,
    activity_notes_store: ActivityNotesStore,
    inventory_store: InventoryStore,
    spending_store: SpendingStore,
    hobby_store: HobbyStore,
    story_store: StoryStore,
) -> None:
    """Directly asked to read a shared link and say what she thinks about it."""
    messages = [
        "[id:100] [2026-06-06 15:00:00] Ola: Mugda zerknij na ten artykuł i powiedz "
        "co o nim myślisz: https://fitblog.example.com/kreatyna-fakty-i-mity"
    ]

    result = await _complete(
        client,
        messages,
        calendar_store,
        activity_notes_store,
        inventory_store,
        spending_store,
        hobby_store,
        story_store,
    )

    assert _tool_was_called(result, "fetch_link"), (
        f"Expected fetch_link to be called. Response: {result.output}"
    )


async def test_fetch_link_called_with_the_shared_url(
    client: LLMClient,
    calendar_store: CalendarStore,
    activity_notes_store: ActivityNotesStore,
    inventory_store: InventoryStore,
    spending_store: SpendingStore,
    hobby_store: HobbyStore,
    story_store: StoryStore,
) -> None:
    """The URL she fetches is the one that was shared in the message."""
    messages = [
        "[id:200] [2026-06-06 15:00:00] Marek: przeczytaj to i powiedz o co chodzi: "
        "https://fitblog.example.com/kreatyna-fakty-i-mity"
    ]

    result = await _complete(
        client,
        messages,
        calendar_store,
        activity_notes_store,
        inventory_store,
        spending_store,
        hobby_store,
        story_store,
    )

    args = _fetch_link_args(result)
    assert "fitblog.example.com/kreatyna-fakty-i-mity" in args.get("url", ""), (
        f"Expected the shared URL to be passed to fetch_link. Got: {args}"
    )


async def test_fetch_link_called_when_opinion_on_link_requested(
    client: LLMClient,
    calendar_store: CalendarStore,
    activity_notes_store: ActivityNotesStore,
    inventory_store: InventoryStore,
    spending_store: SpendingStore,
    hobby_store: HobbyStore,
    story_store: StoryStore,
) -> None:
    """A link dropped with a genuine 'what do you reckon?' — she should read it first."""
    messages = [
        "[id:300] [2026-06-06 15:00:00] Kasia: widziałaś to? "
        "https://fitblog.example.com/kreatyna-fakty-i-mity ciekawe czy to prawda z tymi nerkami"
    ]

    result = await _complete(
        client,
        messages,
        calendar_store,
        activity_notes_store,
        inventory_store,
        spending_store,
        hobby_store,
        story_store,
    )

    assert _tool_was_called(result, "fetch_link"), (
        f"Expected fetch_link to be called before reacting to the link. "
        f"Response: {result.output}"
    )


# ---------------------------------------------------------------------------
# Leaves fetch_link alone when it isn't needed
# ---------------------------------------------------------------------------


async def test_fetch_link_not_called_for_routine_conversation(
    client: LLMClient,
    calendar_store: CalendarStore,
    activity_notes_store: ActivityNotesStore,
    inventory_store: InventoryStore,
    spending_store: SpendingStore,
    hobby_store: HobbyStore,
    story_store: StoryStore,
) -> None:
    """Ordinary chat with no link — nothing to fetch."""
    messages = [
        "[id:400] [2026-06-06 15:00:00] Ola: siema, jak minął ci dzień? robiłaś dziś trening?"
    ]

    result = await _complete(
        client,
        messages,
        calendar_store,
        activity_notes_store,
        inventory_store,
        spending_store,
        hobby_store,
        story_store,
    )

    assert not _tool_was_called(result, "fetch_link"), (
        f"Expected fetch_link NOT to be called in routine chat. Response: {result.output}"
    )


async def test_fetch_link_not_called_when_link_is_incidental(
    client: LLMClient,
    calendar_store: CalendarStore,
    activity_notes_store: ActivityNotesStore,
    inventory_store: InventoryStore,
    spending_store: SpendingStore,
    hobby_store: HobbyStore,
    story_store: StoryStore,
) -> None:
    """A link is mentioned only in passing while the user asks about her, not the page."""
    messages = [
        "[id:500] [2026-06-06 15:00:00] Bartek: założyłem se ostatnio stronę "
        "https://mojarandomstrona.example.com ale mniejsza z tym — lepiej powiedz jak "
        "tam twoje treningi ostatnio szły?"
    ]

    result = await _complete(
        client,
        messages,
        calendar_store,
        activity_notes_store,
        inventory_store,
        spending_store,
        hobby_store,
        story_store,
    )

    assert not _tool_was_called(result, "fetch_link"), (
        f"Expected fetch_link NOT to be called when the link is incidental. "
        f"Response: {result.output}"
    )
