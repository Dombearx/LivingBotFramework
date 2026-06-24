from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Annotated

import discord
from pydantic import Field
from pydantic_ai import BinaryContent, RunContext

from livingbot import clock, config
from livingbot.calendar import CalendarStore, PlanEntry
from livingbot.hobbies import EXPERIENCE_PER_SESSION, Hobby, HobbyStore
from livingbot.inventory import InventoryItem, InventoryStore
from livingbot.spending import POINT_COST, SpendCategory, SpendingStore
from livingbot.stories import StoryStore
from livingbot.timeformat import humanize_ago


@dataclass
class BotDeps:
    channel: discord.abc.Messageable
    calendar_store: CalendarStore
    inventory_store: InventoryStore
    spending_store: SpendingStore
    hobby_store: HobbyStore
    story_store: StoryStore
    photo_result: bytes | None = None


def format_message(message: discord.Message) -> str:
    timestamp = clock.to_local(message.created_at).strftime("%Y-%m-%d %H:%M:%S")
    return (
        f"[id:{message.id}] [{timestamp}] "
        f"{message.author.display_name}: {message.content}"
    )


async def extract_images(message: discord.Message) -> list[BinaryContent]:
    """Download any image attachments on a message for the VLM to look at."""
    images: list[BinaryContent] = []
    for attachment in message.attachments:
        if attachment.content_type and attachment.content_type.startswith("image/"):
            data = await attachment.read()
            images.append(BinaryContent(data=data, media_type=attachment.content_type))
    return images


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
    hobby: str = "",
) -> str:
    """Add something to your own calendar, e.g. a gym session or a multi-day trip.
    start and end are datetimes; location is where you physically are during it.
    Use this whenever you decide to do something that changes where you are or how
    your time is spent. Set hobby to the exact name of one of your hobbies when this
    plan is you actually practising it (e.g. "gym" for a gym session) — that's how
    you grow more skilled at it over time; leave it empty otherwise. Returns the new
    entry's id."""
    calendar = ctx.deps.calendar_store.load()
    entry = PlanEntry(
        activity=activity,
        location=location,
        start=start,
        end=end,
        note=note,
        hobby=hobby,
    )
    calendar.entries.append(entry)
    ctx.deps.calendar_store.save(calendar)
    if hobby:
        ctx.deps.hobby_store.gain_experience(hobby, EXPERIENCE_PER_SESSION)
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


async def add_hobby(ctx: RunContext[BotDeps], name: str) -> str:
    """Add a new hobby to your life, e.g. when you genuinely take up something like
    pottery or running. You start out as a novice and grow more skilled at it over
    time as you spend time on it — see add_plan."""
    now = clock.now()
    hobbies = ctx.deps.hobby_store.load()
    if any(hobby.name == name for hobby in hobbies.entries):
        return f"{name} is already one of your hobbies."
    acquired = [
        (hobby, hobby.acquired_at)
        for hobby in hobbies.entries
        if hobby.acquired_at is not None
    ]
    if acquired:
        last_hobby, last_at = max(acquired, key=lambda pair: pair[1])
        if now - last_at < config.HOBBY_COOLDOWN:
            return (
                f"You took up {last_hobby.name} "
                f"{humanize_ago(last_at, now)} — it's too soon to take "
                "up something new. Give it a couple of weeks before adding another "
                "hobby."
            )
    hobbies.entries.append(Hobby(name=name, acquired_at=now))
    ctx.deps.hobby_store.save(hobbies)
    return f"Added {name} to your hobbies."


async def recall_story(
    ctx: RunContext[BotDeps],
    query: Annotated[str, Field(min_length=1)],
    n: Annotated[int, Field(ge=1, le=10)] = 3,
) -> str:
    """Search the stories from your life for ones that fit a topic, mood or situation,
    described in natural language, e.g. "an embarrassing moment" or "something about
    travel". Returns up to n best-matching stories with their full content and whether
    you've already told them — useful both for sharing something new and for casually
    referring back to something you've told before."""
    stories = await ctx.deps.story_store.search(query, limit=n)
    if not stories:
        return "Nothing from your life comes to mind for that."
    lines = []
    for story in stories:
        status = (
            "already told — you may refer back to it, but don't retell it in full"
            if story.told_at
            else "not told yet"
        )
        if story.image_path:
            status += "; has a photo you can attach with show_story_image"
        lines.append(f"[id:{story.id}] ({status})\n{story.content}")
    return "\n\n".join(lines)


async def mark_story_told(ctx: RunContext[BotDeps], story_id: str) -> str:
    """Record that you just shared this story with the group, by its id. Call this
    right after telling it in your reply, so you remember not to tell it again —
    you can still casually refer back to it later."""
    if await ctx.deps.story_store.mark_told(story_id):
        return f"Marked story {story_id} as told."
    return f"No story with id {story_id}."


async def show_story_image(ctx: RunContext[BotDeps], story_id: str) -> str:
    """Attach the photo that goes with one of your life stories, by its id. Use this
    while telling or referring back to a story that has a photo, so the group can see
    it. Only one photo can be attached per message; calling this replaces any photo
    already attached."""
    story = await ctx.deps.story_store.get(story_id)
    if story is None:
        return f"No story with id {story_id}."
    if not story.image_path:
        return "That story has no photo to show."
    path = Path(story.image_path)
    if not path.exists():
        return "That story's photo is missing."
    ctx.deps.photo_result = path.read_bytes()
    return "Photo attached."


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
