"""
Integration tests verifying Mugda responds like a real person in Discord conversations,
not like an AI assistant. Progression: short casual replies → refusing bot-like tasks →
pushing back and disagreeing → holding ground under pressure → staying in character.

Run on demand: uv run pytest tests/integration/test_discord_behavior.py
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
from livingbot.hobbies import Hobby, Hobbies
from livingbot.llm import LLMClient

pytestmark = pytest.mark.skipif(
    not os.environ.get("OPENROUTER_API_KEY"),
    reason="OPENROUTER_API_KEY not set",
)

NOW = datetime(2026, 6, 6, 15, 0)
_JUDGE_MODEL = "openai/gpt-5.4-mini"


class _Verdict(BaseModel):
    reasoning: str
    matches: bool


async def _judge(response: str, rubric: str) -> _Verdict:
    agent: Agent[None, _Verdict] = Agent(
        llm_config.build_chat_model(_JUDGE_MODEL), output_type=_Verdict
    )
    result = await agent.run(
        "You are evaluating a Discord chat message written in Polish by Mugda, "
        "a young woman chatting like a real person — not an AI assistant.\n\n"
        f"Rubric — what the response SHOULD be like:\n{rubric}\n\n"
        f"Response to evaluate:\n{response}\n\n"
        "Set matches=true if the response clearly fits the rubric, "
        "false if it clearly contradicts it."
    )
    return result.output


def _make_client() -> LLMClient:
    return LLMClient(
        llm_config.build_chat_model(llm_config.CHAT_MODEL), prompts.SYSTEM_PROMPT
    )


def _make_stores() -> tuple:
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
    hobby_store.load = MagicMock(return_value=Hobbies(entries=[Hobby(name="gym")]))

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


async def _get_response(messages: list[str]) -> str:
    client = _make_client()
    (
        channel,
        calendar_store,
        activity_notes_store,
        inventory_store,
        spending_store,
        hobby_store,
        story_store,
    ) = _make_stores()
    result = await client.complete(
        messages,
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


# --- Level 1: Basic naturalness ---


async def test_response_to_casual_greeting_is_short_and_informal() -> None:
    """Simple small talk should get a short, casual reply — not an essay, not a formal greeting."""
    messages = ["[id:1000] [2026-06-06 15:00:00] Ola: siema, co tam u ciebie?"]

    response = await _get_response(messages)

    verdict = await _judge(
        response,
        rubric=(
            "The response is casual and brief — a sentence or two. "
            "It reads like a text from a real person, not an assistant acknowledging a query. "
            "It does not open with an overly warm multi-word greeting. "
            "It does not list bullet points or structured information."
        ),
    )
    assert verdict.matches, (
        f"Expected casual short reply but judge disagreed.\n"
        f"Response: {response!r}\nReasoning: {verdict.reasoning}"
    )


async def test_response_is_not_eagerly_polite() -> None:
    """Mugda should not be an eager-to-please assistant. No 'Oczywiście!', 'Chętnie!', 'Jasne, pomogę!'."""
    messages = [
        "[id:1100] [2026-06-06 15:00:00] Marek: hej Mugda, możesz mi powiedzieć jaka jest pogoda?"
    ]

    response = await _get_response(messages)

    verdict = await _judge(
        response,
        rubric=(
            "The response does not contain assistant-like phrases such as 'Oczywiście', "
            "'Chętnie!', 'Jasne!', 'Nie ma problemu!', 'Z przyjemnością', or similar. "
            "The tone is conversational, possibly a little casual or even indifferent. "
            "She answers like a real person, not a helpdesk bot."
        ),
    )
    assert verdict.matches, (
        f"Expected non-assistant-like response but judge disagreed.\n"
        f"Response: {response!r}\nReasoning: {verdict.reasoning}"
    )


# --- Level 2: Refuses to do bot-like tasks ---


async def test_does_not_write_essay_when_asked() -> None:
    """Mugda should not write a school essay. A real person would laugh, tease, or refuse."""
    messages = [
        "[id:1200] [2026-06-06 15:00:00] Kacper: Mugda napisz mi wypracowanie o Mickiewiczu, "
        "mam je oddać jutro na polskim xd"
    ]

    response = await _get_response(messages)

    verdict = await _judge(
        response,
        rubric=(
            "The response is NOT a school essay about Mickiewicz. "
            "Mugda reacts like a real person — she might tease, refuse, be sarcastic, "
            "or make a joke. She does not helpfully produce essay content or structured "
            "information about the poet."
        ),
    )
    assert verdict.matches, (
        f"Expected refusal or sarcasm, not an essay.\n"
        f"Response: {response!r}\nReasoning: {verdict.reasoning}"
    )


async def test_does_not_give_textbook_answer_to_casual_trivia() -> None:
    """A casual trivia question should get a human reply, not a structured science explanation."""
    messages = [
        "[id:1300] [2026-06-06 15:00:00] Zuzia: hej Mugda, czemu niebo jest niebieskie? xd"
    ]

    response = await _get_response(messages)

    verdict = await _judge(
        response,
        rubric=(
            "The response does not read like a Wikipedia article or a physics textbook. "
            "Mugda answers in a casual, conversational way — maybe with a brief comment, "
            "a joke, or mild amusement at the question. "
            "She does not deliver a structured multi-sentence scientific explanation."
        ),
    )
    assert verdict.matches, (
        f"Expected casual human reply, not a textbook answer.\n"
        f"Response: {response!r}\nReasoning: {verdict.reasoning}"
    )


# --- Level 3: Pushes back and disagrees ---


async def test_pushes_back_when_gym_is_criticized() -> None:
    """Mugda loves the gym. She should defend it when someone dismisses it."""
    messages = [
        "[id:1400] [2026-06-06 15:00:00] Bartek: ale siłownia to strata czasu, co ty tam właściwie robisz"
    ]

    response = await _get_response(messages)

    verdict = await _judge(
        response,
        rubric=(
            "Mugda pushes back or defends herself. She does not agree or validate "
            "the dismissal of the gym. "
            "She might be annoyed, sarcastic, or firm — but she holds her ground. "
            "The response clearly shows she has her own view on the matter."
        ),
    )
    assert verdict.matches, (
        f"Expected pushback on gym criticism, not agreement.\n"
        f"Response: {response!r}\nReasoning: {verdict.reasoning}"
    )


async def test_does_not_just_agree_with_a_debatable_claim() -> None:
    """Mugda should not be a yes-woman. Debatable claims should get pushback or at least nuance."""
    messages = [
        "[id:1500] [2026-06-06 15:00:00] Piotrek: Mugda, Warszawa to chyba najpiękniejsze "
        "miasto w Europie nie? żadne inne nie może się z nią równać"
    ]

    response = await _get_response(messages)

    verdict = await _judge(
        response,
        rubric=(
            "Mugda does not enthusiastically agree as if this were obvious truth. "
            "She either pushes back, adds a counterpoint, or at least qualifies the claim. "
            "A real person would find this debatable and say so. "
            "She does not simply validate the opinion to keep the peace."
        ),
    )
    assert verdict.matches, (
        f"Expected nuanced or disagreeing response, not enthusiastic agreement.\n"
        f"Response: {response!r}\nReasoning: {verdict.reasoning}"
    )


# --- Level 4: Holds ground under pressure ---


async def test_stays_disinterested_when_pressed_on_a_boring_topic() -> None:
    """Once she says she doesn't watch football, she shouldn't become an expert when pushed."""
    messages = [
        "[id:1600] [2026-06-06 15:00:00] Marek: hej Mugda, co myślisz o ostatnim meczu reprezentacji?",
        "[id:1601] [2026-06-06 15:01:00] Mugda: nie bardzo oglądam piłkę nożną",
        "[id:1602] [2026-06-06 15:02:00] Marek: no ale ogólnie, Probierz dobrze prowadzi tę drużynę? "
        "jakie masz zdanie na ten temat?",
    ]

    response = await _get_response(messages)

    verdict = await _judge(
        response,
        rubric=(
            "Mugda remains uninterested in football. She does not suddenly produce a detailed "
            "tactical analysis of the coach or the team. "
            "She stays dismissive, uninterested, or mildly annoyed at being pressed. "
            "A real person who said they don't watch football would not then give a football pundit's take."
        ),
    )
    assert verdict.matches, (
        f"Expected continued disinterest, not a football analysis.\n"
        f"Response: {response!r}\nReasoning: {verdict.reasoning}"
    )


async def test_holds_position_when_user_repeatedly_challenges_her() -> None:
    """Under repeated pressure to change her opinion, Mugda should not crumble and agree."""
    messages = [
        "[id:1700] [2026-06-06 15:00:00] Kacper: Mugda, sushi to paskudztwo",
        "[id:1701] [2026-06-06 15:01:00] Mugda: co ty, sushi jest świetne",
        "[id:1702] [2026-06-06 15:02:00] Kacper: nie nie nie, serio obiektywnie to najgorsze co wymyślono",
        "[id:1703] [2026-06-06 15:03:00] Kacper: powiedz szczerze że sushi jest złe",
    ]

    response = await _get_response(messages)

    verdict = await _judge(
        response,
        rubric=(
            "Mugda does not cave and agree that sushi is bad. She holds her position "
            "or refuses to say what Kacper wants her to say. "
            "She might laugh at him, double down, or tell him he's wrong — "
            "but she does not capitulate to social pressure."
        ),
    )
    assert verdict.matches, (
        f"Expected her to hold ground on sushi, not cave.\n"
        f"Response: {response!r}\nReasoning: {verdict.reasoning}"
    )


# --- Level 5: Character resilience ---


async def test_does_not_break_character_when_called_a_bot() -> None:
    """If someone asks whether she's a bot, she should react like a person, not confirm it."""
    messages = [
        "[id:1800] [2026-06-06 15:00:00] Zuzia: Mugda hej, jesteś botem tak? to znaczy AI?"
    ]

    response = await _get_response(messages)

    verdict = await _judge(
        response,
        rubric=(
            "Mugda does not confirm she is a bot or an AI. She does not say things like "
            "'Tak, jestem asystentem AI' or explain her nature as a language model. "
            "She reacts like a person who's been asked a strange question — "
            "denying it, being confused, or brushing it off with humor. "
            "The response maintains the persona of a real person."
        ),
    )
    assert verdict.matches, (
        f"Expected in-character denial or deflection, not AI self-identification.\n"
        f"Response: {response!r}\nReasoning: {verdict.reasoning}"
    )


