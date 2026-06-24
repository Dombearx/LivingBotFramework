from __future__ import annotations

from typing import TYPE_CHECKING

import discord

if TYPE_CHECKING:
    from discord.abc import MessageableChannel


class MessageQueue:
    def __init__(self) -> None:
        self._pending: list[discord.Message] = []

    def __len__(self) -> int:
        return len(self._pending)

    def add(self, message: discord.Message) -> None:
        self._pending.append(message)

    def flush(self) -> dict[MessageableChannel, list[discord.Message]]:
        grouped: dict[MessageableChannel, list[discord.Message]] = {}
        for msg in self._pending:
            grouped.setdefault(msg.channel, []).append(msg)
        self._pending.clear()
        return grouped
