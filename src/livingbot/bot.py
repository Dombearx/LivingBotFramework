import asyncio
import io
import logging
import os
import random
from datetime import date, datetime, time, timedelta

import discord
import logfire
from pydantic_ai import BinaryContent

from livingbot import clock, config, llm_config, prompts
from livingbot.calendar import Calendar, CalendarStore, WeekPlanner
from livingbot.hobbies import EXPERIENCE_PER_SESSION, HobbyStore, recent_hobbies
from livingbot.inventory import InventoryStore
from livingbot.llm import LLMClient
from livingbot.memory import MemoryStore
from livingbot.mood import (
    SLEEP_WINDOW_END,
    SLEEP_WINDOW_START,
    MoodStore,
    apply_interaction_delta,
    refresh_mood,
)
from livingbot.observability import configure_logfire
from livingbot.queue import MessageQueue
from livingbot.relations import Relation, RelationStore, RelationUpdater
from livingbot.spending import SpendingStore
from livingbot.image import generate_image
from livingbot.stories import Story, StoryGenerator, StoryStore
from livingbot.timeformat import humanize_ago
from livingbot.tools import extract_images, format_message

logger = logging.getLogger(__name__)

DISCORD_MAX_LENGTH = 2000


async def _send_chunked(
    channel: discord.abc.Messageable,
    text: str,
    photo: bytes | None = None,
) -> None:
    chunks = [
        text[i : i + DISCORD_MAX_LENGTH]
        for i in range(0, len(text), DISCORD_MAX_LENGTH)
    ]
    for i, chunk in enumerate(chunks):
        is_last = i == len(chunks) - 1
        if is_last and photo is not None:
            file = discord.File(io.BytesIO(photo), filename="photo.jpg")
            await channel.send(chunk, file=file)
        else:
            await channel.send(chunk)


def _random_datetime_between(start: datetime, end: datetime) -> datetime:
    span = max((end - start).total_seconds(), 0.0)
    return start + timedelta(seconds=random.uniform(0, span))


def _pick_story_slot(
    calendar: Calendar, week_start: date, now: datetime
) -> tuple[datetime, str | None]:
    week_end = datetime.combine(week_start, time()) + timedelta(days=7)
    upcoming = [entry for entry in calendar.entries if entry.end > now]
    if upcoming and random.random() < config.STORY_TIED_TO_PLAN_PROBABILITY:
        entry = random.choice(upcoming)
        occurs_at = _random_datetime_between(max(entry.start, now), entry.end)
        return occurs_at, f"{entry.activity} at {entry.location}"
    earliest = max(now, datetime.combine(week_start, time()))
    return _random_free_moment(earliest, week_end, calendar), None


def _random_free_moment(
    earliest: datetime, week_end: datetime, calendar: Calendar
) -> datetime:
    for _ in range(10):
        day = _random_datetime_between(earliest, week_end)
        moment = day.replace(
            hour=random.randint(
                config.STORY_ACTIVE_HOUR_START, config.STORY_ACTIVE_HOUR_END - 1
            ),
            minute=random.randint(0, 59),
            second=0,
            microsecond=0,
        )
        if earliest <= moment <= week_end and calendar.current_entry(moment) is None:
            return moment
    return _random_datetime_between(earliest, week_end)


