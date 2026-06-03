from datetime import datetime
from unittest.mock import ANY, AsyncMock, MagicMock, PropertyMock, patch

import discord

from livingbot.bot import LivingBot, _format_message, _send_chunked
from livingbot.calendar import Calendar, PlanEntry
from livingbot.relations import Relation


def bot_user() -> MagicMock:
    return MagicMock(spec=discord.ClientUser)


def other_user() -> MagicMock:
    return MagicMock(spec=discord.User)


def make_llm_client(response: str = "llm response") -> MagicMock:
    mock_result = MagicMock()
    mock_result.output = response
    client = MagicMock()
    client.complete = AsyncMock(return_value=mock_result)
    return client


def make_memory_store() -> MagicMock:
    store = MagicMock()
    store.retrieve = AsyncMock(return_value=[])
    store.store = AsyncMock()
    return store


def make_relation_store() -> MagicMock:
    store = MagicMock()
    store.load = MagicMock(return_value=Relation(user_id="123"))
    store.save = MagicMock()
    return store


def make_relation_updater() -> MagicMock:
    updater = MagicMock()
    updater.update = AsyncMock(return_value=Relation(user_id="123"))
    return updater


def make_calendar_store(calendar: Calendar | None = None) -> MagicMock:
    store = MagicMock()
    store.load = MagicMock(
        return_value=calendar
        if calendar is not None
        else Calendar(home_location="home")
    )
    store.save = MagicMock()
    return store


def make_week_planner(entries: list[PlanEntry] | None = None) -> MagicMock:
    planner = MagicMock()
    planner.plan = AsyncMock(return_value=entries or [])
    return planner


def make_inventory_store() -> MagicMock:
    store = MagicMock()
    store.all = AsyncMock(return_value=[])
    return store


def make_bot(
    llm_client: MagicMock | None = None,
    memory_store: MagicMock | None = None,
    relation_store: MagicMock | None = None,
    relation_updater: MagicMock | None = None,
    calendar_store: MagicMock | None = None,
    week_planner: MagicMock | None = None,
    inventory_store: MagicMock | None = None,
) -> LivingBot:
    intents = discord.Intents.default()
    intents.message_content = True
    return LivingBot(
        llm_client=llm_client or make_llm_client(),
        memory_store=memory_store or make_memory_store(),
        relation_store=relation_store or make_relation_store(),
        relation_updater=relation_updater or make_relation_updater(),
        calendar_store=calendar_store or make_calendar_store(),
        week_planner=week_planner or make_week_planner(),
        inventory_store=inventory_store or make_inventory_store(),
        intents=intents,
    )


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
        bot._calendar_store,
        bot._inventory_store,
        ANY,
        [],
        [Relation(user_id="123"), Relation(user_id="123")],
    )


@patch("asyncio.create_task", side_effect=lambda coro: coro.close())
@patch("random.random", return_value=0.0)
@patch.object(LivingBot, "user", new_callable=PropertyMock)
async def test_attempt_response_retrieves_memories_with_single_author_id(
    mock_user: PropertyMock,
    mock_random: MagicMock,
    mock_create_task: MagicMock,
) -> None:
    user = bot_user()
    mock_user.return_value = user
    memory_store = make_memory_store()
    bot = make_bot(memory_store=memory_store)
    author = other_user()
    channel = make_channel()
    msg = make_message(author=author, mentions=[user], channel=channel)
    bot._queue.add(msg)

    await bot._attempt_response()

    memory_store.retrieve.assert_called_once_with(
        _format_message(msg), user_ids=[str(author.id)]
    )


@patch("asyncio.create_task", side_effect=lambda coro: coro.close())
@patch("random.random", return_value=0.0)
@patch.object(LivingBot, "user", new_callable=PropertyMock)
async def test_attempt_response_retrieves_memories_for_all_unique_authors(
    mock_user: PropertyMock,
    mock_random: MagicMock,
    mock_create_task: MagicMock,
) -> None:
    user = bot_user()
    mock_user.return_value = user
    memory_store = make_memory_store()
    bot = make_bot(memory_store=memory_store)
    author_a, author_b = other_user(), other_user()
    channel = make_channel()
    msg1 = make_message(author=author_a, mentions=[user], channel=channel)
    msg2 = make_message(author=author_b, mentions=[user], channel=channel)
    bot._queue.add(msg1)
    bot._queue.add(msg2)

    await bot._attempt_response()

    memory_store.retrieve.assert_called_once_with(
        f"{_format_message(msg1)}\n{_format_message(msg2)}",
        user_ids=[str(author_a.id), str(author_b.id)],
    )