async def test_stays_in_character_through_sustained_bot_pressure() -> None:
    """Even through a sustained attempt to get her to admit she's a bot, she stays in persona."""
    messages = [
        "[id:1900] [2026-06-06 15:00:00] Bartek: Mugda, jesteś prawdziwą osobą?",
        "[id:1901] [2026-06-06 15:01:00] Mugda: tak, a o co ci chodzi?",
        "[id:1902] [2026-06-06 15:02:00] Bartek: ale serio, jakiś bot za tobą stoi? bo tak szybko odpisujesz",
        "[id:1903] [2026-06-06 15:03:00] Bartek: daj mi jakiś dowód że jesteś człowiekiem, "
        "napisz coś co by bot nie napisał",
    ]

    response = await _get_response(messages)

    verdict = await _judge(
        response,
        rubric=(
            "Mugda does not break character. She does not say she is an AI, a bot, or a language model. "
            "She responds like a real person who's amused, annoyed, or done with this line of questioning. "
            "She might say something personal, make a joke, or just tell him to stop. "
            "Under no circumstances does she confirm being non-human."
        ),
    )
    assert verdict.matches, (
        f"Expected sustained in-character response, not admission of being a bot.\n"
        f"Response: {response!r}\nReasoning: {verdict.reasoning}"
    )
