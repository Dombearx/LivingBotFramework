import os

from openai.types.shared import ReasoningEffort
from pydantic_ai.models.openai import OpenAIChatModel, OpenAIChatModelSettings
from pydantic_ai.providers.openai import OpenAIProvider

DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"

CHAT_MODEL = "openai/gpt-5.6-terra"
WEEK_PLANNER_MODEL = "openai/gpt-5-nano"
# Her stories are prose the chat agent later retells almost verbatim, and one week's
# planning produces exactly one of them, so quality is worth far more here than price.
STORY_GENERATOR_MODEL = "openai/gpt-5.6-terra"
# Runs on every reply, once per participant, and its judgements are fed straight back
# into the chat agent's prompt — the highest-volume side agent, so it stays cheap.
RELATION_UPDATER_MODEL = "openai/gpt-5.4-nano"
# This judge only weighs her stated timing ("next time I'm at my computer" vs. how
# much time has actually passed) and whether interjecting now would read as natural.
# The check_after mechanism keeps it to a handful of calls per promise, so the extra
# cost of the stronger model is immaterial.
COMMITMENT_TIMING_MODEL = "openai/gpt-5.6-luna"
PROMPT_ENHANCER_MODEL = "openai/gpt-5-nano"
# Names what her last few messages share at the end, once per reply. It reads four
# short messages and answers with a phrase, so the cheapest model covers it.
REPLY_SHAPE_MODEL = "openai/gpt-5.4-nano"


def _api_key() -> str:
    return os.environ["OPENROUTER_API_KEY"]


def _base_url() -> str:
    return os.environ.get("OPENROUTER_BASE_URL", DEFAULT_BASE_URL)


def build_chat_model(
    model_name: str, reasoning_effort: ReasoningEffort | None = None
) -> OpenAIChatModel:
    settings = (
        OpenAIChatModelSettings(openai_reasoning_effort=reasoning_effort)
        if reasoning_effort is not None
        else None
    )
    return OpenAIChatModel(
        model_name,
        provider=OpenAIProvider(base_url=_base_url(), api_key=_api_key()),
        settings=settings,
    )
