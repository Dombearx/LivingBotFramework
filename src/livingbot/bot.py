import asyncio
import io
import logging
import os
import random
from datetime import datetime, timedelta

import discord

from livingbot import config, llm_config, prompts
from livingbot.calendar import CalendarStore, WeekPlanner
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
from livingbot.queue import MessageQueue
from livingbot.relations import Relation, RelationStore, RelationUpdater
from livingbot.spending import SpendingStore
from livingbot.tools import format_message

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
        mood_store: MoodStore,
        **kwargs: object,
    ) -> None:
        super().__init__(**kwargs)
        self._queue = MessageQueue()
        self._fatigue: float = 0.0
        self._resting: bool = False
        self._response_lock = asyncio.Lock()
        self._llm_client = llm_client
        self._memory_store = memory_store
        self._relation_store = relation_store
        self._relation_updater = relation_updater
        self._calendar_store = calendar_store
        self._week_planner = week_planner
        self._inventory_store = inventory_store
        self._spending_store = spending_store
        self._mood_store = mood_store
        self._messages_since_photo: int = 0
        self._photo_cooldown: int = random.randint(
            config.PHOTO_COOLDOWN_MIN, config.PHOTO_COOLDOWN_MAX
        )

    async def setup_hook(self) -> None:
        self.loop.create_task(self._life_loop())

    async def _life_loop(self) -> None:
        while True:
            try:
                await self._ensure_week_planned()
                self._ensure_morning_mood_refresh()
            except Exception:
                logger.exception("Life loop iteration failed")
            await asyncio.sleep(config.LIFE_LOOP_INTERVAL_SECONDS)

    def _ensure_morning_mood_refresh(self) -> None:
        now = datetime.now()
        if not (SLEEP_WINDOW_START <= now.hour < SLEEP_WINDOW_END):
            return
        mood = self._mood_store.load()
        if mood.last_sleep_date is not None and mood.last_sleep_date >= now.date():
            return
        calendar = self._calendar_store.load()
        mood = refresh_mood(mood, now, calendar)
        self._mood_store.save(mood)
        logger.info("Morning mood refresh: %.1f", mood.value)

    async def _ensure_week_planned(self) -> None:
        now = datetime.now()
        week_start = now.date() - timedelta(days=now.weekday())
        calendar = self._calendar_store.load()
        calendar.prune_past(now)
        if calendar.planned_week_start != week_start:
            entries = await self._week_planner.plan(
                week_start, config.HOBBIES, calendar.home_location
            )
            calendar.entries.extend(entries)
            calendar.planned_week_start = week_start
            logger.info(
                "Planned week starting %s with %d entries", week_start, len(entries)
            )
        self._calendar_store.save(calendar)

    async def on_ready(self) -> None:
        logger.info(
            "Logged in as %s (id=%s)", self.user, self.user.id if self.user else None
        )

    async def on_message(self, message: discord.Message) -> None:
        if message.author == self.user:
            return

        if not self._is_directed_at_bot(message):
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

    async def _attempt_response(self) -> bool:
        now = datetime.now()
        mood = refresh_mood(self._mood_store.load(), now, self._calendar_store.load())

        mood_factor = 0.5 + (mood.value / 100.0)
        if random.random() < mood_factor / (self._fatigue + 1.0):
            self._mood_store.save(mood)
            self._fatigue += len(self._queue)
            for channel, messages in self._queue.flush().items():
                formatted = [format_message(m) for m in messages]
                author_ids = list(dict.fromkeys(str(m.author.id) for m in messages))
                memories = await self._memory_store.retrieve(
                    "\n".join(formatted), user_ids=author_ids
                )
                relations = [self._relation_store.load(uid) for uid in author_ids]
                result = await self._llm_client.complete(
                    formatted,
                    channel,
                    self._calendar_store,
                    self._inventory_store,
                    self._spending_store,
                    now,
                    memories,
                    relations,
                    mood,
                    photo_hint=self._photo_hint_for_message(),
                    portrait_path=config.PORTRAIT_PATH,
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
        return False

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
                mood = self._mood_store.load()
                mood = apply_interaction_delta(mood, delta)
                self._mood_store.save(mood)
                logger.debug(
                    "Mood adjusted by interaction delta=%d: %.1f", delta, mood.value
                )

    async def _rest_and_respond(self) -> None:
        while True:
            mood = self._mood_store.load()
            mood_rest_factor = 1.5 - (mood.value / 100.0)
            max_delay = max(3.0, 5.0 * self._fatigue * mood_rest_factor)
            actual_delay = random.uniform(3.0, max_delay)
            await asyncio.sleep(actual_delay * 60.0)

            async with self._response_lock:
                self._fatigue = max(0.0, self._fatigue - actual_delay / 5.0)
                if await self._attempt_response():
                    self._resting = False
                    return

    def _is_directed_at_bot(self, message: discord.Message) -> bool:
        if self.user is not None and self.user in message.mentions:
            return True
        return self._is_reply_to_bot(message)

    def _is_reply_to_bot(self, message: discord.Message) -> bool:
        if message.reference is None or self.user is None:
            return False
        ref = message.reference.resolved
        return isinstance(ref, discord.Message) and ref.author == self.user


def run() -> None:
    token = os.environ["DISCORD_BOT_TOKEN"]
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
    mood_store = MoodStore(config.MOOD_DATA_PATH)
    bot = LivingBot(
        llm_client=llm_client,
        memory_store=memory_store,
        relation_store=relation_store,
        relation_updater=relation_updater,
        calendar_store=calendar_store,
        week_planner=week_planner,
        inventory_store=inventory_store,
        spending_store=spending_store,
        mood_store=mood_store,
        intents=intents,
    )
    bot.run(token, log_handler=None)
