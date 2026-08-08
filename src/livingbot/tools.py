import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Annotated

import discord
import httpx
import trafilatura
from pydantic import Field
from pydantic_ai import BinaryContent, RunContext

from livingbot import clock, config
from livingbot.activity_notes import ActivityNote, ActivityNotesStore
from livingbot.calendar import CalendarStore, PlanEntry
from livingbot.commitments import Commitment, CommitmentStore
from livingbot.directory import Directory
from livingbot.hobbies import EXPERIENCE_PER_SESSION, Hobby, HobbyStore
from livingbot.inventory import InventoryItem, InventoryStore
from livingbot.preferences import PreferenceStore
from livingbot.spending import POINT_COST, SpendCategory, SpendingStore
from livingbot.stories import StoryStore
from livingbot.timeformat import humanize_ago

logger = logging.getLogger(__name__)

MAX_LINK_PREVIEW_LENGTH = 300
MAX_EMBED_IMAGE_BYTES = 8 * 1024 * 1024
MAX_ARTICLE_CHARS = 6000
_FETCH_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"
)


@dataclass
class BotDeps:
    channel: discord.abc.Messageable
    channel_id: int
    calendar_store: CalendarStore
    activity_notes_store: ActivityNotesStore
    inventory_store: InventoryStore
    spending_store: SpendingStore
    hobby_store: HobbyStore
    story_store: StoryStore
    preference_store: PreferenceStore
    commitment_store: CommitmentStore
    directory: Directory = field(default_factory=lambda: Directory({}))
    photo_result: bytes | None = None


# Marks her own lines in a formatted history. The prompt builder reads it back out to
# pick her messages from the channel's, so the two must agree on the exact wording.
OWN_MESSAGE_MARKER = " (you)"


def format_message(message: discord.Message, own: bool = False) -> str:
    timestamp = clock.to_local(message.created_at).strftime("%Y-%m-%d %H:%M:%S")
    author = message.author.display_name
    if own:
        author += OWN_MESSAGE_MARKER
    # clean_content is discord.py's own mention rendering: "<@123>" arrives as
    # "@Kuba", so the model never sees a raw user id.
    line = f"[id:{message.id}] [{timestamp}] {author}: {message.clean_content}"
    previews = _format_link_previews(message)
    if previews:
        line += f"\n{previews}"
    return line


def _format_link_previews(message: discord.Message) -> str:
    previews: list[str] = []
    for embed in message.embeds:
        if embed.type == "image":
            continue
        parts = [part for part in (embed.title, embed.description) if part]
        text = " — ".join(parts) if parts else (embed.url or "")
        if not text:
            continue
        if len(text) > MAX_LINK_PREVIEW_LENGTH:
            text = text[:MAX_LINK_PREVIEW_LENGTH].rstrip() + "…"
        previews.append(f"  [link preview: {text}]")
    return "\n".join(previews)


async def extract_images(message: discord.Message) -> list[BinaryContent]:
    """Download image attachments and images shared as links for the VLM to look at."""
    images: list[BinaryContent] = []
    for attachment in message.attachments:
        if attachment.content_type and attachment.content_type.startswith("image/"):
            data = await attachment.read()
            images.append(BinaryContent(data=data, media_type=attachment.content_type))
    images.extend(await _extract_embed_images(message))
    return images


async def _extract_embed_images(message: discord.Message) -> list[BinaryContent]:
    # Discord unfurls a pasted image link into an "image" embed; the bytes still
    # live behind a URL we have to fetch ourselves.
    urls: list[str] = []
    for embed in message.embeds:
        if embed.type != "image":
            continue
        url = embed.thumbnail.proxy_url or embed.thumbnail.url or embed.url
        if url:
            urls.append(url)
    if not urls:
        return []
    images: list[BinaryContent] = []
    async with httpx.AsyncClient() as client:
        for url in dict.fromkeys(urls):
            content = await _download_image(client, url)
            if content is not None:
                images.append(content)
    return images