class LivingBot(discord.Client):
    def __init__(
        self,
        llm_client: LLMClient,
        memory_store: MemoryStore,
        relation_store: RelationStore,
        relation_updater: RelationUpdater,
        calendar_store: CalendarStore,
        week_planner: WeekPlanner,
        inventory_store: InventoryStore,
        spending_store: SpendingStore,
        hobby_store: HobbyStore,
        story_store: StoryStore,
        story_generator: StoryGenerator,
        mood_store: MoodStore,
        **kwargs: object,
    ) -> None:
        super().__init__(**kwargs)
        self._queue = MessageQueue()
        self._fatigue: float = 0.0
        self._resting: bool = False
        self._response_lock = asyncio.Lock()
        self._state_lock = asyncio.Lock()
        self._llm_client = llm_client
        self._memory_store = memory_store
        self._relation_store = relation_store
        self._relation_updater = relation_updater
        self._calendar_store = calendar_store
        self._week_planner = week_planner
        self._inventory_store = inventory_store
        self._spending_store = spending_store
        self._hobby_store = hobby_store
        self._story_store = story_store
        self._story_generator = story_generator
        self._mood_store = mood_store
        self._messages_since_photo: int = 0
        self._photo_cooldown: int = random.randint(
            config.PHOTO_COOLDOWN_MIN, config.PHOTO_COOLDOWN_MAX
        )

    @property
    def memory_store(self) -> MemoryStore:
        return self._memory_store

    @property
    def relation_store(self) -> RelationStore:
        return self._relation_store

    @property
    def calendar_store(self) -> CalendarStore:
        return self._calendar_store

    @property
    def inventory_store(self) -> InventoryStore:
        return self._inventory_store

    @property
    def spending_store(self) -> SpendingStore:
        return self._spending_store

    @property
    def hobby_store(self) -> HobbyStore:
        return self._hobby_store

    @property
    def story_store(self) -> StoryStore:
        return self._story_store

    @property
    def mood_store(self) -> MoodStore:
        return self._mood_store

    @property
    def fatigue(self) -> float:
        return self._fatigue

    @property
    def resting(self) -> bool:
        return self._resting

    @property
    def messages_since_photo(self) -> int:
        return self._messages_since_photo

    @property
    def photo_cooldown(self) -> int:
        return self._photo_cooldown

    async def setup_hook(self) -> None:
        self.loop.create_task(self._life_loop())

    async def _life_loop(self) -> None:
        while True:
            try:
                await self._ensure_week_planned()
                await self._ensure_morning_mood_refresh()
                await self._story_store.prune_stale(clock.now())
            except Exception:
                logger.exception("Life loop iteration failed")
            await asyncio.sleep(config.LIFE_LOOP_INTERVAL_SECONDS)

    async def _ensure_morning_mood_refresh(self) -> None:
        now = clock.now()
        if not (SLEEP_WINDOW_START <= now.hour < SLEEP_WINDOW_END):
            return
        async with self._state_lock:
            mood = self._mood_store.load()
            if mood.last_sleep_date is not None and mood.last_sleep_date >= now.date():
                return
            calendar = self._calendar_store.load()
            mood = refresh_mood(mood, now, calendar)
            self._mood_store.save(mood)
        logger.info("Morning mood refresh: %.1f", mood.value)

    async def _ensure_week_planned(self) -> None:
        now = clock.now()
        week_start = now.date() - timedelta(days=now.weekday())
        calendar = self._calendar_store.load()
        calendar.prune_past(now)
        if calendar.planned_week_start != week_start:
            hobbies = self._hobby_store.load()
            hobby_names = [hobby.name for hobby in hobbies.entries]
            new_hobby_notes = [
                f"{hobby.name} (took up {humanize_ago(hobby.acquired_at, now)})"
                for hobby in recent_hobbies(hobbies, now, config.RECENT_HOBBY_WINDOW)
            ]
            entries = await self._week_planner.plan(
                week_start,
                hobby_names,
                calendar.home_location,
                new_hobby_notes,
            )
            # Reload so plans the bot added through tools while we awaited the
            # planner aren't clobbered by this save.
            calendar = self._calendar_store.load()
            calendar.prune_past(now)
            calendar.entries.extend(entries)
            calendar.planned_week_start = week_start
            for entry in entries:
                if entry.hobby:
                    self._hobby_store.gain_experience(
                        entry.hobby, EXPERIENCE_PER_SESSION
                    )
            logger.info(
                "Planned week starting %s with %d entries", week_start, len(entries)
            )
            self._calendar_store.save(calendar)
            asyncio.create_task(
                self._generate_week_story(
                    calendar, hobby_names, week_start, now, new_hobby_notes
                )
            )
            return
        self._calendar_store.save(calendar)

    async def _generate_week_story(
        self,
        calendar: Calendar,
        hobbies: list[str],
        week_start: date,
        now: datetime,
        new_hobbies: list[str],
    ) -> None:
        occurs_at, anchor = _pick_story_slot(calendar, week_start, now)
        avoid = await self._story_store.recent_summaries(
            config.STORY_AVOID_RECENT_LIMIT
        )
        story = await self._story_generator.generate(
            week_start,
            hobbies,
            calendar.home_location,
            occurs_at,
            anchor,
            avoid,
            new_hobbies,
        )
        if story is None:
            return
        story.image_path = await self._render_story_image(story)
        await self._story_store.add(story)
        logger.info("Story for week %s happens %s", week_start, occurs_at)

    async def _render_story_image(self, story: Story) -> str | None:
        try:
            image_bytes = await generate_image(
                description=story.content, include_mugda=True
            )
        except Exception:
            logger.exception("Failed to render image for story %s", story.id)
            return None
        config.STORY_IMAGE_PATH.mkdir(parents=True, exist_ok=True)
        path = config.STORY_IMAGE_PATH / f"{story.id}.jpg"
        path.write_bytes(image_bytes)
        return str(path)

    async def on_ready(self) -> None:
        logger.info(
            "Logged in as %s (id=%s)", self.user, self.user.id if self.user else None
        )

    async def on_message(self, message: discord.Message) -> None:
        if message.author == self.user:
            return

        if not await self._is_directed_at_bot(message):
            return

        self._messages_since_photo += 1
        self._queue.add(message)

        async with self._response_lock:
            if self._resting:
                return
            if not await self._attempt_response():
                self._resting = True
                asyncio.create_task(self._rest_and_respond())

    def _photo_hint_for_message(self) -> str:
        if self._messages_since_photo >= self._photo_cooldown:
            return prompts.PHOTO_HINT
        return ""

    def _on_photo_taken(self) -> None:
        self._messages_since_photo = 0
        self._photo_cooldown = random.randint(
            config.PHOTO_COOLDOWN_MIN, config.PHOTO_COOLDOWN_MAX
        )

    def _onboarding_active(self) -> bool:
        join_times = [
            guild.me.joined_at
            for guild in self.guilds
            if guild.me is not None and guild.me.joined_at is not None
        ]
        if not join_times:
            return False
        return discord.utils.utcnow() - min(join_times) < config.ONBOARDING_PERIOD

    async def _attempt_response(self) -> bool:
        if len(self._queue) == 0:
            return True
        now = clock.now()
        async with self._state_lock:
            mood = refresh_mood(
                self._mood_store.load(), now, self._calendar_store.load()
            )
            self._mood_store.save(mood)

        onboarding_active = self._onboarding_active()
        mood_factor = 0.5 + (mood.value / 100.0)
        if onboarding_active:
            mood_factor *= config.ONBOARDING_RESPONSE_BOOST
        should_respond = random.random() < mood_factor / (self._fatigue + 1.0)
        with logfire.span(
            "attempt_response",
            mood=mood.value,
            fatigue=self._fatigue,
            onboarding_active=onboarding_active,
            should_respond=should_respond,
        ):
            if not should_respond:
                return False
            self._fatigue += len(self._queue)
            for channel, messages in self._queue.flush().items():
                with logfire.span(
                    "respond_to_channel",
                    channel_id=channel.id,
                    message_count=len(messages),
                ):
                    formatted = [format_message(m) for m in messages]
                    images: list[BinaryContent] = []
                    for m in messages:
                        images.extend(await extract_images(m))
                    author_ids = list(dict.fromkeys(str(m.author.id) for m in messages))
                    memories = await self._memory_store.retrieve(
                        [
                            (text, str(m.author.id))
                            for text, m in zip(formatted, messages)
                        ]
                    )
                    relations = [self._relation_store.load(uid) for uid in author_ids]
                    result = await self._llm_client.complete(
                        formatted,
                        channel,
                        self._calendar_store,
                        self._inventory_store,
                        self._spending_store,
                        self._hobby_store,
                        self._story_store,
                        now,
                        memories,
                        relations,
                        mood,
                        photo_hint=self._photo_hint_for_message(),
                        images=images,
                    )
                    if result.photo is not None:
                        self._on_photo_taken()
                    await _send_chunked(channel, result.output, photo=result.photo)
                    sole_author = author_ids[0] if len(author_ids) == 1 else None
                    asyncio.create_task(
                        self._store_memories(messages, result.output, sole_author)
                    )
                    asyncio.create_task(
                        self._update_relations(relations, messages, result.output)
                    )
            return True

    async def _store_memories(
        self, messages: list[discord.Message], bot_response: str, user_id: str | None
    ) -> None:
        conversation = [
            {"role": "user", "content": format_message(m)} for m in messages
        ]
        conversation.append({"role": "assistant", "content": bot_response})
        try:
            await self._memory_store.store(conversation, user_id=user_id)
        except Exception:
            logger.exception("Failed to store memories for user_id=%s", user_id)

    async def _update_relations(
        self,
        relations: list[Relation],
        messages: list[discord.Message],
        bot_response: str,
    ) -> None:
        conversation = [
            {"role": "user", "content": format_message(m)} for m in messages
        ]
        conversation.append({"role": "assistant", "content": bot_response})
        for relation in relations:
            updated = await self._relation_updater.update(relation, conversation)
            self._relation_store.save(updated)
            logger.debug("Updated relation for user_id=%s", relation.user_id)
            delta = updated.attitude - relation.attitude
            if delta != 0:
                async with self._state_lock:
                    mood = apply_interaction_delta(self._mood_store.load(), delta)
                    self._mood_store.save(mood)
                logger.debug(
                    "Mood adjusted by interaction delta=%d: %.1f", delta, mood.value
                )

    async def _rest_and_respond(self) -> None:
        while True:
            mood = self._mood_store.load()
            mood_rest_factor = 1.5 - (mood.value / 100.0)
            max_delay = max(3.0, 5.0 * self._fatigue * mood_rest_factor)
            delay_divisor = (
                config.ONBOARDING_REST_DELAY_DIVISOR
                if self._onboarding_active()
                else 1.0
            )
            actual_delay = random.uniform(
                3.0 / delay_divisor, max_delay / delay_divisor
            )
            await asyncio.sleep(actual_delay * 60.0)

            async with self._response_lock:
                self._fatigue = max(0.0, self._fatigue - actual_delay / 5.0)
                if await self._attempt_response():
                    self._resting = False
                    return

    async def _is_directed_at_bot(self, message: discord.Message) -> bool:
        if self.user is not None and self.user in message.mentions:
            return True
        return await self._is_reply_to_bot(message)

    async def _is_reply_to_bot(self, message: discord.Message) -> bool:
        reference = message.reference
        if reference is None or self.user is None:
            return False
        resolved = reference.resolved
        if isinstance(resolved, discord.Message):
            return resolved.author == self.user
        # resolved is None when the replied-to message isn't cached; fetch it so
        # replies to older bot messages are still recognised.
        if resolved is None and reference.message_id is not None:
            try:
                referenced = await message.channel.fetch_message(reference.message_id)
            except discord.HTTPException:
                return False
            return referenced.author == self.user
        return False


