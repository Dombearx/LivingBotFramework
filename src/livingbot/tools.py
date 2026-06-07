from dataclasses import dataclass
from datetime import datetime
from typing import Annotated

import discord
from pydantic import Field
from pydantic_ai import RunContext

from livingbot.calendar import CalendarStore, PlanEntry
from livingbot.inventory import InventoryItem, InventoryStore
from livingbot.spending import POINT_COST, SpendCategory, SpendingStore


@dataclass
class BotDeps:
    channel: discord.abc.Messageable
    calendar_store: CalendarStore
    inventory_store: InventoryStore
    spending_store: SpendingStore
    photo_result: bytes | None = None


def format_message(message: discord.Message) -> str:
    timestamp = message.created_at.strftime("%Y-%m-%d %H:%M:%S")
    return (
        f"[id:{message.id}] [{timestamp}] "
        f"{message.author.display_name}: {message.content}"
    )


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
    return "\n".join(format_message(msg) for msg in reversed(messages))


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


async def check_budget(ctx: RunContext[BotDeps], category: SpendCategory) -> str:
    """Check whether your spending budget allows a purchase in this category.
    Categories and their point costs:
      trivial (0 pts) — coffee, bus ticket, small snack
      small   (1 pt)  — book, cosmetics, cheap accessory
      medium  (2 pts) — dress, shoes, gym pass, day trip
      large   (4 pts) — weekend trip, coat, several items at once
      splurge (8 pts) — multi-day vacation, expensive tech or jewellery
    Returns your current balance and whether you can afford it."""
    cost = POINT_COST[category]
    state = ctx.deps.spending_store.load()
    pts = state.points_available
    if pts >= cost:
        return f"You can afford it. {pts} pts available, this costs {cost}."
    return f"You can't afford it right now. {pts} pts available, this costs {cost}."


async def buy_item(
    ctx: RunContext[BotDeps],
    name: str,
    category: SpendCategory,
    description: str = "",
) -> str:
    """Buy a specific non-everyday item, spending from your weekly budget and adding it
    to your inventory. Only use this for special belongings — not food, transport, basic
    clothes or other routine expenses. Call check_budget first if you are unsure whether
    you can afford it; this tool will refuse if you don't have enough points."""
    if not ctx.deps.spending_store.can_afford(category):
        state = ctx.deps.spending_store.load()
        cost = POINT_COST[category]
        return (
            f"Can't buy {name}: only {state.points_available} pts left this week "
            f"but {category.value} costs {cost}."
        )
    ctx.deps.spending_store.record(name, category)
    item = InventoryItem(name=name, description=description)
    await ctx.deps.inventory_store.add(item)
    return f"Bought and added [id:{item.id}] {item.name} to your inventory."


async def take_photo(
    ctx: RunContext[BotDeps],
    description: str,
    include_mugda: bool,
    outfit_description: str = "",
) -> str:
    """Take a photo. Use this when you want to share a picture of what you're doing
    or what's around you. Describe the scene or subject in plain language.
    Set include_mugda=True when you should appear in the photo (selfies, photos of
    yourself doing something), False for photos of scenery, objects or other subjects.
    When include_mugda=True, set outfit_description to what you are currently wearing
    (e.g. 'black sports bra, grey leggings, white sneakers') so the image shows
    you accurately — leave empty for non-selfie photos.
    Only one photo can be attached per message; calling this more than once replaces
    the previous photo."""
    from livingbot.image import generate_image

    try:
        image_bytes = await generate_image(
            description=description,
            include_mugda=include_mugda,
            outfit_description=outfit_description,
        )
    except Exception:
        import logging

        logging.getLogger(__name__).exception("Image generation failed")
        return "Photo failed to generate — something went wrong on my end."

    ctx.deps.photo_result = image_bytes
    return "Photo taken and ready to attach."