async def _download_image(client: httpx.AsyncClient, url: str) -> BinaryContent | None:
    try:
        response = await client.get(url, timeout=10.0)
        response.raise_for_status()
    except httpx.HTTPError:
        logger.warning("Could not fetch image behind link %s", url)
        return None
    media_type = response.headers.get("content-type", "").split(";")[0].strip()
    if not media_type.startswith("image/"):
        return None
    if len(response.content) > MAX_EMBED_IMAGE_BYTES:
        logger.warning("Image behind link %s is too large; skipping", url)
        return None
    return BinaryContent(data=response.content, media_type=media_type)


async def fetch_link(url: str) -> str:
    """Open a web link someone shared and read what's actually on the page — an article,
    a blog post, a recipe — so you can react to it with your own honest opinion instead
    of guessing from the URL. Pass the full link. Returns the page's main text, trimmed
    if it's long. Use it whenever someone drops a link and wants your take, or when what
    you'd say depends on what the page really says. React like a person with a view on
    it — don't summarise it like an assistant."""
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            response = await client.get(
                url, timeout=15.0, headers={"User-Agent": _FETCH_USER_AGENT}
            )
            response.raise_for_status()
    except httpx.HTTPError:
        logger.warning("Could not open link %s", url)
        return "Couldn't open that link."
    content_type = response.headers.get("content-type", "").split(";")[0].strip()
    if content_type and not content_type.startswith(("text/html", "application/xhtml")):
        return f"That link isn't a readable page ({content_type})."
    text = await asyncio.to_thread(trafilatura.extract, response.text)
    if not text or not text.strip():
        return "Opened the link but there was no readable text on it."
    text = text.strip()
    if len(text) > MAX_ARTICLE_CHARS:
        text = text[:MAX_ARTICLE_CHARS].rstrip() + "…"
    return text


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


async def add_activity_note(ctx: RunContext[BotDeps], activity: str, note: str) -> str:
    """Save a standing reminder tied to an activity, so you remember it every time you
    do that activity — e.g. activity "gym", note "bring my new personalised dumbbells".
    The reminder sticks to every future occurrence of that activity and is attached to
    any matching plans already on your calendar. Returns the reminder's id."""
    store = ctx.deps.activity_notes_store
    notes = store.load()
    new_note = ActivityNote(activity=activity, note=note)
    notes.entries.append(new_note)
    store.save(notes)

    calendar = ctx.deps.calendar_store.load()
    matched = [e for e in calendar.upcoming(clock.now()) if new_note.matches(e)]
    for entry in matched:
        notes.apply_to(entry)
    if matched:
        ctx.deps.calendar_store.save(calendar)
    return (
        f"Saved [id:{new_note.id}] reminder for '{activity}': {note}. "
        f"Attached it to {len(matched)} upcoming plan(s)."
    )


async def remove_activity_note(ctx: RunContext[BotDeps], note_id: str) -> str:
    """Remove a standing activity reminder by its id, e.g. once it no longer applies.
    The id is shown next to each reminder in your activity notes."""
    store = ctx.deps.activity_notes_store
    notes = store.load()
    remaining = [n for n in notes.entries if n.id != note_id]
    if len(remaining) == len(notes.entries):
        return f"No activity reminder with id {note_id}."
    notes.entries = remaining
    store.save(notes)
    return f"Removed activity reminder {note_id}."


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


async def record_preference(ctx: RunContext[BotDeps], topic: str, stance: str) -> str:
    """Write down a taste of yours so you keep it for good. Use this the moment you make
    your mind up about something you had never settled before — the kind of guys you go
    for, how you take your coffee, which films you can't sit through. topic is the area
    in a few words ("body type in guys"); stance is your actual position, specific and
    one-sided ("lean and visibly strong, not skinny and not heavy"). Recording the same
    topic again replaces the old stance, so only do that when your mind genuinely
    changes."""
    preference = ctx.deps.preference_store.record(topic, stance)
    return f"Noted [id:{preference.id}] {preference.topic}: {preference.stance}."


