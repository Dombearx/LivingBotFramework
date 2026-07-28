import logging
from typing import Self

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel

from livingbot import llm_config
from livingbot.prompts import COMMITMENT_TIMING_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


class CommitmentTimingDecision(BaseModel):
    reason: str = Field(max_length=300)
    should_follow_up: bool = False
    retry_in_hours: float | None = Field(default=None, ge=0.5, le=336.0)


class CommitmentTimingJudge:
    @classmethod
    def create(cls) -> Self:
        return cls(llm_config.build_chat_model(llm_config.COMMITMENT_TIMING_MODEL))

    def __init__(self, model: OpenAIChatModel) -> None:
        self._agent: Agent[None, CommitmentTimingDecision] = Agent(
            model,
            name="commitment_timing",
            instructions=COMMITMENT_TIMING_SYSTEM_PROMPT,
            output_type=CommitmentTimingDecision,
        )

    async def decide(self, context: str) -> CommitmentTimingDecision | None:
        try:
            result = await self._agent.run(context)
        except Exception:
            logger.exception("Failed to decide commitment follow-up timing")
            return None
        return result.output
