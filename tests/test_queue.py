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


def test_add_below_threshold_returns_false() -> None:
    queue = MessageQueue(threshold=3)
    channel = make_channel()

    result1 = queue.add(make_message(channel))
    result2 = queue.add(make_message(channel))

    assert result1 is False
    assert result2 is False


def test_add_at_threshold_returns_true() -> None:
    queue = MessageQueue(threshold=3)
    channel = make_channel()
    queue.add(make_message(channel))
    queue.add(make_message(channel))

    result = queue.add(make_message(channel))

    assert result is True


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

    result = queue.add(make_message(channel))

    assert result is False


def test_flush_on_empty_queue_returns_empty_list() -> None:
    queue = MessageQueue(threshold=3)

    channels = queue.flush()

    assert channels == []
