import asyncio
import io
import logging
import os
import random
from datetime import date, datetime, time, timedelta
from typing import Any

import discord
import logfire
from pydantic_ai import BinaryContent

from livingbot import clock, config, prompts
from livingbot.activity_notes import ActivityNotesStore
from livingbot.calendar import Calendar, CalendarStore, WeekPlanner
from livingbot.commitment_timing import CommitmentTimingJudge
from livingbot.commitments import Commitment, CommitmentStatus, CommitmentStore
from livingbot.hobbies import EXPERIENCE_PER_SESSION, HobbyStore, recent_hobbies
from livingbot.inventory import InventoryStore
from livingbot.llm import LLMClient
from livingbot.memory import MemoryStore
from livingbot.mood import (
    FATIGUE_MAX,
    MORNING_WINDOW_END,
    MORNING_WINDOW_START,
    MoodStore,
    add_fatigue,
    apply_interaction_delta,
    build_mood_block,
    is_awake,
    refresh_mood,
)
from livingbot.observability import configure_logfire
from livingbot.photo import PhotoCooldown, PhotoCooldownStore
from livingbot.preferences import PreferenceStore
from livingbot.queue import MessageQueue
from livingbot.relations import (
    Relation,
    RelationStore,
    RelationUpdater,
    apply_update,
)
from livingbot.spending import SpendingStore
from livingbot.image import generate_image
from livingbot.scheduled_posts import ScheduledPostStore
from livingbot.spontaneous import SpontaneousStore
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
            hour=random.randint(config.AWAKE_HOUR_START, config.AWAKE_HOUR_END - 1),
            minute=random.randint(0, 59),
            second=0,
            microsecond=0,
        )
        if earliest <= moment <= week_end and calendar.current_entry(moment) is None:
            return moment
    return _random_datetime_between(earliest, week_end)


def _next_spontaneous_time(now: datetime) -> datetime:
    days_ahead = random.uniform(
        config.RANDOM_POST_MIN_DAYS, config.RANDOM_POST_MAX_DAYS
    )
    target = now + timedelta(days=days_ahead)
    return target.replace(
        hour=random.randint(config.AWAKE_HOUR_START, config.AWAKE_HOUR_END - 1),
        minute=random.randint(0, 59),
        second=0,
        microsecond=0,
    )


