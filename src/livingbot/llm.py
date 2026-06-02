import discord
from pydantic import BaseModel
from pydantic_ai import Agent, AgentRunResult

from livingbot.tools import BotDeps, load_context


class LLMConfig(BaseModel):
    model: str
    system_prompt: str


class LLMClient:
    def __init__(self, config: LLMConfig) -> None:
        self._config = config
        self._agent: Agent[BotDeps, str] = Agent(
            config.model,
            system_prompt=config.system_prompt,
            tools=[load_context],
        )

    async def complete(
        self,
        user_messages: list[str],
        channel: discord.abc.Messageable,
        memories: list[str] | None = None,
    ) -> AgentRunResult[str]:
        deps = BotDeps(channel=channel)
        prompt = "\n".join(user_messages)
        if memories:
            memory_block = "\n".join(f"- {m}" for m in memories)
            prompt = f"What I remember:\n{memory_block}\n\n{prompt}"
        return await self._agent.run(prompt, deps=deps)
