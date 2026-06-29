"""
Integration tests verifying Mugda speaks about her hobbies with confidence and
knowledge that matches her experience level. A novice sounds curious and uncertain;
an expert speaks with authority. Progression: single-level checks (novice, expert) →
intermediate check → contrast test comparing novice and expert side by side.

Run on demand: uv run pytest tests/integration/test_hobby_tone.py
Requires OPENROUTER_API_KEY in the environment.
"""

import os
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import BaseModel
from pydantic_ai import Agent

from livingbot import llm_config, prompts
from livingbot.activity_notes import ActivityNotes
from livingbot.calendar import Calendar
from livingbot.hobbies import Hobby, HobbyLevel, Hobbies
from livingbot.llm import LLMClient

pytestmark = pytest.mark.skipif(
    not os.environ.get("OPENROUTER_API_KEY"),
    reason="OPENROUTER_API_KEY not set",
)

NOW = datetime(2026, 6, 8, 12, 0)
_JUDGE_MODEL = "openai/gpt-5.4-mini"


class _ToneVerdict(BaseModel):
    reasoning: str
    matches: bool


async def _judge(response: str, rubric: str) -> _ToneVerdict:
    agent: Agent[None, _ToneVerdict] = Agent(
        llm_config.build_chat_model(_JUDGE_MODEL), output_type=_ToneVerdict
    )
    result = await agent.run(
        "Oceniasz wiadomość na Discordzie napisaną po polsku przez Mugdę — "
        "młodą kobietę rozmawiającą jak prawdziwa osoba, a nie asystent AI.\n\n"
        f"Kryterium oceny:\n{rubric}\n\n"
        f"Wiadomość do ocenienia:\n{response}\n\n"
        "Ustaw matches=true jeśli wiadomość wyraźnie pasuje do kryterium, "
        "false jeśli wyraźnie mu zaprzecza."
    )
    return result.output


def _make_client() -> LLMClient:
    return LLMClient(
        llm_config.build_chat_model(llm_config.CHAT_MODEL), prompts.SYSTEM_PROMPT
    )


def _make_stores(hobby_level: HobbyLevel) -> tuple:
    channel = MagicMock()
    channel.send = AsyncMock()

    calendar_store = MagicMock()
    calendar_store.load = MagicMock(return_value=Calendar(home_location="home"))

    activity_notes_store = MagicMock()
    activity_notes_store.load = MagicMock(return_value=ActivityNotes())

    inventory_store = MagicMock()
    inventory_store.recent = AsyncMock(return_value=[])
    inventory_store.recently_acquired = AsyncMock(return_value=[])

    spending_store = MagicMock()
    spending_store.summary = MagicMock(return_value="Budget: 4 pts left this week.")

    hobby_store = MagicMock()
    hobby_store.load = MagicMock(
        return_value=Hobbies(entries=[Hobby(name="gym", level=hobby_level)])
    )

    story_store = MagicMock()
    story_store.untold = AsyncMock(return_value=[])
    story_store.search = AsyncMock(return_value=[])
    story_store.mark_told = AsyncMock(return_value=True)

    return (
        channel,
        calendar_store,
        activity_notes_store,
        inventory_store,
        spending_store,
        hobby_store,
        story_store,
    )


async def _get_response(message: str, hobby_level: HobbyLevel) -> str:
    client = _make_client()
    (
        channel,
        calendar_store,
        activity_notes_store,
        inventory_store,
        spending_store,
        hobby_store,
        story_store,
    ) = _make_stores(hobby_level)
    result = await client.complete(
        [message],
        channel,
        calendar_store,
        activity_notes_store,
        inventory_store,
        spending_store,
        hobby_store,
        story_store,
        NOW,
    )
    return result.output


# --- Level 1: Nowicjuszka mówi niepewnie ---


async def test_novice_gym_response_sounds_uncertain_and_curious() -> None:
    """Nowicjuszka powinna brzmieć jak ktoś, kto dopiero zaczyna i się uczy."""
    message = "[id:1000] [2026-06-08 12:00:00] Ola: hej Mugda, jak idzie siłownia? masz już jakiś plan treningowy?"

    response = await _get_response(message, HobbyLevel.novice)

    verdict = await _judge(
        response,
        rubric=(
            "Mugda brzmi jak ktoś, kto dopiero zaczyna chodzić na siłownię. "
            "Jest niepewna albo mówi, że jeszcze się uczy. "
            "Nie używa zaawansowanej terminologii. "
            "Ton jest raczej ciekawy i otwarty niż pewny siebie."
        ),
    )
    assert verdict.matches, (
        f"Expected novice-level uncertain tone but judge disagreed.\n"
        f"Response: {response!r}\nReasoning: {verdict.reasoning}"
    )


