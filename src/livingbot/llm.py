import discord
from pydantic import BaseModel
from pydantic_ai import Agent

from livingbot.tools import BotDeps, load_context


class LLMConfig(BaseModel):
    model: str
    system_prompt: str


class LLMClient:
    def __init__(self, config: LLMConfig) -> None:
        self._agent: Agent[BotDeps, str] = Agent(
            config.model,
            system_prompt=config.system_prompt,
            tools=[load_context],
        )

    async def complete(
        self,
        user_messages: list[str],
        channel: discord.abc.Messageable,
        anchor_message_id: int,
    ) -> str:
        deps = BotDeps(channel=channel, anchor_message_id=anchor_message_id)
        result = await self._agent.run("\n".join(user_messages), deps=deps)
        return result.output