@patch("asyncio.create_task", side_effect=lambda coro: coro.close())
@patch("random.random", return_value=0.0)
@patch.object(LivingBot, "user", new_callable=PropertyMock)
async def test_attempt_response_passes_retrieved_memories_to_llm(
    mock_user: PropertyMock,
    mock_random: MagicMock,
    mock_create_task: MagicMock,
) -> None:
    user = bot_user()
    mock_user.return_value = user
    memory_store = make_memory_store()
    memory_store.retrieve = AsyncMock(return_value=["remember this"])
    llm_client = make_llm_client()
    bot = make_bot(llm_client=llm_client, memory_store=memory_store)
    channel = make_channel()
    msg = make_message(author=other_user(), mentions=[user], channel=channel)
    bot._queue.add(msg)

    await bot._attempt_response()

    assert llm_client.complete.call_args.args[5] == ["remember this"]


@patch("random.random", return_value=0.0)
@patch.object(LivingBot, "user", new_callable=PropertyMock)
async def test_attempt_response_stores_memories_with_user_id_for_single_author(
    mock_user: PropertyMock,
    mock_random: MagicMock,
) -> None:
    user = bot_user()
    mock_user.return_value = user
    memory_store = make_memory_store()
    bot = make_bot(memory_store=memory_store)
    author = other_user()
    channel = make_channel()
    msg = make_message(author=author, mentions=[user], channel=channel)
    bot._queue.add(msg)

    tasks: list = []
    with patch("asyncio.create_task", side_effect=lambda c: tasks.append(c)):
        await bot._attempt_response()
    for t in tasks:
        await t

    assert memory_store.store.call_args.kwargs["user_id"] == str(author.id)


@patch("random.random", return_value=0.0)
@patch.object(LivingBot, "user", new_callable=PropertyMock)
async def test_attempt_response_stores_memories_globally_for_multiple_authors(
    mock_user: PropertyMock,
    mock_random: MagicMock,
) -> None:
    user = bot_user()
    mock_user.return_value = user
    memory_store = make_memory_store()
    bot = make_bot(memory_store=memory_store)
    channel = make_channel()
    msg1 = make_message(author=other_user(), mentions=[user], channel=channel)
    msg2 = make_message(author=other_user(), mentions=[user], channel=channel)
    bot._queue.add(msg1)
    bot._queue.add(msg2)

    tasks: list = []
    with patch("asyncio.create_task", side_effect=lambda c: tasks.append(c)):
        await bot._attempt_response()
    for t in tasks:
        await t

    assert memory_store.store.call_args.kwargs["user_id"] is None


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


@patch("asyncio.create_task", side_effect=lambda coro: coro.close())
@patch("random.random", return_value=0.0)
@patch.object(LivingBot, "user", new_callable=PropertyMock)
async def test_attempt_response_loads_relation_for_each_unique_author(
    mock_user: PropertyMock,
    mock_random: MagicMock,
    mock_create_task: MagicMock,
) -> None:
    user = bot_user()
    mock_user.return_value = user
    relation_store = make_relation_store()
    bot = make_bot(relation_store=relation_store)
    author_a, author_b = other_user(), other_user()
    channel = make_channel()
    msg1 = make_message(author=author_a, mentions=[user], channel=channel)
    msg2 = make_message(author=author_b, mentions=[user], channel=channel)
    bot._queue.add(msg1)
    bot._queue.add(msg2)

    await bot._attempt_response()

    assert relation_store.load.call_count == 2
    relation_store.load.assert_any_call(str(author_a.id))
    relation_store.load.assert_any_call(str(author_b.id))


@patch("asyncio.create_task", side_effect=lambda coro: coro.close())
@patch("random.random", return_value=0.0)
@patch.object(LivingBot, "user", new_callable=PropertyMock)
async def test_attempt_response_does_not_load_duplicate_author_twice(
    mock_user: PropertyMock,
    mock_random: MagicMock,
    mock_create_task: MagicMock,
) -> None:
    user = bot_user()
    mock_user.return_value = user
    relation_store = make_relation_store()
    bot = make_bot(relation_store=relation_store)
    author = other_user()
    channel = make_channel()
    msg1 = make_message(author=author, mentions=[user], channel=channel)
    msg2 = make_message(author=author, mentions=[user], channel=channel)
    bot._queue.add(msg1)
    bot._queue.add(msg2)

    await bot._attempt_response()

    relation_store.load.assert_called_once_with(str(author.id))


