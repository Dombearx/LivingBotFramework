from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import discord
import pytest

from livingbot.bot import LivingBot


@pytest.fixture
def bot_user():
    return MagicMock(spec=discord.ClientUser)


@pytest.fixture
def other_user():
    return MagicMock(spec=discord.User)


@pytest.fixture
def bot():
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
    msg.channel.fetch_message = AsyncMock()
    return msg


async def test_on_message_when_author_is_bot_does_not_respond(bot, bot_user):
    message = make_message(author=bot_user)

    with patch.object(type(bot), "user", new_callable=PropertyMock, return_value=bot_user):
        await bot.on_message(message)

    message.channel.send.assert_not_called()


async def test_on_message_when_bot_is_mentioned_sends_i_am_here(bot, bot_user, other_user):
    message = make_message(author=other_user, mentions=[bot_user])

    with patch.object(type(bot), "user", new_callable=PropertyMock, return_value=bot_user):
        await bot.on_message(message)

    message.channel.send.assert_called_once_with("I'm here")


async def test_on_message_when_reply_to_bot_sends_i_am_here(bot, bot_user, other_user):
    message = make_message(author=other_user)

    with patch.object(type(bot), "user", new_callable=PropertyMock, return_value=bot_user):
        with patch.object(bot, "_is_reply_to_bot", new=AsyncMock(return_value=True)):
            await bot.on_message(message)

    message.channel.send.assert_called_once_with("I'm here")


async def test_on_message_when_unrelated_message_sends_nothing(bot, bot_user, other_user):
    message = make_message(author=other_user)

    with patch.object(type(bot), "user", new_callable=PropertyMock, return_value=bot_user):
        await bot.on_message(message)

    message.channel.send.assert_not_called()


async def test_is_reply_to_bot_when_no_reference_returns_false(bot, bot_user, other_user):
    message = make_message(author=other_user, reference=None)

    with patch.object(type(bot), "user", new_callable=PropertyMock, return_value=bot_user):
        result = await bot._is_reply_to_bot(message)

    assert result is False


async def test_is_reply_to_bot_when_resolved_reference_is_bots_returns_true(bot, bot_user, other_user):
    # object.__new__ produces a real discord.Message instance (passes isinstance) without
    # requiring its complex __init__; author is in __slots__ so it's directly assignable
    bot_message = object.__new__(discord.Message)
    bot_message.author = bot_user

    reference = MagicMock(spec=discord.MessageReference)
    reference.resolved = bot_message

    message = make_message(author=other_user, reference=reference)

    with patch.object(type(bot), "user", new_callable=PropertyMock, return_value=bot_user):
        result = await bot._is_reply_to_bot(message)

    assert result is True


async def test_is_reply_to_bot_when_reference_not_cached_fetches_and_returns_true(bot, bot_user, other_user):
    fetched = MagicMock()
    fetched.author = bot_user

    reference = MagicMock(spec=discord.MessageReference)
    reference.resolved = None
    reference.message_id = 999

    message = make_message(author=other_user, reference=reference)
    message.channel.fetch_message = AsyncMock(return_value=fetched)

    with patch.object(type(bot), "user", new_callable=PropertyMock, return_value=bot_user):
        result = await bot._is_reply_to_bot(message)

    assert result is True
    message.channel.fetch_message.assert_called_once_with(999)


async def test_is_reply_to_bot_when_fetched_message_not_found_returns_false(bot, bot_user, other_user):
    reference = MagicMock(spec=discord.MessageReference)
    reference.resolved = None
    reference.message_id = 999

    message = make_message(author=other_user, reference=reference)
    message.channel.fetch_message = AsyncMock(
        side_effect=discord.NotFound(MagicMock(), "not found")
    )

    with patch.object(type(bot), "user", new_callable=PropertyMock, return_value=bot_user):
        result = await bot._is_reply_to_bot(message)

    assert result is False
