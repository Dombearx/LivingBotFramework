from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import discord

from livingbot.bot import LivingBot


def bot_user() -> MagicMock:
    return MagicMock(spec=discord.ClientUser)


def other_user() -> MagicMock:
    return MagicMock(spec=discord.User)


def make_bot() -> LivingBot:
    intents = discord.Intents.default()
    intents.message_content = True
    return LivingBot(intents=intents)


def make_message(
    author: MagicMock,
    mentions: list | None = None,
    reference: MagicMock | None = None,
    channel: MagicMock | None = None,
) -> MagicMock:
    msg = MagicMock(spec=discord.Message)
    msg.author = author
    msg.mentions = mentions or []
    msg.reference = reference
    if channel is None:
        msg.channel = MagicMock()
        msg.channel.send = AsyncMock()
    else:
        msg.channel = channel
    return msg


def make_channel() -> MagicMock:
    channel = MagicMock()
    channel.send = AsyncMock()
    return channel


@patch.object(LivingBot, "user", new_callable=PropertyMock)
async def test_on_message_when_author_is_bot_does_not_respond(
    mock_user: PropertyMock,
) -> None:
    user = bot_user()
    mock_user.return_value = user
    bot = make_bot()
    message = make_message(author=user)

    await bot.on_message(message)

    message.channel.send.assert_not_called()


@patch.object(LivingBot, "user", new_callable=PropertyMock)
async def test_on_message_when_bot_is_mentioned_below_threshold_sends_nothing(
    mock_user: PropertyMock,
) -> None:
    user = bot_user()
    mock_user.return_value = user
    bot = make_bot()
    message = make_message(author=other_user(), mentions=[user])

    await bot.on_message(message)

    message.channel.send.assert_not_called()


@patch.object(LivingBot, "user", new_callable=PropertyMock)
async def test_on_message_when_threshold_reached_replies_to_each_channel_once(
    mock_user: PropertyMock,
) -> None:
    user = bot_user()
    mock_user.return_value = user
    bot = make_bot()
    channel_a = make_channel()
    channel_b = make_channel()

    await bot.on_message(
        make_message(author=other_user(), mentions=[user], channel=channel_a)
    )
    await bot.on_message(
        make_message(author=other_user(), mentions=[user], channel=channel_b)
    )
    await bot.on_message(
        make_message(author=other_user(), mentions=[user], channel=channel_a)
    )

    channel_a.send.assert_called_once_with("I'm here")
    channel_b.send.assert_called_once_with("I'm here")


@patch.object(LivingBot, "user", new_callable=PropertyMock)
async def test_on_message_after_flush_queue_resets(mock_user: PropertyMock) -> None:
    user = bot_user()
    mock_user.return_value = user
    bot = make_bot()
    channel = make_channel()

    for _ in range(3):
        await bot.on_message(
            make_message(author=other_user(), mentions=[user], channel=channel)
        )

    channel.send.reset_mock()
    await bot.on_message(
        make_message(author=other_user(), mentions=[user], channel=channel)
    )

    channel.send.assert_not_called()


@patch.object(LivingBot, "user", new_callable=PropertyMock)
async def test_on_message_when_unrelated_message_does_not_contribute_to_queue(
    mock_user: PropertyMock,
) -> None:
    user = bot_user()
    mock_user.return_value = user
    bot = make_bot()
    channel = make_channel()

    for _ in range(3):
        await bot.on_message(make_message(author=other_user(), channel=channel))

    channel.send.assert_not_called()


@patch.object(LivingBot, "user", new_callable=PropertyMock)
async def test_on_message_when_reply_to_bot_below_threshold_sends_nothing(
    mock_user: PropertyMock,
) -> None:
    user = bot_user()
    mock_user.return_value = user
    bot = make_bot()

    bot_message = object.__new__(discord.Message)
    bot_message.author = user
    reference = MagicMock(spec=discord.MessageReference)
    reference.resolved = bot_message
    message = make_message(author=other_user(), reference=reference)

    await bot.on_message(message)

    message.channel.send.assert_not_called()


@patch.object(LivingBot, "user", new_callable=PropertyMock)
def test_is_reply_to_bot_when_no_reference_returns_false(
    mock_user: PropertyMock,
) -> None:
    user = bot_user()
    mock_user.return_value = user
    bot = make_bot()
    message = make_message(author=other_user(), reference=None)

    result = bot._is_reply_to_bot(message)

    assert result is False


@patch.object(LivingBot, "user", new_callable=PropertyMock)
def test_is_reply_to_bot_when_resolved_reference_is_bots_returns_true(
    mock_user: PropertyMock,
) -> None:
    user = bot_user()
    mock_user.return_value = user
    bot = make_bot()

    # object.__new__ produces a real discord.Message instance (passes isinstance) without
    # requiring its complex __init__; author is in __slots__ so it's directly assignable
    bot_message = object.__new__(discord.Message)
    bot_message.author = user

    reference = MagicMock(spec=discord.MessageReference)
    reference.resolved = bot_message
    message = make_message(author=other_user(), reference=reference)

    result = bot._is_reply_to_bot(message)

    assert result is True