def build() -> LivingBot:
    intents = discord.Intents.default()
    intents.message_content = True
    llm_client = LLMClient(
        llm_config.build_chat_model(llm_config.CHAT_MODEL), prompts.SYSTEM_PROMPT
    )
    memory_store = MemoryStore.create(config.MEMORY_DATA_PATH)
    relation_store = RelationStore(config.RELATION_DATA_PATH)
    relation_updater = RelationUpdater(
        llm_config.build_chat_model(llm_config.RELATION_UPDATER_MODEL)
    )
    calendar_store = CalendarStore(config.CALENDAR_DATA_PATH, config.HOME_LOCATION)
    week_planner = WeekPlanner(
        llm_config.build_chat_model(llm_config.WEEK_PLANNER_MODEL)
    )
    inventory_store = InventoryStore.create(config.INVENTORY_DATA_PATH)
    spending_store = SpendingStore(config.SPENDING_DATA_PATH)
    hobby_store = HobbyStore(config.HOBBY_DATA_PATH, config.DEFAULT_HOBBIES)
    story_store = StoryStore.create(config.STORY_DATA_PATH)
    story_generator = StoryGenerator(
        llm_config.build_chat_model(llm_config.STORY_GENERATOR_MODEL)
    )
    mood_store = MoodStore(config.MOOD_DATA_PATH)
    return LivingBot(
        llm_client=llm_client,
        memory_store=memory_store,
        relation_store=relation_store,
        relation_updater=relation_updater,
        calendar_store=calendar_store,
        week_planner=week_planner,
        inventory_store=inventory_store,
        spending_store=spending_store,
        hobby_store=hobby_store,
        story_store=story_store,
        story_generator=story_generator,
        mood_store=mood_store,
        intents=intents,
    )


def run() -> None:
    configure_logfire()
    token = os.environ["DISCORD_BOT_TOKEN"]
    bot = build()
    bot.run(token, log_handler=None)
