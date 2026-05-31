import discord

THRESHOLD = 3


class MessageQueue:
    def __init__(self, threshold: int = THRESHOLD) -> None:
        self._threshold = threshold
        self._pending: list[discord.Message] = []

    def add(self, message: discord.Message) -> bool:
        self._pending.append(message)
        return len(self._pending) >= self._threshold

    def flush(self) -> list[discord.abc.Messageable]:
        seen: dict[discord.abc.Messageable, None] = {}
        for msg in self._pending:
            seen.setdefault(msg.channel, None)
        self._pending.clear()
        return list(seen.keys())
