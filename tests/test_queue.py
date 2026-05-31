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


def test_len_returns_pending_count() -> None:
    queue = MessageQueue()
    channel = make_channel()
    queue.add(make_message(channel))
    queue.add(make_message(channel))

    assert len(queue) == 2


def test_flush_groups_all_messages_by_channel() -> None:
    queue = MessageQueue()
    channel_a = make_channel()
    channel_b = make_channel()
    msg_a1 = make_message(channel_a)
    msg_b1 = make_message(channel_b)
    msg_a2 = make_message(channel_a)
    queue.add(msg_a1)
    queue.add(msg_b1)
    queue.add(msg_a2)

    result = queue.flush()

    assert result[channel_a] == [msg_a1, msg_a2]
    assert result[channel_b] == [msg_b1]


def test_flush_clears_queue() -> None:
    queue = MessageQueue()
    channel = make_channel()
    queue.add(make_message(channel))

    queue.flush()

    assert queue.flush() == {}


def test_flush_on_empty_queue_returns_empty_dict() -> None:
    queue = MessageQueue()

    result = queue.flush()

    assert result == {}
