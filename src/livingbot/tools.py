from dataclasses import dataclass
from typing import Annotated

import discord
from pydantic import Field
from pydantic_ai import RunContext


@dataclass
class BotDeps:
    channel: discord.abc.Messageable


async def load_context(
    ctx: RunContext[BotDeps],
    n: Annotated[int, Field(ge=1, le=100)],
    before_message_id: int,
) -> str:
    """Load N previous messages (1–100) before the given message ID.
    Use an ID from the current conversation or a previous tool call result.
    Each returned message includes its ID for use in subsequent calls."""
    messages: list[discord.Message] = [
        msg
        async for msg in ctx.deps.channel.history(
            limit=n, before=discord.Object(id=before_message_id)
        )
    ]
    if not messages:
        return "No earlier messages available."
    return "\n".join(
        f"[id:{msg.id}] [{msg.created_at.strftime('%Y-%m-%d %H:%M:%S')}] {msg.author.display_name}: {msg.content}"
        for msg in reversed(messages)
    )