async def add_commitment(
    ctx: RunContext[BotDeps],
    person: str,
    description: str,
    due_hint: str,
) -> str:
    """Record a concrete promise YOU just made to a SPECIFIC person about something
    YOU will do or share LATER, not right now. Only call this when YOU yourself used
    clear future-promise language addressed to them — e.g. "I'll show you once I'm at
    my computer" / "pokażę ci jak będę przy kompie" or "I'll send it to you tomorrow".
    This tool tracks only what you owe other people. If THEY are the one saying they
    will do or send something, record nothing at all — "podeślę ci jutro zdjęcia" said
    by them is their promise, not yours, and calling this tool would make you chase
    them for something you never owed.
    Do NOT call this either for: anything you already did or said in this same reply; a
    vague maybe ("sometime", "kiedyś", "we should really..."); or an idea still being
    floated that nobody has actually committed to.
    When in doubt, don't record it — most conversations make no promise worth tracking.
    person: the name of the person you promised, exactly as it is shown in the
    conversation.
    description: what you promised, in a few words, e.g. "show a screenshot of my BG3
    character".
    due_hint: your own words for when, taken from what you actually said, e.g. "next
    time I'm at my computer" or "tomorrow".
    Returns the new promise's id."""
    user_id = ctx.deps.directory.id_for(person)
    if user_id is None:
        return f"No one called {person} is here, so there's nothing to record."
    store = ctx.deps.commitment_store
    commitments = store.load()
    commitment = Commitment(
        user_id=user_id,
        channel_id=ctx.deps.channel_id,
        description=description,
        due_hint=due_hint,
        made_at=clock.now(),
    )
    commitments.entries.append(commitment)
    store.save(commitments)
    return f"Noted [id:{commitment.id}] promise to {person}: {description}."


async def resolve_commitment(ctx: RunContext[BotDeps], commitment_id: str) -> str:
    """Mark a promise as fulfilled once you've actually followed through on it in this
    reply — e.g. you showed the photo, sent the info, or did the thing you said you
    would. The id is shown next to open promises in your context. Call this the moment
    you follow through, so you don't bring the same promise up again."""
    store = ctx.deps.commitment_store
    commitments = store.load()
    for commitment in commitments.entries:
        if commitment.id == commitment_id:
            commitment.status = "fulfilled"
            store.save(commitments)
            return f"Marked promise {commitment_id} as fulfilled."
    return f"No open promise with id {commitment_id}."


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
    hobby: str = "",
) -> str:
    """Take a photo. Use this when you want to share a picture of what you're doing
    or what's around you. Describe the scene or subject in plain language.
    Set include_mugda=True when you should appear in the photo (selfies, photos of
    yourself doing something), False for photos of scenery, objects or other subjects.
    When include_mugda=True, set outfit_description to what you are currently wearing
    (e.g. 'black sports bra, grey leggings, white sneakers') so the image shows
    you accurately — leave empty for non-selfie photos.
    Set hobby to the exact name of one of your hobbies when the photo shows something
    you made or did with it — a painting you painted, a cake you baked, a lift you hit —
    so the picture comes out as good or as bad as you actually are at it. Leave it
    empty for anything else.
    Only one photo can be attached per message; calling this more than once replaces
    the previous photo."""
    from livingbot.image import generate_image

    hobbies = ctx.deps.hobby_store.load()
    hobby_entry = next((h for h in hobbies.entries if h.name == hobby), None)
    if hobby and hobby_entry is None:
        names = ", ".join(h.name for h in hobbies.entries) or "(none)"
        return (
            f"You don't have a hobby called {hobby}. Your hobbies are: {names}. "
            "Take the photo again with one of those, or with no hobby at all."
        )

    try:
        image_bytes = await generate_image(
            description=description,
            include_mugda=include_mugda,
            outfit_description=outfit_description,
            hobby=hobby_entry,
        )
    except Exception:
        logger.exception("Image generation failed")
        return "Photo failed to generate — something went wrong on my end."

    ctx.deps.photo_result = image_bytes
    return "Photo taken and ready to attach."
