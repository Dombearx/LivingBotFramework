from unittest.mock import AsyncMock, MagicMock

import discord

from livingbot.queue import MessageQueue


def make_channel() -> MagicMock:
    channel = MagicMock()
    channel.send = AsyncMock()
    return channel


def make_message(channel: MagicMock) -> MagicMock:
    msg = MagicMock(spec=discord.Message)
    msg.channel = channel
    return msg


def test_flush_returns_unique_channels() -> None:
    queue = MessageQueue()
    channel_a = make_channel()
    channel_b = make_channel()
    queue.add(make_message(channel_a))
    queue.add(make_message(channel_b))
    queue.add(make_message(channel_a))

    channels = queue.flush()

    assert channels == [channel_a, channel_b]


def test_flush_clears_queue() -> None:
    queue = MessageQueue()
    channel = make_channel()
    queue.add(make_message(channel))

    queue.flush()

    assert queue.flush() == []


def test_flush_on_empty_queue_returns_empty_list() -> None:
    queue = MessageQueue()

    channels = queue.flush()

    assert channels == []
