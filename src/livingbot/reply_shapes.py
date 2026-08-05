import logging
from typing import Self

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel

from livingbot import llm_config
from livingbot.prompts import REPLY_SHAPE_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


class ReplyShape(BaseModel):
    shared_ending: str | None = Field(default=None, max_length=200)


class ReplyShapeLabeller:
    """Names what her own recent messages have in common at the end.

    Showing her the messages and asking her to notice does not work — measured, she
    ends a reply the same way as the four in front of her at exactly the rate she
    would have anyway. This does the noticing for her, so the prompt can state the
    conclusion instead of hoping she draws it.
    """

    @classmethod
    def create(cls) -> Self:
        return cls(llm_config.build_chat_model(llm_config.REPLY_SHAPE_MODEL))

    def __init__(self, model: OpenAIChatModel) -> None:
        self._agent: Agent[None, ReplyShape] = Agent(
            model,
            name="reply_shape",
            instructions=REPLY_SHAPE_SYSTEM_PROMPT,
            output_type=ReplyShape,
        )

    async def label(self, messages: list[str]) -> str | None:
        if len(messages) < 2:
            return None
        numbered = "\n".join(f"{i}. {m}" for i, m in enumerate(messages, 1))
        try:
            result = await self._agent.run(numbered)
        except Exception:
            logger.exception("Failed to label the shape of her recent replies")
            return None
        return result.output.shared_ending
