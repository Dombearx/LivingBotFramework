from pydantic import BaseModel
from pydantic_ai import Agent


class LLMConfig(BaseModel):
    model: str
    system_prompt: str


class LLMClient:
    def __init__(self, config: LLMConfig) -> None:
        self._agent: Agent[None, str] = Agent(
            config.model, system_prompt=config.system_prompt
        )

    async def complete(self, user_messages: list[str]) -> str:
        result = await self._agent.run("\n".join(user_messages))
        return result.output
