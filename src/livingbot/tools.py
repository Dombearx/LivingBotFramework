from dataclasses import dataclass
from typing import Annotated

import discord
from pydantic import Field
from pydantic_ai import RunContext


@dataclass
class BotDeps:
    channel: discord.abc.Messageable
    anchor_message_id: int


async def load_context(
    ctx: RunContext[BotDeps],
    n: Annotated[int, Field(ge=1, le=100)],
    before_message_id: int | None = None,
) -> str:
    """Load N previous messages (1–100) before a given message ID.
    Omit before_message_id to start before the current conversation.
    Each returned message includes its ID — pass the oldest returned ID
    as before_message_id in the next call to go further back."""
    before_id = (
        before_message_id
        if before_message_id is not None
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
    return "\n".join(
        f"[id:{msg.id}] [{msg.created_at.strftime('%Y-%m-%d %H:%M:%S')}] {msg.author.display_name}: {msg.content}"
        for msg in reversed(messages)
    )
