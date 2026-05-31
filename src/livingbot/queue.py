import discord


class MessageQueue:
    def __init__(self) -> None:
        self._pending: list[discord.Message] = []

    def __len__(self) -> int:
        return len(self._pending)

    def add(self, message: discord.Message) -> None:
        self._pending.append(message)

    def flush(self) -> list[discord.abc.Messageable]:
        seen: dict[discord.abc.Messageable, None] = {}
        for msg in self._pending:
            seen.setdefault(msg.channel, None)
        self._pending.clear()
        return list(seen.keys())

    def flush_messages(self) -> list[discord.Message]:
        latest: dict[discord.abc.Messageable, discord.Message] = {}
        for msg in self._pending:
            latest[msg.channel] = msg
        self._pending.clear()
        return list(latest.values())
