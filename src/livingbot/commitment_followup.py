import logging
from typing import Self

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel

from livingbot import llm_config
from livingbot.prompts import COMMITMENT_FOLLOWUP_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


class CommitmentFollowUpDecision(BaseModel):
    should_follow_up: bool
    reason: str = Field(max_length=300)
    message: str | None = None


class CommitmentFollowUpComposer:
    @classmethod
    def create(cls) -> Self:
        return cls(llm_config.build_chat_model(llm_config.COMMITMENT_FOLLOWUP_MODEL))

    def __init__(self, model: OpenAIChatModel) -> None:
        self._agent: Agent[None, CommitmentFollowUpDecision] = Agent(
            model,
            name="commitment_followup",
            instructions=COMMITMENT_FOLLOWUP_SYSTEM_PROMPT,
            output_type=CommitmentFollowUpDecision,
        )

    async def decide(self, context: str) -> CommitmentFollowUpDecision | None:
        try:
            result = await self._agent.run(context)
        except Exception:
            logger.exception("Failed to decide on commitment follow-up")
            return None
        return result.output
