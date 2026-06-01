"""
Integration tests that send real requests to the LLM and verify it calls load_context
when the conversation warrants fetching message history.

Run on demand: uv run pytest tests/integration/
Requires OPENAI_API_KEY in the environment.
"""

import os
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart

from livingbot.llm import LLMClient, LLMConfig

pytestmark = pytest.mark.skipif(
    not os.environ.get("OPENAI_API_KEY"),
    reason="OPENAI_API_KEY not set",
)

_MODEL = os.environ.get("LLM_INTEGRATION_MODEL", "openai:gpt-4o-mini")

_SYSTEM_PROMPT = """Jesteś pomocnym botem na polskim serwerze Discord dla graczy.
Gdy użytkownik pyta o poprzednie wiadomości, historię rozmowy lub co było wcześniej
napisane, użyj narzędzia load_context, aby pobrać wcześniejsze wiadomości z kanału.
Identyfikatory wiadomości (id:XXXXX) znajdziesz w treści wiadomości — użyj ich jako
before_message_id przy wywołaniu load_context."""


def _make_history_message(id: int, author: str, content: str) -> MagicMock:
    msg = MagicMock()
    msg.id = id
    msg.created_at = datetime(2026, 5, 31, 10, 0, 0, tzinfo=timezone.utc)
    msg.author.display_name = author
    msg.content = content
    return msg


def _make_channel(history: list[MagicMock]) -> MagicMock:
    channel = MagicMock()

    async def history_gen(*args, **kwargs):
        for msg in history:
            yield msg

    channel.history = MagicMock(side_effect=lambda **kwargs: history_gen())
    return channel


def _load_context_was_called(result) -> bool:
    for message in result.all_messages():
        if isinstance(message, ModelResponse):
            for part in message.parts:
                if isinstance(part, ToolCallPart) and part.tool_name == "load_context":
                    return True
    return False


@pytest.fixture
def client() -> LLMClient:
    return LLMClient(LLMConfig(model=_MODEL, system_prompt=_SYSTEM_PROMPT))


async def test_load_context_called_when_explicitly_asked(client: LLMClient) -> None:
    """Sanity check: bot fetches history when user directly asks for it."""
    channel = _make_channel(
        [
            _make_history_message(900, "Marek", "hej, co u was?"),
            _make_history_message(901, "Kasia", "spoko, gramy w CS"),
        ]
    )
    user_messages = [
        "[id:1000] [2026-05-31 12:00:00] TestUser: Can you check what messages were sent before this one? Use the load_context tool with id 1000."
    ]

    result = await client.complete(user_messages, channel)

    assert _load_context_was_called(result), (
        f"Expected load_context to be called. LLM response: {result.output}"
    )


async def test_load_context_called_for_polish_history_question(
    client: LLMClient,
) -> None:
    """Bot fetches history when asked in Polish what was discussed earlier."""
    channel = _make_channel(
        [
            _make_history_message(1900, "Piotrek", "gram dziś wieczór od 20:00"),
            _make_history_message(1901, "Bartek", "ok, dołączę"),
            _make_history_message(1902, "Piotrek", "zapraszam wszystkich"),
        ]
    )
    user_messages = [
        "[id:2000] [2026-05-31 14:00:00] Marek: hej, co gadaliście wcześniej? o czym była rozmowa?"
    ]

    result = await client.complete(user_messages, channel)

    assert _load_context_was_called(result), (
        f"Expected load_context to be called. LLM response: {result.output}"
    )


async def test_load_context_called_when_asked_to_remind_what_user_wrote(
    client: LLMClient,
) -> None:
    """Bot fetches history when asked to recall what a specific person wrote."""
    channel = _make_channel(
        [
            _make_history_message(2900, "Tomek", "event zaczynamy o 19:00 w sobotę"),
            _make_history_message(2901, "Tomek", "zapis przez formularz na discordzie"),
            _make_history_message(2902, "Ania", "super, zapisuję się"),
        ]
    )
    user_messages = [
        "[id:3000] [2026-05-31 15:30:00] Kasia: hej, możesz mi przypomnieć co Tomek pisał o evencie? przegapiłam"
    ]

    result = await client.complete(user_messages, channel)

    assert _load_context_was_called(result), (
        f"Expected load_context to be called. LLM response: {result.output}"
    )


async def test_load_context_called_to_summarize_channel_discussion(
    client: LLMClient,
) -> None:
    """Bot fetches history when asked to summarize the recent discussion."""
    channel = _make_channel(
        [
            _make_history_message(3900, "Bartek", "co myślicie o nowym sezonie Apex?"),
            _make_history_message(3901, "Marek", "słaby, matchmaking zepsuty"),
            _make_history_message(3902, "Kasia", "zgadzam się, ranki nie mają sensu"),
            _make_history_message(3903, "Piotrek", "ale nowa legenda jest ok"),
            _make_history_message(3904, "Bartek", "racja, Conduit jest fajna"),
        ]
    )
    user_messages = [
        "[id:4000] [2026-05-31 16:00:00] Ania: hej, właśnie weszłam — streść mi ostatnią dyskusję na kanale"
    ]

    result = await client.complete(user_messages, channel)

    assert _load_context_was_called(result), (
        f"Expected load_context to be called. LLM response: {result.output}"
    )


async def test_load_context_called_for_implicit_context_reference(
    client: LLMClient,
) -> None:
    """Bot fetches history when user implicitly refers to something decided earlier."""
    channel = _make_channel(
        [
            _make_history_message(
                4900, "Marek", "dobra, gramy o 21:00 na serwerze TeamSpeak"
            ),
            _make_history_message(4901, "Piotrek", "ok, będę"),
            _make_history_message(4902, "Bartek", "ja też"),
        ]
    )
    user_messages = [
        "[id:5000] [2026-05-31 17:00:00] Kasia: a co w końcu ustaliliście? o której i gdzie?"
    ]

    result = await client.complete(user_messages, channel)

    assert _load_context_was_called(result), (
        f"Expected load_context to be called. LLM response: {result.output}"
    )
