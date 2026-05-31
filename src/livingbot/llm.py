from dataclasses import dataclass
from typing import Annotated

import discord
from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext


@dataclass
class _ContextState:
    channel: discord.abc.Messageable
    anchor_message_id: int
    cursor: int | None = None


class LLMConfig(BaseModel):
    model: str
    system_prompt: str


class LLMClient:
    def __init__(self, config: LLMConfig) -> None:
        self._agent: Agent[_ContextState, str] = Agent(
            config.model, system_prompt=config.system_prompt
        )

        @self._agent.tool
        async def load_context(
            ctx: RunContext[_ContextState],
            n: Annotated[int, Field(ge=1, le=100)],
        ) -> str:
            """Load N previous messages sent before the current conversation.
            Each call fetches the next N messages further back in history.
            Messages are returned in chronological order with timestamp and author.
            Call repeatedly to load more context if needed."""
            before_id = (
                ctx.deps.cursor
                if ctx.deps.cursor is not None
                else ctx.deps.anchor_message_id
            )
            messages: list[discord.Message] = [
                msg
                async for msg in ctx.deps.channel.history(
                    limit=n, before=discord.Object(id=before_id)
                )
            ]
            if not messages:
                return "No earlier messages available."
            ctx.deps.cursor = messages[-1].id
            return "\n".join(
                f"[{msg.created_at.strftime('%Y-%m-%d %H:%M:%S')}] {msg.author.display_name}: {msg.content}"
                for msg in reversed(messages)
            )

    async def complete(
        self,
        user_messages: list[str],
        channel: discord.abc.Messageable,
        anchor_message_id: int,
    ) -> str:
        deps = _ContextState(channel=channel, anchor_message_id=anchor_message_id)
        result = await self._agent.run("\n".join(user_messages), deps=deps)
        return result.output
