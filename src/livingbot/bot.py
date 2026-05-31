import logging
import os

import discord

from livingbot.queue import MessageQueue

logger = logging.getLogger(__name__)


class LivingBot(discord.Client):
    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._queue = MessageQueue()

    async def on_ready(self) -> None:
        logger.info(
            "Logged in as %s (id=%s)", self.user, self.user.id if self.user else None
        )

    async def on_message(self, message: discord.Message) -> None:
        if message.author == self.user:
            return

        if not self._is_directed_at_bot(message):
            return

        if self._queue.add(message):
            for channel in self._queue.flush():
                await channel.send("I'm here")

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
