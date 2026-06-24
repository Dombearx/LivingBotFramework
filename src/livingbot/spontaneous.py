import logging
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel

from livingbot.prompts import SPONTANEOUS_MESSAGE_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


class SpontaneousState(BaseModel):
    next_post_at: datetime | None = None


class SpontaneousStore:
    def __init__(self, data_path: Path) -> None:
        self._path = data_path / "spontaneous.json"
        data_path.mkdir(parents=True, exist_ok=True)

    def load(self) -> SpontaneousState:
        if not self._path.exists():
            return SpontaneousState()
        return SpontaneousState.model_validate_json(self._path.read_text())

    def save(self, state: SpontaneousState) -> None:
        self._path.write_text(state.model_dump_json(indent=2))


class SpontaneousMessenger:
    def __init__(self, model: OpenAIChatModel) -> None:
        self._agent: Agent[None, str] = Agent(
            model, system_prompt=SPONTANEOUS_MESSAGE_SYSTEM_PROMPT
        )

    async def compose(self, context: str) -> str | None:
        try:
            result = await self._agent.run(context)
        except Exception:
            logger.exception("Failed to compose a spontaneous message")
            return None
        return result.output
