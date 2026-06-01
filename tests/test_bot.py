from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import discord

from livingbot.bot import LivingBot, _format_message, _send_chunked


def bot_user() -> MagicMock:
    return MagicMock(spec=discord.ClientUser)


def other_user() -> MagicMock:
    return MagicMock(spec=discord.User)


def make_llm_client(response: str = "llm response") -> MagicMock:
    client = MagicMock()
    client.complete = AsyncMock(return_value=response)
    return client


def make_bot(llm_client: MagicMock | None = None) -> LivingBot:
    intents = discord.Intents.default()
    intents.message_content = True
    return LivingBot(llm_client=llm_client or make_llm_client(), intents=intents)


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
async def test_on_message_when_random_favors_immediate_sends_llm_response(
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

    channel.send.assert_called_once_with("llm response")


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


@patch("asyncio.sleep", new_callable=AsyncMock)
@patch("random.random", return_value=0.0)
@patch("random.uniform", return_value=5.0)
@patch.object(LivingBot, "user", new_callable=PropertyMock)
async def test_rest_and_respond_sends_llm_response_and_clears_resting(
    mock_user: PropertyMock,
    mock_uniform: MagicMock,
    mock_random: MagicMock,
    mock_sleep: AsyncMock,
) -> None:
    user = bot_user()
    mock_user.return_value = user
    bot = make_bot()
    bot._resting = True
    bot._fatigue = 2.0
    channel = make_channel()
    bot._queue.add(make_message(author=other_user(), mentions=[user], channel=channel))

    await bot._rest_and_respond()

    channel.send.assert_called_once_with("llm response")
    assert bot._resting is False


@patch("asyncio.sleep", new_callable=AsyncMock)
@patch("random.random", return_value=0.0)
@patch("random.uniform", return_value=10.0)
@patch.object(LivingBot, "user", new_callable=PropertyMock)
async def test_rest_and_respond_reduces_fatigue_by_actual_delay_over_five(
    mock_user: PropertyMock,
    mock_uniform: MagicMock,
    mock_random: MagicMock,
    mock_sleep: AsyncMock,
) -> None:
    user = bot_user()
    mock_user.return_value = user
    bot = make_bot()
    bot._fatigue = 3.0

    await bot._rest_and_respond()

    # actual=10 min, reduction=10/5=2.0, fatigue=max(0, 3.0-2.0)=1.0
    assert bot._fatigue == 1.0


@patch("asyncio.sleep", new_callable=AsyncMock)
@patch("random.random", return_value=0.0)
@patch("random.uniform", return_value=10.0)
@patch.object(LivingBot, "user", new_callable=PropertyMock)
async def test_rest_and_respond_fatigue_reduction_is_clamped_to_zero(
    mock_user: PropertyMock,
    mock_uniform: MagicMock,
    mock_random: MagicMock,
    mock_sleep: AsyncMock,
) -> None:
    user = bot_user()
    mock_user.return_value = user
    bot = make_bot()
    bot._fatigue = 1.0

    await bot._rest_and_respond()

    # actual=10 min, reduction=10/5=2.0 > fatigue=1.0, clamped to 0.0
    assert bot._fatigue == 0.0


@patch("asyncio.sleep", new_callable=AsyncMock)
@patch("random.random", side_effect=[0.99, 0.0])
@patch("random.uniform", return_value=5.0)
@patch.object(LivingBot, "user", new_callable=PropertyMock)
async def test_rest_and_respond_loops_until_random_favors_response(
    mock_user: PropertyMock,
    mock_uniform: MagicMock,
    mock_random: MagicMock,
    mock_sleep: AsyncMock,
) -> None:
    user = bot_user()
    mock_user.return_value = user
    bot = make_bot()
    bot._resting = True
    bot._fatigue = 3.0
    channel = make_channel()
    bot._queue.add(make_message(author=other_user(), mentions=[user], channel=channel))

    await bot._rest_and_respond()

    # iteration 1: reduce 3.0-1.0=2.0, roll 0.99 > 1/3 → loop
    # iteration 2: reduce 2.0-1.0=1.0, roll 0.0 < 1/2 → respond, 1 msg → fatigue=2.0
    channel.send.assert_called_once_with("llm response")
    assert bot._resting is False


def test_format_message_includes_id_timestamp_author_and_content() -> None:
    msg = MagicMock(spec=discord.Message)
    msg.id = 987654321
    msg.created_at.strftime.return_value = "2024-06-01 10:00:00"
    msg.author.display_name = "Alice"
    msg.content = "hello world"

    result = _format_message(msg)

    assert result == "[id:987654321] [2024-06-01 10:00:00] Alice: hello world"


@patch("random.random", return_value=0.0)
@patch.object(LivingBot, "user", new_callable=PropertyMock)
async def test_attempt_response_sends_all_queued_channel_messages_to_llm(
    mock_user: PropertyMock,
    mock_random: MagicMock,
) -> None:
    user = bot_user()
    mock_user.return_value = user
    llm_client = make_llm_client()
    bot = make_bot(llm_client)
    channel = make_channel()
    msg1 = make_message(author=other_user(), mentions=[user], channel=channel)
    msg1.content = "first"
    msg2 = make_message(author=other_user(), mentions=[user], channel=channel)
    msg2.content = "second"
    bot._queue.add(msg1)
    bot._queue.add(msg2)

    await bot._attempt_response()

    llm_client.complete.assert_called_once_with(
        [_format_message(msg1), _format_message(msg2)],
        channel,
    )


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


async def test_send_chunked_when_response_fits_sends_single_message() -> None:
    channel = make_channel()

    await _send_chunked(channel, "short response")

    channel.send.assert_called_once_with("short response")


async def test_send_chunked_when_response_exceeds_limit_splits_into_chunks() -> None:
    channel = make_channel()
    text = "x" * 2500

    await _send_chunked(channel, text)

    assert channel.send.call_count == 2
    channel.send.assert_any_call("x" * 2000)
    channel.send.assert_any_call("x" * 500)
