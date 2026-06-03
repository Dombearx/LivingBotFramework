from dataclasses import dataclass
from datetime import datetime
from typing import Annotated

import discord
from pydantic import Field
from pydantic_ai import RunContext

from livingbot.calendar import Busyness, CalendarStore, PlanEntry


@dataclass
class BotDeps:
    channel: discord.abc.Messageable
    calendar_store: CalendarStore


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


async def add_plan(
    ctx: RunContext[BotDeps],
    activity: str,
    location: str,
    start: datetime,
    end: datetime,
    busyness: Busyness = Busyness.moderate,
    note: str = "",
) -> str:
    """Add something to your own calendar, e.g. a gym session or a multi-day trip.
    start and end are datetimes; location is where you physically are during it.
    busyness is how unreachable it makes you: "deep" when you are fully absorbed and
    your phone is away (gym, cinema), "moderate" when you can glance at it now and
    then, "light" when you are barely occupied (errands, visiting parents).
    Use this whenever you decide to do something that changes where you are or how
    your time is spent. Returns the new entry's id."""
    calendar = ctx.deps.calendar_store.load()
    entry = PlanEntry(
        activity=activity,
        location=location,
        start=start,
        end=end,
        busyness=busyness,
        note=note,
    )
    calendar.entries.append(entry)
    ctx.deps.calendar_store.save(calendar)
    return f"Added [id:{entry.id}] {activity} @ {location} from {start} to {end}."


async def remove_plan(ctx: RunContext[BotDeps], entry_id: str) -> str:
    """Remove an entry from your own calendar by its id, e.g. when plans change or
    you cancel something. The id is shown next to each entry in your calendar."""
    calendar = ctx.deps.calendar_store.load()
    remaining = [e for e in calendar.entries if e.id != entry_id]
    if len(remaining) == len(calendar.entries):
        return f"No calendar entry with id {entry_id}."
    calendar.entries = remaining
    ctx.deps.calendar_store.save(calendar)
    return f"Removed calendar entry {entry_id}."