@patch("random.random", return_value=0.0)
@patch.object(LivingBot, "user", new_callable=PropertyMock)
async def test_update_relations_calls_updater_and_saves_for_each_relation(
    mock_user: PropertyMock,
    mock_random: MagicMock,
) -> None:
    user = bot_user()
    mock_user.return_value = user
    relation_a = Relation(user_id="aaa", attitude=10)
    relation_b = Relation(user_id="bbb", attitude=-5)
    updated_a = Relation(user_id="aaa", attitude=20)
    updated_b = Relation(user_id="bbb", attitude=-10)

    relation_updater = make_relation_updater()
    relation_updater.update = AsyncMock(side_effect=[updated_a, updated_b])
    relation_store = make_relation_store()
    bot = make_bot(relation_store=relation_store, relation_updater=relation_updater)
    msg = make_message(author=other_user(), mentions=[user])

    await bot._update_relations([relation_a, relation_b], [msg], "bot reply")

    assert relation_updater.update.call_count == 2
    relation_store.save.assert_any_call(updated_a)
    relation_store.save.assert_any_call(updated_b)


@patch("random.random", return_value=0.0)
@patch.object(LivingBot, "user", new_callable=PropertyMock)
async def test_update_relations_includes_bot_response_in_conversation(
    mock_user: PropertyMock,
    mock_random: MagicMock,
) -> None:
    user = bot_user()
    mock_user.return_value = user
    relation = Relation(user_id="aaa")
    relation_updater = make_relation_updater()
    bot = make_bot(relation_updater=relation_updater)
    msg = make_message(author=other_user(), mentions=[user])
    msg.content = "hey bot"

    await bot._update_relations([relation], [msg], "my reply")

    conversation = relation_updater.update.call_args.args[1]
    roles = [turn["role"] for turn in conversation]
    contents = [turn["content"] for turn in conversation]
    assert roles[-1] == "assistant"
    assert contents[-1] == "my reply"


@patch("livingbot.bot.datetime")
async def test_ensure_week_planned_when_week_unplanned_plans_and_saves(
    mock_datetime: MagicMock,
) -> None:
    mock_datetime.now.return_value = datetime(2026, 6, 3, 14, 30)
    entry = PlanEntry(
        activity="gym",
        location="gym",
        start=datetime(2026, 6, 4, 18, 0),
        end=datetime(2026, 6, 4, 19, 30),
    )
    calendar_store = make_calendar_store(Calendar(home_location="home"))
    week_planner = make_week_planner([entry])
    bot = make_bot(calendar_store=calendar_store, week_planner=week_planner)

    await bot._ensure_week_planned()

    week_start = datetime(2026, 6, 1).date()
    week_planner.plan.assert_called_once_with(week_start, ["gym"], "home")
    saved = calendar_store.save.call_args.args[0]
    assert saved.entries == [entry]
    assert saved.planned_week_start == week_start


@patch("livingbot.bot.datetime")
async def test_ensure_week_planned_when_week_already_planned_does_not_replan(
    mock_datetime: MagicMock,
) -> None:
    mock_datetime.now.return_value = datetime(2026, 6, 3, 14, 30)
    calendar = Calendar(
        home_location="home", planned_week_start=datetime(2026, 6, 1).date()
    )
    week_planner = make_week_planner()
    bot = make_bot(
        calendar_store=make_calendar_store(calendar), week_planner=week_planner
    )

    await bot._ensure_week_planned()

    week_planner.plan.assert_not_called()


@patch("livingbot.bot.datetime")
async def test_ensure_week_planned_prunes_finished_entries(
    mock_datetime: MagicMock,
) -> None:
    mock_datetime.now.return_value = datetime(2026, 6, 3, 14, 30)
    finished = PlanEntry(
        activity="gym",
        location="gym",
        start=datetime(2026, 6, 1, 18, 0),
        end=datetime(2026, 6, 1, 19, 30),
    )
    calendar = Calendar(
        home_location="home",
        planned_week_start=datetime(2026, 6, 1).date(),
        entries=[finished],
    )
    calendar_store = make_calendar_store(calendar)
    bot = make_bot(calendar_store=calendar_store)

    await bot._ensure_week_planned()

    saved = calendar_store.save.call_args.args[0]
    assert saved.entries == []
