import os

from openai.types.shared import ReasoningEffort
from pydantic_ai.models.openai import OpenAIChatModel, OpenAIChatModelSettings
from pydantic_ai.providers.openai import OpenAIProvider

DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"

CHAT_MODEL = "openai/gpt-5.4-mini"
WEEK_PLANNER_MODEL = "openai/gpt-5-nano"
STORY_GENERATOR_MODEL = "openai/gpt-5-nano"
RELATION_UPDATER_MODEL = "openai/gpt-5-nano"
SPONTANEOUS_MESSENGER_MODEL = "openai/gpt-5-nano"
# Deciding a follow-up means reading the conversation for whether the promise is
# already settled, then weighing her stated timing, then estimating the remaining
# wait. gpt-5-nano fumbled the first of those and chased promises she had already
# kept, so this judge gets the stronger model. The check_after mechanism keeps it
# to a handful of calls per promise, so the extra cost is immaterial.
COMMITMENT_FOLLOWUP_MODEL = "openai/gpt-5.4-mini"
PROMPT_ENHANCER_MODEL = "openai/gpt-5-nano"


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
