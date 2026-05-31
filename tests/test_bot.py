from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import discord

from livingbot.bot import LivingBot


def bot_user():
    return MagicMock(spec=discord.ClientUser)


def other_user():
    return MagicMock(spec=discord.User)


def make_bot():
    intents = discord.Intents.default()
    intents.message_content = True
    return LivingBot(intents=intents)


def make_message(author, mentions=None, reference=None):
    msg = MagicMock(spec=discord.Message)
    msg.author = author
    msg.mentions = mentions or []
    msg.reference = reference
    msg.channel = MagicMock()
    msg.channel.send = AsyncMock()
    return msg


async def test_on_message_when_author_is_bot_does_not_respond():
    bot = make_bot()
    user = bot_user()
    message = make_message(author=user)

    with patch.object(type(bot), "user", new_callable=PropertyMock, return_value=user):
        await bot.on_message(message)

    message.channel.send.assert_not_called()


async def test_on_message_when_bot_is_mentioned_sends_i_am_here():
    bot = make_bot()
    user = bot_user()
    message = make_message(author=other_user(), mentions=[user])

    with patch.object(type(bot), "user", new_callable=PropertyMock, return_value=user):
        await bot.on_message(message)

    message.channel.send.assert_called_once_with("I'm here")


async def test_on_message_when_reply_to_bot_sends_i_am_here():
    bot = make_bot()
    user = bot_user()
    message = make_message(author=other_user())

    with patch.object(type(bot), "user", new_callable=PropertyMock, return_value=user):
        with patch.object(bot, "_is_reply_to_bot", return_value=True):
            await bot.on_message(message)

    message.channel.send.assert_called_once_with("I'm here")


async def test_on_message_when_unrelated_message_sends_nothing():
    bot = make_bot()
    user = bot_user()
    message = make_message(author=other_user())

    with patch.object(type(bot), "user", new_callable=PropertyMock, return_value=user):
        await bot.on_message(message)

    message.channel.send.assert_not_called()


def test_is_reply_to_bot_when_no_reference_returns_false():
    bot = make_bot()
    user = bot_user()
    message = make_message(author=other_user(), reference=None)

    with patch.object(type(bot), "user", new_callable=PropertyMock, return_value=user):
        result = bot._is_reply_to_bot(message)

    assert result is False


def test_is_reply_to_bot_when_resolved_reference_is_bots_returns_true():
    bot = make_bot()
    user = bot_user()

    # object.__new__ produces a real discord.Message instance (passes isinstance) without
    # requiring its complex __init__; author is in __slots__ so it's directly assignable
    bot_message = object.__new__(discord.Message)
    bot_message.author = user

    reference = MagicMock(spec=discord.MessageReference)
    reference.resolved = bot_message

    message = make_message(author=other_user(), reference=reference)

    with patch.object(type(bot), "user", new_callable=PropertyMock, return_value=user):
        result = bot._is_reply_to_bot(message)

    assert result is True
