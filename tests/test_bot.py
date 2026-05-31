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
async def test_on_message_when_unrelated_message_does_not_trigger_response(
    mock_user: PropertyMock,
) -> None:
    user = bot_user()
    mock_user.return_value = user
    bot = make_bot()
    channel = make_channel()

    await bot.on_message(make_message(author=other_user(), channel=channel))

    channel.send.assert_not_called()


@patch("random.random", return_value=0.0)
@patch.object(LivingBot, "user", new_callable=PropertyMock)
async def test_on_message_when_random_favors_immediate_sends_response(
    mock_user: PropertyMock,
    mock_random: MagicMock,
) -> None:
    user = bot_user()
    mock_user.return_value = user
    bot = make_bot()
    channel = make_channel()

    await bot.on_message(
        make_message(author=other_user(), mentions=[user], channel=channel)
    )

    channel.send.assert_called_once_with("I'm here")


@patch("asyncio.create_task", side_effect=lambda coro: coro.close())
@patch("random.random", return_value=0.99)
@patch.object(LivingBot, "user", new_callable=PropertyMock)
async def test_on_message_when_random_disfavors_immediate_does_not_send(
    mock_user: PropertyMock,
    mock_random: MagicMock,
    mock_create_task: MagicMock,
) -> None:
    user = bot_user()
    mock_user.return_value = user
    bot = make_bot()
    bot._fatigue = 1.0
    channel = make_channel()

    await bot.on_message(
        make_message(author=other_user(), mentions=[user], channel=channel)
    )

    channel.send.assert_not_called()


@patch("asyncio.create_task", side_effect=lambda coro: coro.close())
@patch("random.random", return_value=0.99)
@patch.object(LivingBot, "user", new_callable=PropertyMock)
async def test_on_message_when_random_disfavors_immediate_sets_resting(
    mock_user: PropertyMock,
    mock_random: MagicMock,
    mock_create_task: MagicMock,
) -> None:
    user = bot_user()
    mock_user.return_value = user
    bot = make_bot()
    bot._fatigue = 1.0

    await bot.on_message(make_message(author=other_user(), mentions=[user]))

    assert bot._resting is True


@patch("random.random", return_value=0.0)
@patch.object(LivingBot, "user", new_callable=PropertyMock)
async def test_on_message_increments_fatigue_on_directed_message(
    mock_user: PropertyMock,
    mock_random: MagicMock,
) -> None:
    user = bot_user()
    mock_user.return_value = user
    bot = make_bot()

    await bot.on_message(make_message(author=other_user(), mentions=[user]))

    assert bot._fatigue == 1.0


@patch.object(LivingBot, "user", new_callable=PropertyMock)
async def test_on_message_when_resting_queues_without_sending(
    mock_user: PropertyMock,
) -> None:
    user = bot_user()
    mock_user.return_value = user
    bot = make_bot()
    bot._resting = True
    channel = make_channel()

    await bot.on_message(
        make_message(author=other_user(), mentions=[user], channel=channel)
    )

    channel.send.assert_not_called()


@patch.object(LivingBot, "user", new_callable=PropertyMock)
async def test_on_message_when_resting_increments_fatigue(
    mock_user: PropertyMock,
) -> None:
    user = bot_user()
    mock_user.return_value = user
    bot = make_bot()
    bot._resting = True
    bot._fatigue = 2.0

    await bot.on_message(make_message(author=other_user(), mentions=[user]))

    assert bot._fatigue == 3.0


@patch("asyncio.sleep", new_callable=AsyncMock)
@patch("random.uniform", return_value=5.0)
@patch.object(LivingBot, "user", new_callable=PropertyMock)
async def test_rest_and_respond_sends_to_queued_channels_and_clears_resting(
    mock_user: PropertyMock,
    mock_uniform: MagicMock,
    mock_sleep: AsyncMock,
) -> None:
    user = bot_user()
    mock_user.return_value = user
    bot = make_bot()
    bot._resting = True
    bot._fatigue = 2.0
    channel = make_channel()
    bot._queue.add(make_message(author=other_user(), mentions=[user], channel=channel))

    await bot._rest_and_respond(2.0)

    channel.send.assert_called_once_with("I'm here")
    assert bot._resting is False


@patch("asyncio.sleep", new_callable=AsyncMock)
@patch("random.uniform", return_value=10.0)
@patch.object(LivingBot, "user", new_callable=PropertyMock)
async def test_rest_and_respond_reduces_fatigue_by_actual_delay_over_five(
    mock_user: PropertyMock,
    mock_uniform: MagicMock,
    mock_sleep: AsyncMock,
) -> None:
    user = bot_user()
    mock_user.return_value = user
    bot = make_bot()
    bot._fatigue = 3.0

    await bot._rest_and_respond(2.0)

    # actual=10 min, reduction=10/5=2.0, new_fatigue=max(0, 3.0-2.0)=1.0
    assert bot._fatigue == 1.0


@patch("asyncio.sleep", new_callable=AsyncMock)
@patch("random.uniform", return_value=10.0)
@patch.object(LivingBot, "user", new_callable=PropertyMock)
async def test_rest_and_respond_fatigue_does_not_go_below_zero(
    mock_user: PropertyMock,
    mock_uniform: MagicMock,
    mock_sleep: AsyncMock,
) -> None:
    user = bot_user()
    mock_user.return_value = user
    bot = make_bot()
    bot._fatigue = 1.0

    await bot._rest_and_respond(2.0)

    # actual=10 min, reduction=10/5=2.0, new_fatigue=max(0, 1.0-2.0)=0.0
    assert bot._fatigue == 0.0


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
