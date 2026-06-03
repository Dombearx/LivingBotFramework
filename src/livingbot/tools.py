from dataclasses import dataclass
from datetime import datetime
from typing import Annotated

import discord
from pydantic import Field
from pydantic_ai import RunContext

from livingbot.calendar import CalendarStore, PlanEntry
from livingbot.inventory import InventoryItem, InventoryStore


@dataclass
class BotDeps:
    channel: discord.abc.Messageable
    calendar_store: CalendarStore
    inventory_store: InventoryStore


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
    note: str = "",
) -> str:
    """Add something to your own calendar, e.g. a gym session or a multi-day trip.
    start and end are datetimes; location is where you physically are during it.
    Use this whenever you decide to do something that changes where you are or how
    your time is spent. Returns the new entry's id."""
    calendar = ctx.deps.calendar_store.load()
    entry = PlanEntry(
        activity=activity, location=location, start=start, end=end, note=note
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


async def add_item(ctx: RunContext[BotDeps], name: str, description: str = "") -> str:
    """Add a specific item you now own to your inventory, e.g. when you buy, are given
    or make something particular like a white skirt with red dots or a swimming suit.
    Only track special or specific belongings — assume you always have ordinary basics
    like everyday clothes, food and toiletries, and do not add those. Returns the new
    item's id."""
    item = InventoryItem(name=name, description=description)
    await ctx.deps.inventory_store.add(item)
    return f"Added [id:{item.id}] {item.name} to your inventory."


async def remove_item(ctx: RunContext[BotDeps], item_id: str) -> str:
    """Remove an item from your inventory by its id, e.g. when you use it up, lose it or
    give it away. The id is shown next to each item in your belongings."""
    if await ctx.deps.inventory_store.remove(item_id):
        return f"Removed item {item_id} from your inventory."
    return f"No inventory item with id {item_id}."


async def search_inventory(
    ctx: RunContext[BotDeps],
    query: Annotated[str, Field(min_length=1)],
    n: Annotated[int, Field(ge=1, le=20)] = 5,
) -> str:
    """Search your inventory for items related to a need or situation, described in
    natural language, e.g. "something for the swimming pool" or "a festive outfit".
    Returns up to n best-matching items by meaning, not just exact words. Use this to
    check whether you own something suitable before deciding what to do or say."""
    items = await ctx.deps.inventory_store.search(query, limit=n)
    if not items:
        return "Your inventory is empty."
    return "\n".join(
        f"[id:{item.id}] {item.name}"
        + (f" — {item.description}" if item.description else "")
        for item in items
    )
