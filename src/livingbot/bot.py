import logging
import os

import discord

logger = logging.getLogger(__name__)


class LivingBot(discord.Client):
    async def on_ready(self) -> None:
        logger.info(
            "Logged in as %s (id=%s)", self.user, self.user.id if self.user else None
        )

    async def on_message(self, message: discord.Message) -> None:
        if message.author == self.user:
            return

        if self.user is not None and self.user in message.mentions:
            await message.channel.send("I'm here")
            return

        if await self._is_reply_to_bot(message):
            await message.channel.send("I'm here")

    async def _is_reply_to_bot(self, message: discord.Message) -> bool:
        if message.reference is None or self.user is None:
            return False
        ref = message.reference.resolved
        if isinstance(ref, discord.Message):
            return ref.author == self.user
        # Message not in cache — fetch it
        try:
            fetched = await message.channel.fetch_message(message.reference.message_id)
            return fetched.author == self.user
        except discord.NotFound:
            return False


def run() -> None:
    token = os.environ["DISCORD_BOT_TOKEN"]
    intents = discord.Intents.default()
    intents.message_content = True
    bot = LivingBot(intents=intents)
    bot.run(token, log_handler=None)
