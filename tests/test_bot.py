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


@patch.object(LivingBot, "user", new_callable=PropertyMock)
async def test_on_message_when_author_is_bot_does_not_respond(mock_user):
    user = bot_user()
    mock_user.return_value = user
    bot = make_bot()
    message = make_message(author=user)

    await bot.on_message(message)

    message.channel.send.assert_not_called()


@patch.object(LivingBot, "user", new_callable=PropertyMock)
async def test_on_message_when_bot_is_mentioned_sends_i_am_here(mock_user):
    user = bot_user()
    mock_user.return_value = user
    bot = make_bot()
    message = make_message(author=other_user(), mentions=[user])

    await bot.on_message(message)

    message.channel.send.assert_called_once_with("I'm here")


@patch.object(LivingBot, "_is_reply_to_bot", return_value=True)
@patch.object(LivingBot, "user", new_callable=PropertyMock)
async def test_on_message_when_reply_to_bot_sends_i_am_here(mock_user, _mock_reply):
    user = bot_user()
    mock_user.return_value = user
    bot = make_bot()
    message = make_message(author=other_user())

    await bot.on_message(message)

    message.channel.send.assert_called_once_with("I'm here")


@patch.object(LivingBot, "user", new_callable=PropertyMock)
async def test_on_message_when_unrelated_message_sends_nothing(mock_user):
    user = bot_user()
    mock_user.return_value = user
    bot = make_bot()
    message = make_message(author=other_user())

    await bot.on_message(message)

    message.channel.send.assert_not_called()


@patch.object(LivingBot, "user", new_callable=PropertyMock)
def test_is_reply_to_bot_when_no_reference_returns_false(mock_user):
    user = bot_user()
    mock_user.return_value = user
    bot = make_bot()
    message = make_message(author=other_user(), reference=None)

    result = bot._is_reply_to_bot(message)

    assert result is False


@patch.object(LivingBot, "user", new_callable=PropertyMock)
def test_is_reply_to_bot_when_resolved_reference_is_bots_returns_true(mock_user):
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