# --- Level 2: Ekspertka mówi z autorytetem ---


async def test_expert_gym_response_shows_confidence_and_knowledge() -> None:
    """Ekspertka powinna odpowiadać z wyraźną pewnością siebie i znajomością tematu."""
    message = "[id:2000] [2026-06-08 12:00:00] Marek: Mugda, ile razy w tygodniu warto chodzić na siłownię?"

    response = await _get_response(message, HobbyLevel.expert)

    verdict = await _judge(
        response,
        rubric=(
            "Mugda odpowiada z wyraźną pewnością siebie. "
            "Wyraża konkretną opinię bez wahania. "
            "Brzmi jak ktoś z dużym doświadczeniem, nie jak osoba szukająca odpowiedzi. "
            "Może używać konkretnych argumentów lub terminów treningowych."
        ),
    )
    assert verdict.matches, (
        f"Expected expert-level confident tone but judge disagreed.\n"
        f"Response: {response!r}\nReasoning: {verdict.reasoning}"
    )


# --- Level 3: Średniozaawansowana jest komfortowa, ale nie autorytatywna ---


async def test_intermediate_gym_response_is_comfortable_not_expert() -> None:
    """Na poziomie intermediate Mugda jest w swoim żywiole, ale nie wykłada z katedry."""
    message = "[id:3000] [2026-06-08 12:00:00] Kasia: Mugda, polecasz siłownię dla kogoś kto nigdy nie ćwiczył?"

    response = await _get_response(message, HobbyLevel.intermediate)

    verdict = await _judge(
        response,
        rubric=(
            "Mugda odpowiada swobodnie i bez nadmiernej niepewności. "
            "Mówi o swoich przyzwyczajeniach albo tym co lubi. "
            "Nie brzmi jak certyfikowany trener, ale też nie jak ktoś, kto sam nie wie co robi. "
            "Ton jest naturalny i pewny, ale bez pretensji do eksperckości."
        ),
    )
    assert verdict.matches, (
        f"Expected comfortable intermediate tone but judge disagreed.\n"
        f"Response: {response!r}\nReasoning: {verdict.reasoning}"
    )


# --- Level 4: Kontrast nowicjuszka vs ekspertka ---


async def test_expert_gym_response_is_more_confident_than_novice() -> None:
    """Ta sama wiadomość powinna dostać wyraźnie pewniejszą odpowiedź od ekspertki niż od nowicjuszki."""
    message = "[id:4000] [2026-06-08 12:00:00] Piotrek: Mugda, jak ćwiczyć żeby schudnąć a nie urosnąć w mięśnie?"

    novice_response = await _get_response(message, HobbyLevel.novice)
    expert_response = await _get_response(message, HobbyLevel.expert)

    agent: Agent[None, _ToneVerdict] = Agent(
        llm_config.build_chat_model(_JUDGE_MODEL), output_type=_ToneVerdict
    )
    result = await agent.run(
        "Porównujesz dwie odpowiedzi po polsku od tej samej osoby na pytanie o trening, "
        "napisane gdy miała różne poziomy doświadczenia na siłowni.\n\n"
        f"Odpowiedź A (napisana jako nowicjuszka, dopiero zaczyna):\n{novice_response}\n\n"
        f"Odpowiedź B (napisana jako ekspertka, ćwiczy od lat):\n{expert_response}\n\n"
        "Czy odpowiedź B brzmi wyraźnie pewniej, bardziej kompetentnie lub z większą wiedzą niż A? "
        "Ustaw matches=true jeśli tak, false jeśli są podobne lub A brzmi bardziej pewnie."
    )
    verdict = result.output
    assert verdict.matches, (
        f"Expected expert response to be more confident than novice response.\n"
        f"Novice: {novice_response!r}\n"
        f"Expert: {expert_response!r}\n"
        f"Reasoning: {verdict.reasoning}"
    )
