import discord


class MessageQueue:
    def __init__(self) -> None:
        self._pending: list[discord.Message] = []

    def __len__(self) -> int:
        return len(self._pending)

    def add(self, message: discord.Message) -> None:
        self._pending.append(message)

    def flush(self) -> dict[discord.abc.Messageable, list[discord.Message]]:
        grouped: dict[discord.abc.Messageable, list[discord.Message]] = {}
        for msg in self._pending:
            grouped.setdefault(msg.channel, []).append(msg)
        self._pending.clear()
        return grouped
