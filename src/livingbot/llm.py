import discord
from pydantic import BaseModel
from pydantic_ai import Agent, AgentRunResult

from livingbot.relations import Relation
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
        relation: Relation | None = None,
    ) -> AgentRunResult[str]:
        deps = BotDeps(channel=channel)
        prompt = "\n".join(user_messages)
        if memories:
            memory_block = "\n".join(f"- {m}" for m in memories)
            prompt = f"What I remember:\n{memory_block}\n\n{prompt}"
        if relation:
            prompt = _build_relation_block(relation) + prompt
        return await self._agent.run(prompt, deps=deps)


def _build_relation_block(relation: Relation) -> str:
    parts: list[str] = [
        f"My relationship with this person (attitude: {relation.attitude}/100):"
    ]
    if relation.most_important_memory:
        parts.append(f"- Most important memory: {relation.most_important_memory}")
    if relation.inside_jokes:
        parts.append(f"- Inside jokes: {', '.join(relation.inside_jokes)}")
    if relation.topics_of_interest:
        topics = ", ".join(relation.topics_of_interest)
        parts.append(
            f"- Their interests: {topics}"
            " (only reference these if they are clearly relevant to what they just said)"
        )
    return "\n".join(parts) + "\n\n"
