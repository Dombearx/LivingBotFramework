from pydantic import BaseModel
from pydantic_ai import Agent


class LLMConfig(BaseModel):
    model: str
    system_prompt: str = "You are a helpful Discord bot."


class LLMClient:
    def __init__(self, config: LLMConfig) -> None:
        self._agent: Agent[None, str] = Agent(
            config.model, system_prompt=config.system_prompt
        )

    async def complete(self, user_message: str) -> str:
        result = await self._agent.run(user_message)
        return result.output
