import os

from openai import AsyncOpenAI
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"

CHAT_MODEL = "openai/gpt-5.4-mini"
WEEK_PLANNER_MODEL = "openai/gpt-5-nano"
STORY_GENERATOR_MODEL = "openai/gpt-5-nano"
RELATION_UPDATER_MODEL = "openai/gpt-5-nano"
SPONTANEOUS_MESSENGER_MODEL = "openai/gpt-5-nano"
PROMPT_ENHANCER_MODEL = "openai/gpt-5-nano"


def _api_key() -> str:
    return os.environ["OPENROUTER_API_KEY"]


def _base_url() -> str:
    return os.environ.get("OPENROUTER_BASE_URL", DEFAULT_BASE_URL)


def build_chat_model(model_name: str) -> OpenAIChatModel:
    return OpenAIChatModel(
        model_name,
        provider=OpenAIProvider(base_url=_base_url(), api_key=_api_key()),
    )


def build_openai_client() -> AsyncOpenAI:
    return AsyncOpenAI(base_url=_base_url(), api_key=_api_key())
