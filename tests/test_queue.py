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


def test_is_ready_below_threshold_returns_false() -> None:
    queue = MessageQueue(threshold=3)
    channel = make_channel()
    queue.add(make_message(channel))
    queue.add(make_message(channel))

    assert queue.is_ready() is False


def test_is_ready_at_threshold_returns_true() -> None:
    queue = MessageQueue(threshold=3)
    channel = make_channel()
    queue.add(make_message(channel))
    queue.add(make_message(channel))
    queue.add(make_message(channel))

    assert queue.is_ready() is True


def test_flush_returns_unique_channels() -> None:
    queue = MessageQueue(threshold=3)
    channel_a = make_channel()
    channel_b = make_channel()
    queue.add(make_message(channel_a))
    queue.add(make_message(channel_b))
    queue.add(make_message(channel_a))

    channels = queue.flush()

    assert channels == [channel_a, channel_b]


def test_flush_clears_queue() -> None:
    queue = MessageQueue(threshold=3)
    channel = make_channel()
    queue.add(make_message(channel))
    queue.add(make_message(channel))
    queue.add(make_message(channel))
    queue.flush()

    assert queue.is_ready() is False


def test_flush_on_empty_queue_returns_empty_list() -> None:
    queue = MessageQueue(threshold=3)

    channels = queue.flush()

    assert channels == []
