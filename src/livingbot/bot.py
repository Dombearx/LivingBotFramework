import asyncio
import logging
import os
import random

import discord

from livingbot.queue import MessageQueue

logger = logging.getLogger(__name__)


class LivingBot(discord.Client):
    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._queue = MessageQueue()
        self._fatigue: float = 0.0
        self._resting: bool = False

    async def on_ready(self) -> None:
        logger.info(
            "Logged in as %s (id=%s)", self.user, self.user.id if self.user else None
        )

    async def on_message(self, message: discord.Message) -> None:
        if message.author == self.user:
            return

        if not self._is_directed_at_bot(message):
            return

        self._queue.add(message)
        self._fatigue += 1.0

        if not self._resting:
            if not await self._attempt_response():
                self._resting = True
                asyncio.create_task(self._rest_and_respond())

    async def _attempt_response(self) -> bool:
        if random.random() < 1.0 / (self._fatigue + 1.0):
            for channel in self._queue.flush():
                await channel.send("I'm here")
            return True
        return False

    async def _rest_and_respond(self) -> None:
        while True:
            max_delay = max(3.0, 5.0 * self._fatigue)
            actual_delay = random.uniform(3.0, max_delay)
            await asyncio.sleep(actual_delay * 60.0)

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
    bot = LivingBot(intents=intents)
    bot.run(token, log_handler=None)