class LivingBot(discord.Client):
    def __init__(
        self,
        llm_client: LLMClient,
        memory_store: MemoryStore,
        relation_store: RelationStore,
        relation_updater: RelationUpdater,
        calendar_store: CalendarStore,
        activity_notes_store: ActivityNotesStore,
        week_planner: WeekPlanner,
        inventory_store: InventoryStore,
        spending_store: SpendingStore,
        hobby_store: HobbyStore,
        story_store: StoryStore,
        story_generator: StoryGenerator,
        mood_store: MoodStore,
        preference_store: PreferenceStore,
        photo_cooldown_store: PhotoCooldownStore,
        commitment_store: CommitmentStore,
        commitment_timing_judge: CommitmentTimingJudge,
        spontaneous_store: SpontaneousStore | None = None,
        scheduled_post_store: ScheduledPostStore | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._queue = MessageQueue()
        self._resting: bool = False
        self._next_attempt_at: datetime | None = None
        # Starts spent so the first message she sends carries the emoji list.
        self._messages_since_emoji_reminder = config.SERVER_EMOJI_REMINDER_INTERVAL
        self._response_lock = asyncio.Lock()
        self._state_lock = asyncio.Lock()
        self._llm_client = llm_client
        self._memory_store = memory_store
        self._relation_store = relation_store
        self._relation_updater = relation_updater
        self._calendar_store = calendar_store
        self._activity_notes_store = activity_notes_store
        self._week_planner = week_planner
        self._inventory_store = inventory_store
        self._spending_store = spending_store
        self._hobby_store = hobby_store
        self._story_store = story_store
        self._story_generator = story_generator
        self._mood_store = mood_store
        self._preference_store = preference_store
        self._photo_cooldown_store = photo_cooldown_store
        self._commitment_store = commitment_store
        self._commitment_timing_judge = commitment_timing_judge
        self._spontaneous_store = spontaneous_store
        self._scheduled_post_store = scheduled_post_store

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
    def activity_notes_store(self) -> ActivityNotesStore:
        return self._activity_notes_store

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
    def preference_store(self) -> PreferenceStore:
        return self._preference_store

    @property
    def commitment_store(self) -> CommitmentStore:
        return self._commitment_store

    @property
    def spontaneous_store(self) -> SpontaneousStore | None:
        return self._spontaneous_store

    @property
    def scheduled_post_store(self) -> ScheduledPostStore | None:
        return self._scheduled_post_store

    @property
    def fatigue(self) -> float:
        return self._mood_store.load().fatigue

    @property
    def resting(self) -> bool:
        return self._resting

    @property
    def pending_messages(self) -> list[discord.Message]:
        return self._queue.pending()

    @property
    def next_attempt_at(self) -> datetime | None:
        return self._next_attempt_at

    @property
    def messages_since_photo(self) -> int:
        return self._photo_cooldown_store.load().messages_since_photo

    @property
    def photo_cooldown(self) -> int:
        return self._photo_cooldown_store.load().cooldown

    async def setup_hook(self) -> None:
        self.loop.create_task(self._life_loop())

    async def _life_loop(self) -> None:
        while True:
            try:
                with logfire.span("life_loop_iteration"):
                    await self._ensure_week_planned()
                    await self._ensure_morning_mood_refresh()
                    await self._story_store.prune_stale(clock.now())
                    await self._maybe_post_spontaneously()
                    await self._maybe_post_scheduled()
                    await self._maybe_follow_up_on_commitments()
            except Exception:
                logger.exception("Life loop iteration failed")
            await asyncio.sleep(
                random.uniform(
                    config.LIFE_LOOP_INTERVAL_MIN_SECONDS,
                    config.LIFE_LOOP_INTERVAL_MAX_SECONDS,
                )
            )

    async def _ensure_morning_mood_refresh(self) -> None:
        now = clock.now()
        if not (MORNING_WINDOW_START <= now.hour < MORNING_WINDOW_END):
            return
        async with self._state_lock:
            mood = self._mood_store.load()
            if mood.last_sleep_date is not None and mood.last_sleep_date >= now.date():
                return
            calendar = self._calendar_store.load()
            mood = refresh_mood(mood, now, calendar)
            self._mood_store.save(mood)
        logger.info("Morning mood refresh: %.1f", mood.value)

    async def _maybe_post_spontaneously(self) -> None:
        if config.RANDOM_POST_CHANNEL_ID is None:
            return
        if self._spontaneous_store is None:
            return
        now = clock.now()
        async with self._state_lock:
            state = self._spontaneous_store.load()
            if state.next_post_at is None:
                state.next_post_at = _next_spontaneous_time(now)
                self._spontaneous_store.save(state)
                return
            if now < state.next_post_at or not is_awake(now):
                return
            state.next_post_at = _next_spontaneous_time(now)
            self._spontaneous_store.save(state)
        channel = self.get_channel(config.RANDOM_POST_CHANNEL_ID)
        if not isinstance(channel, discord.abc.Messageable):
            logger.warning(
                "Spontaneous post channel %s not available",
                config.RANDOM_POST_CHANNEL_ID,
            )
            return
        # The main chat agent writes this too, rather than a separate composer: it is
        # the same person talking to the same people, and only it can reach for
        # take_photo or mark a story told as it tells one.
        result = await self._llm_client.complete(
            [],
            channel,
            config.RANDOM_POST_CHANNEL_ID,
            self._calendar_store,
            self._activity_notes_store,
            self._inventory_store,
            self._spending_store,
            self._hobby_store,
            self._story_store,
            self._preference_store,
            self._commitment_store,
            now,
            relations=self._relation_store.all(),
            mood=self._mood_store.load(),
            trigger=prompts.SPONTANEOUS_TRIGGER_MESSAGE,
            server_emojis=self._server_emojis_for_message(channel),
        )
        if result.photo is not None:
            self._on_photo_taken()
        await _send_chunked(channel, result.output, photo=result.photo)
        logger.info("Posted a spontaneous message to channel %s", channel.id)

    async def _maybe_post_scheduled(self) -> None:
        if config.RANDOM_POST_CHANNEL_ID is None:
            return
        if self._scheduled_post_store is None:
            return
        now = clock.now()
        async with self._state_lock:
            posts = self._scheduled_post_store.load()
            due = posts.due(now)
            if not due:
                return
            post = due[0]
            post.status = "posted"
            post.posted_at = now
            self._scheduled_post_store.save(posts)
        channel = self.get_channel(config.RANDOM_POST_CHANNEL_ID)
        if not isinstance(channel, discord.abc.Messageable):
            logger.warning(
                "Scheduled post channel %s not available",
                config.RANDOM_POST_CHANNEL_ID,
            )
            return
        # Same reasoning as the spontaneous post above: the main chat agent writes
        # it, since it's the same person talking to the same people.
        result = await self._llm_client.complete(
            [],
            channel,
            config.RANDOM_POST_CHANNEL_ID,
            self._calendar_store,
            self._activity_notes_store,
            self._inventory_store,
            self._spending_store,
            self._hobby_store,
            self._story_store,
            self._preference_store,
            self._commitment_store,
            now,
            relations=self._relation_store.all(),
            mood=self._mood_store.load(),
            trigger=prompts.build_scheduled_post_trigger(
                post.topic, post.mention_user_id
            ),
            server_emojis=self._server_emojis_for_message(channel),
        )
        if result.photo is not None:
            self._on_photo_taken()
        await _send_chunked(channel, result.output, photo=result.photo)
        logger.info(
            "Posted scheduled message about '%s' to channel %s", post.topic, channel.id
        )

    async def _maybe_follow_up_on_commitments(self) -> None:
        now = clock.now()
        await self._retire_stale_commitments(now)
        if not is_awake(now):
            return
        # Everything here is a cheap local filter: a promise only costs a
        # judgement call once its own estimated wait has run out.
        waiting = self._commitment_store.load().awaiting_followup(now)
        for commitment in waiting:
            if await self._maybe_follow_up_on(commitment, now):
                # One unprompted message per waking, however many are due.
                return

    async def _retire_stale_commitments(self, now: datetime) -> None:
        cutoff = now - config.COMMITMENT_RETIREMENT_PERIOD
        async with self._state_lock:
            commitments = self._commitment_store.load()
            stale = [
                c
                for c in commitments.entries
                if c.status == "open" and c.made_at < cutoff
            ]
            if not stale:
                return
            for commitment in stale:
                commitment.status = "dropped"
            self._commitment_store.save(commitments)
        logger.info("Let go of %d promise(s) too old to still chase", len(stale))

    async def _maybe_follow_up_on(self, commitment: Commitment, now: datetime) -> bool:
        channel = self.get_channel(commitment.channel_id)
        if not isinstance(channel, discord.abc.Messageable):
            logger.warning(
                "Commitment %s channel %s not available",
                commitment.id,
                commitment.channel_id,
            )
            await self._defer_commitment(
                commitment, now, config.COMMITMENT_DEFAULT_RETRY_HOURS
            )
            return False

        history = [
            format_message(message, own=message.author == self.user)
            async for message in channel.history(
                limit=config.COMMITMENT_FOLLOWUP_HISTORY_LIMIT
            )
        ]
        history.reverse()
        decision = await self._commitment_timing_judge.decide(
            self._build_commitment_timing_context(commitment, now, history)
        )
        if decision is None:
            await self._defer_commitment(
                commitment, now, config.COMMITMENT_DEFAULT_RETRY_HOURS
            )
            return False

        if not decision.should_follow_up:
            retry_hours = (
                decision.retry_in_hours
                if decision.retry_in_hours is not None
                else config.COMMITMENT_DEFAULT_RETRY_HOURS
            )
            await self._defer_commitment(commitment, now, retry_hours)
            logger.debug(
                "Holding off on commitment %s for %.1fh: %s",
                commitment.id,
                retry_hours,
                decision.reason,
            )
            return False

        # It's time — hand the whole thing off to the main chat agent, which has the
        # tools (take_photo, resolve_commitment), memory and context to actually follow
        # through, rather than composing the message here.
        mood = self._mood_store.load()
        memories = await self._memory_store.retrieve(
            [(commitment.description, commitment.user_id)]
        )
        relation = self._relation_store.load(commitment.user_id)
        result = await self._llm_client.complete(
            [],
            channel,
            commitment.channel_id,
            self._calendar_store,
            self._activity_notes_store,
            self._inventory_store,
            self._spending_store,
            self._hobby_store,
            self._story_store,
            self._preference_store,
            self._commitment_store,
            now,
            memories,
            [relation],
            mood,
            history=history,
            commitments=[commitment],
            trigger=prompts.COMMITMENT_TRIGGER_MESSAGE,
            server_emojis=self._server_emojis_for_message(channel),
        )
        if result.photo is not None:
            self._on_photo_taken()
        await _send_chunked(channel, result.output, photo=result.photo)
        # The agent may have already called resolve_commitment itself while handling
        # this; only stamp nudged_at, don't clobber a status it just set to fulfilled.
        current = next(
            (c for c in self._commitment_store.load().entries if c.id == commitment.id),
            commitment,
        )
        await self._save_commitment_outcome(
            commitment, status=current.status, nudged_at=now, check_after=None
        )
        logger.info(
            "Followed up on commitment %s in channel %s", commitment.id, channel.id
        )
        return True

    async def _defer_commitment(
        self, commitment: Commitment, now: datetime, retry_hours: float
    ) -> None:
        await self._save_commitment_outcome(
            commitment,
            status="open",
            nudged_at=None,
            check_after=now + timedelta(hours=retry_hours),
        )

    async def _save_commitment_outcome(
        self,
        commitment: Commitment,
        status: CommitmentStatus,
        nudged_at: datetime | None,
        check_after: datetime | None,
    ) -> None:
        async with self._state_lock:
            commitments = self._commitment_store.load()
            for entry in commitments.entries:
                if entry.id == commitment.id:
                    entry.status = status
                    entry.nudged_at = nudged_at
                    entry.check_after = check_after
            self._commitment_store.save(commitments)

    def _build_commitment_timing_context(
        self, commitment: Commitment, now: datetime, history: list[str]
    ) -> str:
        calendar = self._calendar_store.load()
        mood = self._mood_store.load()
        lines = [f"Right now it is {now:%A, %Y-%m-%d %H:%M}."]
        current = calendar.current_entry(now)
        if current is not None:
            lines.append(
                f"You are at {current.location}, busy with {current.activity} "
                f"until {current.end:%H:%M}."
            )
        else:
            lines.append(f"You are at {calendar.home_location} with nothing scheduled.")
        lines.append("")
        lines.append(build_mood_block(mood, now).rstrip())
        lines.append("")
        lines.append(
            f"Earlier — {humanize_ago(commitment.made_at, now)} — you promised "
            f"<@{commitment.user_id}> that you would: {commitment.description}."
        )
        lines.append(
            f'At the time, you said this would happen: "{commitment.due_hint}".'
        )
        lines.append("")
        if history:
            lines.append(
                "What has been said in that channel since, so you can judge whether "
                "speaking up now would feel natural or would cut across the moment:"
            )
            lines.extend(f"  {message}" for message in history)
        else:
            lines.append("Nothing has been said in that channel since she promised it.")
        return "\n".join(lines)

    async def _ensure_week_planned(self) -> None:
        now = clock.now()
        week_start = now.date() - timedelta(days=now.weekday())
        calendar = self._calendar_store.load()
        calendar.prune_past(now)
        if calendar.planned_week_start != week_start:
            hobbies = self._hobby_store.load()
            hobby_names = [hobby.name for hobby in hobbies.entries]
            new_hobby_notes = [
                f"{hobby.name} (took up {humanize_ago(acquired_at, now)})"
                for hobby in recent_hobbies(hobbies, now, config.RECENT_HOBBY_WINDOW)
                if (acquired_at := hobby.acquired_at) is not None
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
            activity_notes = self._activity_notes_store.load()
            for entry in entries:
                activity_notes.apply_to(entry)
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
        with logfire.span("generate_week_story", week_start=str(week_start)):
            try:
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
            except Exception:
                logger.exception("Failed to generate story for week %s", week_start)
                return
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

        with logfire.span(
            "on_message",
            author_id=message.author.id,
            channel_id=message.channel.id,
            message_id=message.id,
        ):
            photo_cooldown = self._photo_cooldown_store.load()
            photo_cooldown.messages_since_photo += 1
            self._photo_cooldown_store.save(photo_cooldown)
            self._queue.add(message)

            async with self._response_lock:
                if self._resting:
                    logger.debug("Resting; queued message from %s", message.author.id)
                    return
                if not await self._attempt_response():
                    self._resting = True
                    logger.info(
                        "Holding off replying for now; will catch up after a rest"
                    )
                    asyncio.create_task(self._rest_and_respond())

    def _photo_hint_for_message(self) -> str:
        photo_cooldown = self._photo_cooldown_store.load()
        if photo_cooldown.messages_since_photo >= photo_cooldown.cooldown:
            return prompts.PHOTO_HINT
        return ""

    def _on_photo_taken(self) -> None:
        self._photo_cooldown_store.save(PhotoCooldown())

    def _server_emojis_for_message(self, channel: discord.abc.Messageable) -> list[str]:
        self._messages_since_emoji_reminder += 1
        if self._messages_since_emoji_reminder < config.SERVER_EMOJI_REMINDER_INTERVAL:
            return []
        self._messages_since_emoji_reminder = 0
        guild = getattr(channel, "guild", None)
        if guild is None:
            return []
        return [str(emoji) for emoji in guild.emojis]

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
        # Quadratic falloff: a few messages barely dent her, but odds drop sharply
        # as fatigue nears FATIGUE_MAX, where she stops replying right away.
        fatigue_factor = max(0.0, 1.0 - (mood.fatigue / FATIGUE_MAX) ** 2)
        should_respond = random.random() < mood_factor * fatigue_factor
        with logfire.span(
            "attempt_response",
            mood=mood.value,
            fatigue=mood.fatigue,
            onboarding_active=onboarding_active,
            should_respond=should_respond,
        ):
            if not should_respond:
                return False
            message_count = len(self._queue)
            async with self._state_lock:
                self._mood_store.save(
                    add_fatigue(self._mood_store.load(), message_count)
                )
            for channel, messages in self._queue.flush().items():
                with logfire.span(
                    "respond_to_channel",
                    channel_id=channel.id,
                    message_count=len(messages),
                ) as span:
                    formatted = [format_message(m) for m in messages]
                    history = [
                        format_message(m, own=m.author == self.user)
                        async for m in channel.history(
                            limit=config.CHANNEL_HISTORY_LIMIT,
                            before=discord.Object(id=messages[0].id),
                        )
                    ]
                    history.reverse()
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
                    commitments = [
                        c
                        for c in self._commitment_store.load().open_entries()
                        if c.user_id in author_ids
                    ]
                    span.set_attribute("memories", len(memories))
                    span.set_attribute("images", len(images))
                    result = await self._llm_client.complete(
                        formatted,
                        channel,
                        channel.id,
                        self._calendar_store,
                        self._activity_notes_store,
                        self._inventory_store,
                        self._spending_store,
                        self._hobby_store,
                        self._story_store,
                        self._preference_store,
                        self._commitment_store,
                        now,
                        memories,
                        relations,
                        mood,
                        photo_hint=self._photo_hint_for_message(),
                        server_emojis=self._server_emojis_for_message(channel),
                        images=images,
                        waiting_since=min(
                            clock.to_local(m.created_at) for m in messages
                        ),
                        history=history,
                        commitments=commitments,
                    )
                    span.set_attribute("photo", result.photo is not None)
                    if result.photo is not None:
                        self._on_photo_taken()
                    await _send_chunked(channel, result.output, photo=result.photo)
                    asyncio.create_task(
                        self._store_memories(messages, result.output, author_ids)
                    )
                    asyncio.create_task(
                        self._update_relations(relations, messages, result.output)
                    )
            return True

    async def _store_memories(
        self, messages: list[discord.Message], bot_response: str, user_ids: list[str]
    ) -> None:
        conversation = [
            {"role": "user", "content": format_message(m)} for m in messages
        ]
        conversation.append({"role": "assistant", "content": bot_response})
        try:
            await self._memory_store.store(conversation, user_ids=user_ids)
        except Exception:
            logger.exception("Failed to store memories for user_ids=%s", user_ids)

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
        try:
            own_interests = [
                hobby.name for hobby in self._hobby_store.load().entries
            ] + [
                f"{preference.topic}: {preference.stance}"
                for preference in self._preference_store.load().entries
            ]
            for relation in relations:
                with logfire.span("update_relation", user_id=relation.user_id) as span:
                    update = await self._relation_updater.update(
                        relation, conversation, own_interests
                    )
                    if update is None:
                        continue
                    updated = apply_update(relation, update)
                    self._relation_store.save(updated)
                    span.set_attribute("attitude_delta", update.attitude_delta)
                    span.set_attribute("attitude", updated.attitude)
                    span.set_attribute("reason", update.reason)
                    logger.debug(
                        "Updated relation for user_id=%s: attitude %.1f -> %.1f "
                        "(%+d: %s)",
                        relation.user_id,
                        relation.attitude,
                        updated.attitude,
                        update.attitude_delta,
                        update.reason,
                    )
                    # Mood reacts to the moment, so it gets the raw judged delta
                    # rather than the deliberately slow change actually applied to
                    # attitude.
                    if update.attitude_delta != 0:
                        async with self._state_lock:
                            mood = apply_interaction_delta(
                                self._mood_store.load(), update.attitude_delta
                            )
                            self._mood_store.save(mood)
                        logger.debug(
                            "Mood adjusted by interaction delta=%d: %.1f",
                            update.attitude_delta,
                            mood.value,
                        )
        except Exception:
            logger.exception(
                "Failed to update relations for user_ids=%s",
                [relation.user_id for relation in relations],
            )

    async def _rest_and_respond(self) -> None:
        # Runs detached, and _resting is set before it starts. Clearing the flag
        # in `finally` rather than only on success is what keeps a failure here
        # from wedging her into permanent silence: every reply path checks
        # _resting first, and nothing else ever resets it.
        try:
            while True:
                mood = self._mood_store.load()
                mood_rest_factor = 1.5 - (mood.value / 100.0)
                max_delay = max(3.0, 5.0 * mood.fatigue * mood_rest_factor)
                delay_divisor = (
                    config.ONBOARDING_REST_DELAY_DIVISOR
                    if self._onboarding_active()
                    else 1.0
                )
                actual_delay = random.uniform(
                    3.0 / delay_divisor, max_delay / delay_divisor
                )
                self._next_attempt_at = clock.now() + timedelta(minutes=actual_delay)
                await asyncio.sleep(actual_delay * 60.0)

                # Fatigue recovers on its own while she waits: each attempt refreshes
                # the mood, which decays fatigue over the elapsed time.
                async with self._response_lock:
                    if await self._attempt_response():
                        return
        except Exception:
            logger.exception("Rest loop failed; going back to replying normally")
        finally:
            self._resting = False
            self._next_attempt_at = None

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
    # Needed to populate guild.members (used by the scheduled-posts mention
    # dropdown); must also be enabled as a privileged intent in the Discord
    # Developer Portal or the gateway will reject the connection.
    intents.members = True
    llm_client = LLMClient.create()
    memory_store = MemoryStore.create(config.MEMORY_DATA_PATH)
    relation_store = RelationStore(config.RELATION_DATA_PATH)
    relation_updater = RelationUpdater.create()
    calendar_store = CalendarStore(config.CALENDAR_DATA_PATH, config.HOME_LOCATION)
    activity_notes_store = ActivityNotesStore(config.ACTIVITY_NOTES_DATA_PATH)
    week_planner = WeekPlanner.create()
    inventory_store = InventoryStore.create(config.INVENTORY_DATA_PATH)
    spending_store = SpendingStore(config.SPENDING_DATA_PATH)
    hobby_store = HobbyStore(config.HOBBY_DATA_PATH, config.DEFAULT_HOBBIES)
    story_store = StoryStore.create(config.STORY_DATA_PATH)
    story_generator = StoryGenerator.create()
    mood_store = MoodStore(config.MOOD_DATA_PATH)
    preference_store = PreferenceStore(config.PREFERENCE_DATA_PATH)
    photo_cooldown_store = PhotoCooldownStore(config.PHOTO_COOLDOWN_DATA_PATH)
    commitment_store = CommitmentStore(config.COMMITMENT_DATA_PATH)
    commitment_timing_judge = CommitmentTimingJudge.create()
    spontaneous_store = SpontaneousStore(config.SPONTANEOUS_DATA_PATH)
    scheduled_post_store = ScheduledPostStore(config.SCHEDULED_POST_DATA_PATH)
    return LivingBot(
        llm_client=llm_client,
        memory_store=memory_store,
        relation_store=relation_store,
        relation_updater=relation_updater,
        calendar_store=calendar_store,
        activity_notes_store=activity_notes_store,
        week_planner=week_planner,
        inventory_store=inventory_store,
        spending_store=spending_store,
        hobby_store=hobby_store,
        story_store=story_store,
        story_generator=story_generator,
        mood_store=mood_store,
        preference_store=preference_store,
        photo_cooldown_store=photo_cooldown_store,
        commitment_store=commitment_store,
        commitment_timing_judge=commitment_timing_judge,
        spontaneous_store=spontaneous_store,
        scheduled_post_store=scheduled_post_store,
        intents=intents,
    )


def run() -> None:
    configure_logfire()
    token = os.environ["DISCORD_BOT_TOKEN"]
    bot = build()
    bot.run(token, log_handler=None)
