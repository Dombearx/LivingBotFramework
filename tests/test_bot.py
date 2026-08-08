import asyncio
import contextlib
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import ANY, AsyncMock, MagicMock, PropertyMock, patch

import discord

from livingbot import config, prompts
from livingbot.bot import (
    LivingBot,
    _pick_story_slot,
    _random_free_moment,
    _send_chunked,
    format_message,
)
from livingbot.calendar import Calendar, PlanEntry
from livingbot.commitment_timing import CommitmentTimingDecision
from livingbot.commitments import Commitment, Commitments
from livingbot.directory import Directory
from livingbot.hobbies import Hobbies, Hobby, HobbyLevel
from livingbot.mood import Mood
from livingbot.photo import PhotoCooldown
from livingbot.preferences import Preferences
from livingbot.relations import Relation, RelationUpdate, apply_update
from livingbot.scheduled_posts import ScheduledPost, ScheduledPosts
from livingbot.stories import Story

# A fixed afternoon moment: outside the sleep window and with no elapsed time
# since the mood was last refreshed, so fatigue stays put during a test.
STABLE_NOW = datetime(2026, 6, 24, 15, 0)


def bot_user() -> MagicMock:
    return MagicMock(spec=discord.ClientUser)


def other_user() -> MagicMock:
    return MagicMock(spec=discord.User)


def make_llm_client(response: str = "llm response") -> MagicMock:
    mock_result = MagicMock()
    mock_result.output = response
    mock_result.photo = None
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
    updater.update = AsyncMock(
        return_value=RelationUpdate(attitude_delta=0, reason="nothing notable")
    )
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


def make_spending_store() -> MagicMock:
    store = MagicMock()
    store.summary = MagicMock(return_value="Spending budget: 4 pts left this week.")
    store.load = MagicMock()
    store.can_afford = MagicMock(return_value=True)
    store.record = MagicMock()
    return store


def make_mood_store(mood: Mood | None = None) -> MagicMock:
    store = MagicMock()
    store.load = MagicMock(return_value=mood if mood is not None else Mood())
    store.save = MagicMock()
    return store


def make_hobby_store(hobbies: Hobbies | None = None) -> MagicMock:
    store = MagicMock()
    store.load = MagicMock(return_value=hobbies if hobbies is not None else Hobbies())
    store.save = MagicMock()
    return store


def make_preference_store(preferences: Preferences | None = None) -> MagicMock:
    store = MagicMock()
    store.load = MagicMock(
        return_value=preferences if preferences is not None else Preferences()
    )
    store.save = MagicMock()
    return store


def make_photo_cooldown_store(
    photo_cooldown: PhotoCooldown | None = None,
) -> MagicMock:
    store = MagicMock()
    store.load = MagicMock(
        return_value=photo_cooldown if photo_cooldown is not None else PhotoCooldown()
    )
    store.save = MagicMock()
    return store


def make_story_generator() -> MagicMock:
    generator = MagicMock()
    generator.generate = AsyncMock(return_value=None)
    return generator


def make_story_store() -> MagicMock:
    store = MagicMock()
    store.untold = AsyncMock(return_value=[])
    store.prune_stale = AsyncMock()
    store.recent_summaries = AsyncMock(return_value=[])
    store.add = AsyncMock()
    return store


def make_commitment_store(commitments: Commitments | None = None) -> MagicMock:
    store = MagicMock()
    store.load = MagicMock(return_value=commitments or Commitments())
    store.save = MagicMock()
    return store


def make_commitment_timing_judge() -> MagicMock:
    judge = MagicMock()
    judge.decide = AsyncMock(return_value=None)
    return judge


def make_reply_shape_labeller() -> MagicMock:
    labeller = MagicMock()
    labeller.label = AsyncMock(return_value=None)
    return labeller


def make_scheduled_post_store(posts: ScheduledPosts | None = None) -> MagicMock:
    store = MagicMock()
    store.load = MagicMock(return_value=posts or ScheduledPosts())
    store.save = MagicMock()
    return store


def make_bot(
    llm_client: MagicMock | None = None,
    memory_store: MagicMock | None = None,
    relation_store: MagicMock | None = None,
    relation_updater: MagicMock | None = None,
    calendar_store: MagicMock | None = None,
    activity_notes_store: MagicMock | None = None,
    week_planner: MagicMock | None = None,
    inventory_store: MagicMock | None = None,
    spending_store: MagicMock | None = None,
    hobby_store: MagicMock | None = None,
    story_store: MagicMock | None = None,
    story_generator: MagicMock | None = None,
    mood_store: MagicMock | None = None,
    preference_store: MagicMock | None = None,
    photo_cooldown_store: MagicMock | None = None,
    commitment_store: MagicMock | None = None,
    commitment_timing_judge: MagicMock | None = None,
    reply_shape_labeller: MagicMock | None = None,
    scheduled_post_store: MagicMock | None = None,
) -> LivingBot:
    intents = discord.Intents.default()
    intents.message_content = True
    return LivingBot(
        llm_client=llm_client or make_llm_client(),
        memory_store=memory_store or make_memory_store(),
        relation_store=relation_store or make_relation_store(),
        relation_updater=relation_updater or make_relation_updater(),
        calendar_store=calendar_store or make_calendar_store(),
        activity_notes_store=activity_notes_store or MagicMock(),
        week_planner=week_planner or make_week_planner(),
        inventory_store=inventory_store or make_inventory_store(),
        spending_store=spending_store or make_spending_store(),
        hobby_store=hobby_store or make_hobby_store(),
        story_store=story_store or make_story_store(),
        story_generator=story_generator or make_story_generator(),
        mood_store=mood_store or make_mood_store(),
        preference_store=preference_store or make_preference_store(),
        photo_cooldown_store=photo_cooldown_store or make_photo_cooldown_store(),
        commitment_store=commitment_store or make_commitment_store(),
        commitment_timing_judge=commitment_timing_judge
        or make_commitment_timing_judge(),
        reply_shape_labeller=reply_shape_labeller or make_reply_shape_labeller(),
        scheduled_post_store=scheduled_post_store,
        intents=intents,
    )


# STABLE_NOW expressed as the aware UTC instant Discord would stamp a message
# with, so replies in tests look prompt and need no delay explanation.
STABLE_NOW_UTC = datetime(2026, 6, 24, 13, 0, tzinfo=timezone.utc)


def make_message(
    author: MagicMock,
    mentions: list | None = None,
    reference: MagicMock | None = None,
    channel: MagicMock | None = None,
    created_at: datetime | None = None,
) -> MagicMock:
    msg = MagicMock(spec=discord.Message)
    msg.author = author
    msg.mentions = mentions or []
    msg.reference = reference
    msg.created_at = created_at or STABLE_NOW_UTC
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


def make_guild(joined_at: datetime | None) -> MagicMock:
    guild = MagicMock(spec=discord.Guild)
    guild.me = MagicMock(spec=discord.Member)
    guild.me.joined_at = joined_at
    return guild


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


@patch("livingbot.bot.clock")
@patch("asyncio.create_task", side_effect=lambda coro: coro.close())
@patch("random.random", return_value=0.99)
@patch.object(LivingBot, "user", new_callable=PropertyMock)
async def test_on_message_when_random_disfavors_immediate_does_not_send(
    mock_user: PropertyMock,
    mock_random: MagicMock,
    mock_create_task: MagicMock,
    mock_clock: MagicMock,
) -> None:
    mock_clock.now.return_value = STABLE_NOW
    user = bot_user()
    mock_user.return_value = user
    bot = make_bot(mood_store=make_mood_store(Mood(value=50.0, fatigue=8.0)))
    channel = make_channel()

    await bot.on_message(
        make_message(author=other_user(), mentions=[user], channel=channel)
    )

    channel.send.assert_not_called()


@patch("livingbot.bot.clock")
@patch("asyncio.create_task", side_effect=lambda coro: coro.close())
@patch("random.random", return_value=0.99)
@patch.object(LivingBot, "user", new_callable=PropertyMock)
async def test_on_message_when_random_disfavors_immediate_sets_resting(
    mock_user: PropertyMock,
    mock_random: MagicMock,
    mock_create_task: MagicMock,
    mock_clock: MagicMock,
) -> None:
    mock_clock.now.return_value = STABLE_NOW
    user = bot_user()
    mock_user.return_value = user
    bot = make_bot(mood_store=make_mood_store(Mood(value=50.0, fatigue=8.0)))

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
    channel = make_channel()
    bot._queue.add(make_message(author=other_user(), mentions=[user], channel=channel))

    await bot._rest_and_respond()

    channel.send.assert_called_once_with("llm response")
    assert bot._resting is False


@patch("livingbot.bot.clock")
@patch("asyncio.sleep", new_callable=AsyncMock)
@patch("random.random", side_effect=[0.99, 0.0])
@patch("random.uniform", return_value=5.0)
@patch.object(LivingBot, "user", new_callable=PropertyMock)
async def test_rest_and_respond_loops_until_random_favors_response(
    mock_user: PropertyMock,
    mock_uniform: MagicMock,
    mock_random: MagicMock,
    mock_sleep: AsyncMock,
    mock_clock: MagicMock,
) -> None:
    mock_clock.now.return_value = STABLE_NOW
    user = bot_user()
    mock_user.return_value = user
    bot = make_bot(mood_store=make_mood_store(Mood(value=50.0, fatigue=3.0)))
    bot._resting = True
    channel = make_channel()
    bot._queue.add(make_message(author=other_user(), mentions=[user], channel=channel))

    await bot._rest_and_respond()

    # mood_factor=1.0, fatigue=3.0 → threshold 1/4: roll 0.99 loops, roll 0.0 responds
    channel.send.assert_called_once_with("llm response")
    assert bot._resting is False


@patch("livingbot.bot.clock")
@patch("asyncio.sleep", new_callable=AsyncMock)
@patch("random.uniform", return_value=5.0)
@patch.object(
    LivingBot,
    "_attempt_response",
    new_callable=AsyncMock,
    side_effect=RuntimeError("the LLM fell over"),
)
async def test_rest_and_respond_when_attempt_raises_clears_resting(
    mock_attempt: AsyncMock,
    mock_uniform: MagicMock,
    mock_sleep: AsyncMock,
    mock_clock: MagicMock,
) -> None:
    """Nothing outside this task ever clears _resting, so leaving it set would
    silence her permanently rather than for one failed attempt."""
    mock_clock.now.return_value = STABLE_NOW
    bot = make_bot()
    bot._resting = True

    await bot._rest_and_respond()

    assert bot._resting is False


@patch.object(LivingBot, "guilds", new_callable=PropertyMock)
def test_onboarding_active_when_no_guilds_returns_false(
    mock_guilds: PropertyMock,
) -> None:
    mock_guilds.return_value = []
    bot = make_bot()

    result = bot._onboarding_active()

    assert result is False


@patch.object(LivingBot, "guilds", new_callable=PropertyMock)
def test_onboarding_active_when_joined_recently_returns_true(
    mock_guilds: PropertyMock,
) -> None:
    mock_guilds.return_value = [make_guild(discord.utils.utcnow() - timedelta(days=1))]
    bot = make_bot()

    result = bot._onboarding_active()

    assert result is True


@patch.object(LivingBot, "guilds", new_callable=PropertyMock)
def test_onboarding_active_when_joined_over_period_ago_returns_false(
    mock_guilds: PropertyMock,
) -> None:
    mock_guilds.return_value = [make_guild(discord.utils.utcnow() - timedelta(days=4))]
    bot = make_bot()

    result = bot._onboarding_active()

    assert result is False


@patch("livingbot.bot.clock")
@patch("random.random", return_value=0.6)
@patch.object(LivingBot, "guilds", new_callable=PropertyMock)
async def test_attempt_response_when_onboarding_active_responds_despite_high_fatigue(
    mock_guilds: PropertyMock,
    mock_random: MagicMock,
    mock_clock: MagicMock,
) -> None:
    mock_clock.now.return_value = STABLE_NOW
    mock_guilds.return_value = [make_guild(discord.utils.utcnow() - timedelta(days=1))]
    bot = make_bot(mood_store=make_mood_store(Mood(value=50.0, fatigue=8.0)))
    channel = make_channel()
    bot._queue.add(make_message(author=other_user(), channel=channel))

    # fatigue 8 → factor 0.36; mood_factor 1.0 boosted to 2.0 → odds 0.72; 0.6 < 0.72
    result = await bot._attempt_response()

    assert result is True
    channel.send.assert_called_once_with("llm response")


@patch("livingbot.bot.clock")
@patch("random.random", return_value=0.6)
@patch.object(LivingBot, "guilds", new_callable=PropertyMock)
async def test_attempt_response_when_not_onboarding_skips_response_with_same_roll(
    mock_guilds: PropertyMock,
    mock_random: MagicMock,
    mock_clock: MagicMock,
) -> None:
    mock_clock.now.return_value = STABLE_NOW
    mock_guilds.return_value = []
    bot = make_bot(mood_store=make_mood_store(Mood(value=50.0, fatigue=8.0)))
    channel = make_channel()
    bot._queue.add(make_message(author=other_user(), channel=channel))

    # fatigue 8 → factor 0.36; mood_factor 1.0, not boosted → odds 0.36; 0.6 < 0.36 False
    result = await bot._attempt_response()

    assert result is False
    channel.send.assert_not_called()


@patch("asyncio.sleep", new_callable=AsyncMock)
@patch("random.random", return_value=0.0)
@patch("random.uniform", return_value=1.0)
@patch.object(LivingBot, "guilds", new_callable=PropertyMock)
async def test_rest_and_respond_when_onboarding_active_shrinks_delay_range(
    mock_guilds: PropertyMock,
    mock_uniform: MagicMock,
    mock_random: MagicMock,
    mock_sleep: AsyncMock,
) -> None:
    mock_guilds.return_value = [make_guild(discord.utils.utcnow() - timedelta(days=1))]
    bot = make_bot(mood_store=make_mood_store(Mood(value=50.0, fatigue=3.0)))

    await bot._rest_and_respond()

    # mood_rest_factor=1.0, max_delay=15.0, divided by ONBOARDING_REST_DELAY_DIVISOR=4.0
    mock_uniform.assert_any_call(0.75, 3.75)


def test_format_message_shows_timestamp_in_warsaw_wall_clock() -> None:
    msg = MagicMock(spec=discord.Message)
    msg.id = 987654321
    msg.created_at = datetime(2024, 6, 1, 8, 0, tzinfo=timezone.utc)
    msg.author.display_name = "Alice"
    msg.clean_content = "hello world"

    result = format_message(msg)

    # 08:00 UTC is 10:00 in Warsaw during summer (UTC+2).
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
    msg1.clean_content = "first"
    msg2 = make_message(author=other_user(), mentions=[user], channel=channel)
    msg2.clean_content = "second"
    bot._queue.add(msg1)
    bot._queue.add(msg2)

    await bot._attempt_response()

    llm_client.complete.assert_called_once_with(
        [format_message(msg1), format_message(msg2)],
        channel,
        channel.id,
        bot._calendar_store,
        bot._activity_notes_store,
        bot._inventory_store,
        bot._spending_store,
        bot._hobby_store,
        bot._story_store,
        bot._preference_store,
        bot._commitment_store,
        ANY,
        [],
        [Relation(user_id="123"), Relation(user_id="123")],
        ANY,
        photo_hint=ANY,
        server_emojis=ANY,
        images=[],
        waiting_since=ANY,
        history=[],
        shared_ending=None,
        commitments=[],
        directory=ANY,
    )


@patch("random.random", return_value=0.0)
@patch.object(LivingBot, "user", new_callable=PropertyMock)
async def test_attempt_response_includes_recent_channel_history_oldest_first(
    mock_user: PropertyMock,
    mock_random: MagicMock,
) -> None:
    user = bot_user()
    mock_user.return_value = user
    llm_client = make_llm_client()
    bot = make_bot(llm_client)
    channel = make_channel()
    newer = make_message(author=other_user(), channel=channel)
    newer.content = "newer"
    older = make_message(author=other_user(), channel=channel)
    older.content = "older"

    async def fake_history(limit: int, before: discord.Object):
        for msg in [newer, older]:
            yield msg

    channel.history = MagicMock(side_effect=fake_history)
    queued = make_message(author=other_user(), mentions=[user], channel=channel)
    bot._queue.add(queued)

    await bot._attempt_response()

    channel.history.assert_called_once_with(
        limit=config.CHANNEL_HISTORY_LIMIT, before=discord.Object(id=queued.id)
    )
    call_kwargs = llm_client.complete.call_args.kwargs
    assert call_kwargs["history"] == [format_message(older), format_message(newer)]


def with_image(message: MagicMock, message_id: int, data: bytes) -> MagicMock:
    attachment = MagicMock(spec=discord.Attachment)
    attachment.content_type = "image/png"
    attachment.read = AsyncMock(return_value=data)
    message.id = message_id
    message.attachments = [attachment]
    message.embeds = []
    return message


@patch("random.random", return_value=0.0)
@patch.object(LivingBot, "user", new_callable=PropertyMock)
async def test_attempt_response_re_attaches_images_from_earlier_messages(
    mock_user: PropertyMock,
    mock_random: MagicMock,
) -> None:
    """A photo one message back — hers included — is only visible to the model if its
    bytes are sent again; without this she answers questions about it by inventing."""
    user = bot_user()
    mock_user.return_value = user
    llm_client = make_llm_client()
    bot = make_bot(llm_client)
    channel = make_channel()
    hers = with_image(make_message(author=user, channel=channel), 30, b"her-photo")

    async def fake_history(limit: int, before: discord.Object):
        yield hers

    channel.history = MagicMock(side_effect=fake_history)
    bot._queue.add(make_message(author=other_user(), mentions=[user], channel=channel))

    await bot._attempt_response()

    images = llm_client.complete.call_args.kwargs["images"]
    assert [(i.message_id, i.content.data) for i in images] == [(30, b"her-photo")]


@patch("random.random", return_value=0.0)
@patch.object(LivingBot, "user", new_callable=PropertyMock)
async def test_attempt_response_lists_history_images_before_the_new_ones(
    mock_user: PropertyMock,
    mock_random: MagicMock,
) -> None:
    """The prompt numbers the images in the order they were sent, so the ones from
    history have to come before the ones she is replying to."""
    user = bot_user()
    mock_user.return_value = user
    llm_client = make_llm_client()
    bot = make_bot(llm_client)
    channel = make_channel()
    earlier = with_image(make_message(author=user, channel=channel), 30, b"earlier")

    async def fake_history(limit: int, before: discord.Object):
        yield earlier

    channel.history = MagicMock(side_effect=fake_history)
    queued = make_message(author=other_user(), mentions=[user], channel=channel)
    bot._queue.add(with_image(queued, 40, b"just-sent"))

    await bot._attempt_response()

    images = llm_client.complete.call_args.kwargs["images"]
    assert [i.content.data for i in images] == [b"earlier", b"just-sent"]


@patch("random.random", return_value=0.0)
@patch.object(LivingBot, "user", new_callable=PropertyMock)
async def test_attempt_response_marks_her_own_history_messages_as_hers(
    mock_user: PropertyMock,
    mock_random: MagicMock,
) -> None:
    user = bot_user()
    mock_user.return_value = user
    llm_client = make_llm_client()
    bot = make_bot(llm_client)
    channel = make_channel()
    hers = make_message(author=user, channel=channel)
    hers.content = "moje"

    async def fake_history(limit: int, before: discord.Object):
        yield hers

    channel.history = MagicMock(side_effect=fake_history)
    queued = make_message(author=other_user(), mentions=[user], channel=channel)
    bot._queue.add(queued)

    await bot._attempt_response()

    call_kwargs = llm_client.complete.call_args.kwargs
    assert call_kwargs["history"] == [format_message(hers, own=True)]


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
        [(format_message(msg), str(author.id))]
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
        [
            (format_message(msg1), str(author_a.id)),
            (format_message(msg2), str(author_b.id)),
        ]
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

    assert llm_client.complete.call_args.args[12] == ["remember this"]


@patch("random.random", return_value=0.0)
@patch.object(LivingBot, "user", new_callable=PropertyMock)
async def test_attempt_response_stores_memories_for_the_single_author(
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

    assert memory_store.store.call_args.kwargs["user_ids"] == [str(author.id)]


@patch("random.random", return_value=0.0)
@patch.object(LivingBot, "user", new_callable=PropertyMock)
async def test_attempt_response_stores_memories_for_every_author(
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

    assert memory_store.store.call_args.kwargs["user_ids"] == [
        str(msg1.author.id),
        str(msg2.author.id),
    ]


@patch.object(LivingBot, "user", new_callable=PropertyMock)
async def test_is_reply_to_bot_when_no_reference_returns_false(
    mock_user: PropertyMock,
) -> None:
    user = bot_user()
    mock_user.return_value = user
    bot = make_bot()
    message = make_message(author=other_user(), reference=None)

    result = await bot._is_reply_to_bot(message)

    assert result is False


@patch.object(LivingBot, "user", new_callable=PropertyMock)
async def test_is_reply_to_bot_when_resolved_reference_is_bots_returns_true(
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

    result = await bot._is_reply_to_bot(message)

    assert result is True


async def test_send_chunked_when_response_fits_sends_single_message() -> None:
    channel = make_channel()

    await _send_chunked(channel, "short response", Directory({}))

    channel.send.assert_called_once_with("short response")


async def test_send_chunked_when_response_exceeds_limit_splits_into_chunks() -> None:
    channel = make_channel()
    text = "x" * 2500

    await _send_chunked(channel, text, Directory({}))

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
    update_a = RelationUpdate(attitude_delta=2, reason="asked about her training")
    update_b = RelationUpdate(attitude_delta=-3, reason="called her useless")

    relation_updater = make_relation_updater()
    relation_updater.update = AsyncMock(side_effect=[update_a, update_b])
    relation_store = make_relation_store()
    bot = make_bot(relation_store=relation_store, relation_updater=relation_updater)
    msg = make_message(author=other_user(), mentions=[user])

    await bot._update_relations([relation_a, relation_b], [msg], "bot reply")

    assert relation_updater.update.call_count == 2
    relation_store.save.assert_any_call(apply_update(relation_a, update_a))
    relation_store.save.assert_any_call(apply_update(relation_b, update_b))


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
    msg.clean_content = "hey bot"

    await bot._update_relations([relation], [msg], "my reply")

    conversation = relation_updater.update.call_args.args[1]
    roles = [turn["role"] for turn in conversation]
    contents = [turn["content"] for turn in conversation]
    assert roles[-1] == "assistant"
    assert contents[-1] == "my reply"


@patch("random.random", return_value=0.0)
@patch.object(LivingBot, "user", new_callable=PropertyMock)
async def test_update_relations_when_a_relation_fails_swallows_the_error(
    mock_user: PropertyMock,
    mock_random: MagicMock,
) -> None:
    """It runs as a detached task, so a raised error would surface only as a
    'Task exception was never retrieved' warning at garbage-collection time."""
    user = bot_user()
    mock_user.return_value = user
    relation_store = make_relation_store()
    relation_updater = make_relation_updater()
    relation_updater.update = AsyncMock(side_effect=RuntimeError("judge fell over"))
    bot = make_bot(relation_store=relation_store, relation_updater=relation_updater)
    msg = make_message(author=other_user(), mentions=[user])

    await bot._update_relations([Relation(user_id="aaa")], [msg], "bot reply")

    relation_store.save.assert_not_called()


@patch("livingbot.bot.clock")
async def test_ensure_week_planned_when_week_unplanned_plans_and_saves(
    mock_clock: MagicMock,
) -> None:
    mock_clock.now.return_value = datetime(2026, 6, 3, 14, 30)
    entry = PlanEntry(
        activity="gym",
        location="gym",
        start=datetime(2026, 6, 4, 18, 0),
        end=datetime(2026, 6, 4, 19, 30),
    )
    calendar_store = make_calendar_store(Calendar(home_location="home"))
    week_planner = make_week_planner([entry])
    hobby_store = make_hobby_store(Hobbies(entries=[Hobby(name="gym")]))
    bot = make_bot(
        calendar_store=calendar_store,
        week_planner=week_planner,
        hobby_store=hobby_store,
    )

    await bot._ensure_week_planned()

    week_start = datetime(2026, 6, 1).date()
    week_planner.plan.assert_called_once_with(
        week_start, hobby_store.load(), "home", mock_clock.now.return_value
    )
    saved = calendar_store.save.call_args.args[0]
    assert saved.entries == [entry]
    assert saved.planned_week_start == week_start


@patch("livingbot.bot.clock")
async def test_ensure_week_planned_passes_her_hobbies_to_planner(
    mock_clock: MagicMock,
) -> None:
    now = datetime(2026, 6, 3, 14, 30)
    mock_clock.now.return_value = now
    calendar_store = make_calendar_store(Calendar(home_location="home"))
    week_planner = make_week_planner()
    hobbies = Hobbies(
        entries=[
            Hobby(name="gym"),
            Hobby(name="pottery", acquired_at=now - timedelta(days=2)),
        ]
    )
    bot = make_bot(
        calendar_store=calendar_store,
        week_planner=week_planner,
        hobby_store=make_hobby_store(hobbies),
    )

    await bot._ensure_week_planned()

    week_planner.plan.assert_called_once_with(
        datetime(2026, 6, 1).date(), hobbies, "home", now
    )


@patch("livingbot.bot.clock")
async def test_ensure_week_planned_when_week_already_planned_does_not_replan(
    mock_clock: MagicMock,
) -> None:
    mock_clock.now.return_value = datetime(2026, 6, 3, 14, 30)
    calendar = Calendar(
        home_location="home", planned_week_start=datetime(2026, 6, 1).date()
    )
    week_planner = make_week_planner()
    bot = make_bot(
        calendar_store=make_calendar_store(calendar), week_planner=week_planner
    )

    await bot._ensure_week_planned()

    week_planner.plan.assert_not_called()


@patch("livingbot.bot.clock")
async def test_ensure_week_planned_prunes_finished_entries(
    mock_clock: MagicMock,
) -> None:
    mock_clock.now.return_value = datetime(2026, 6, 3, 14, 30)
    old = PlanEntry(
        activity="gym",
        location="gym",
        start=datetime(2026, 5, 1, 18, 0),
        end=datetime(2026, 5, 1, 19, 30),
    )
    calendar = Calendar(
        home_location="home",
        planned_week_start=datetime(2026, 6, 1).date(),
        entries=[old],
    )
    calendar_store = make_calendar_store(calendar)
    bot = make_bot(calendar_store=calendar_store)

    await bot._ensure_week_planned()

    saved = calendar_store.save.call_args.args[0]
    assert saved.entries == []


# ---------------------------------------------------------------------------
# _send_chunked with photo
# ---------------------------------------------------------------------------


async def test_send_chunked_without_photo_sends_text_only() -> None:
    channel = make_channel()

    await _send_chunked(channel, "hello", Directory({}))

    channel.send.assert_called_once_with("hello")


async def test_send_chunked_with_photo_attaches_file_to_last_chunk() -> None:
    channel = make_channel()

    await _send_chunked(channel, "here you go", Directory({}), photo=b"\xff\xd8\xff")

    call_kwargs = channel.send.call_args.kwargs
    assert "file" in call_kwargs
    assert isinstance(call_kwargs["file"], discord.File)


async def test_send_chunked_with_photo_sends_text_in_same_call() -> None:
    channel = make_channel()

    await _send_chunked(channel, "check this out", Directory({}), photo=b"\xff\xd8\xff")

    text_sent = channel.send.call_args.args[0]
    assert text_sent == "check this out"


async def test_send_chunked_with_long_text_only_attaches_photo_to_last_chunk() -> None:
    channel = make_channel()
    long_text = "x" * 4500  # exceeds DISCORD_MAX_LENGTH, produces 3 chunks

    await _send_chunked(channel, long_text, Directory({}), photo=b"\xff\xd8\xff")

    assert channel.send.call_count == 3
    # first two chunks must not have a file kwarg
    for call in channel.send.call_args_list[:-1]:
        assert "file" not in call.kwargs
    # last chunk must carry the file
    assert "file" in channel.send.call_args_list[-1].kwargs


# ---------------------------------------------------------------------------
# custom emoji cadence: _server_emojis_for_message
# ---------------------------------------------------------------------------


def make_guild_channel(emojis: list[str]) -> MagicMock:
    channel = make_channel()
    channel.guild = MagicMock(spec=discord.Guild)
    channel.guild.emojis = emojis
    return channel


def test_server_emojis_for_message_on_her_first_message_lists_the_guild_emojis() -> (
    None
):
    bot = make_bot()
    channel = make_guild_channel(["<:mugda_lift:111>"])

    assert bot._server_emojis_for_message(channel) == ["<:mugda_lift:111>"]


def test_server_emojis_for_message_within_the_interval_lists_nothing() -> None:
    bot = make_bot()
    channel = make_guild_channel(["<:mugda_lift:111>"])
    bot._server_emojis_for_message(channel)

    assert bot._server_emojis_for_message(channel) == []


def test_server_emojis_for_message_lists_them_again_once_the_interval_passes() -> None:
    bot = make_bot()
    channel = make_guild_channel(["<:mugda_lift:111>"])
    for _ in range(config.SERVER_EMOJI_REMINDER_INTERVAL):
        bot._server_emojis_for_message(channel)

    assert bot._server_emojis_for_message(channel) == ["<:mugda_lift:111>"]


def test_server_emojis_for_message_outside_a_guild_lists_nothing() -> None:
    bot = make_bot()
    channel = MagicMock(spec=discord.abc.Messageable)

    assert bot._server_emojis_for_message(channel) == []


@patch("random.random", return_value=0.0)
@patch.object(LivingBot, "user", new_callable=PropertyMock)
async def test_attempt_response_passes_the_server_custom_emojis_to_the_llm(
    mock_user: PropertyMock,
    mock_random: MagicMock,
) -> None:
    user = bot_user()
    mock_user.return_value = user
    llm_client = make_llm_client()
    bot = make_bot(llm_client)
    channel = make_guild_channel(["<:mugda_lift:111>"])
    bot._queue.add(make_message(author=other_user(), mentions=[user], channel=channel))

    await bot._attempt_response()

    call_kwargs = llm_client.complete.call_args.kwargs
    assert call_kwargs["server_emojis"] == ["<:mugda_lift:111>"]


# ---------------------------------------------------------------------------
# photo cadence: _photo_hint_for_message and _on_photo_taken
# ---------------------------------------------------------------------------


def test_photo_hint_for_message_when_below_cooldown_returns_empty() -> None:
    store = make_photo_cooldown_store(
        PhotoCooldown(messages_since_photo=0, cooldown=50)
    )
    bot = make_bot(photo_cooldown_store=store)

    assert bot._photo_hint_for_message() == ""


def test_photo_hint_for_message_when_at_cooldown_returns_hint() -> None:
    store = make_photo_cooldown_store(
        PhotoCooldown(messages_since_photo=50, cooldown=50)
    )
    bot = make_bot(photo_cooldown_store=store)

    assert bot._photo_hint_for_message() != ""


def test_photo_hint_for_message_when_above_cooldown_returns_hint() -> None:
    store = make_photo_cooldown_store(
        PhotoCooldown(messages_since_photo=99, cooldown=50)
    )
    bot = make_bot(photo_cooldown_store=store)

    assert bot._photo_hint_for_message() != ""


def test_on_photo_taken_resets_message_counter_to_zero() -> None:
    store = make_photo_cooldown_store(
        PhotoCooldown(messages_since_photo=55, cooldown=50)
    )
    bot = make_bot(photo_cooldown_store=store)

    bot._on_photo_taken()

    saved = store.save.call_args.args[0]
    assert saved.messages_since_photo == 0


@patch("random.randint", return_value=45)
def test_on_photo_taken_sets_new_cooldown(mock_randint: MagicMock) -> None:
    store = make_photo_cooldown_store(
        PhotoCooldown(messages_since_photo=0, cooldown=99)
    )
    bot = make_bot(photo_cooldown_store=store)

    bot._on_photo_taken()

    saved = store.save.call_args.args[0]
    assert saved.cooldown == 45


# ---------------------------------------------------------------------------
# _attempt_response photo attachment integration
# ---------------------------------------------------------------------------


@patch("asyncio.create_task", side_effect=lambda coro: coro.close())
@patch("random.random", return_value=0.0)
@patch.object(LivingBot, "user", new_callable=PropertyMock)
async def test_attempt_response_when_photo_returned_attaches_it_to_message(
    mock_user: PropertyMock,
    mock_random: MagicMock,
    mock_create_task: MagicMock,
) -> None:
    user = bot_user()
    mock_user.return_value = user
    llm_client = make_llm_client()
    llm_client.complete.return_value.photo = b"\xff\xd8\xff"
    bot = make_bot(llm_client=llm_client)
    channel = make_channel()
    bot._queue.add(make_message(author=other_user(), mentions=[user], channel=channel))

    await bot._attempt_response()

    last_call = channel.send.call_args
    assert "file" in last_call.kwargs
    assert isinstance(last_call.kwargs["file"], discord.File)


@patch("asyncio.create_task", side_effect=lambda coro: coro.close())
@patch("random.random", return_value=0.0)
@patch.object(LivingBot, "user", new_callable=PropertyMock)
async def test_attempt_response_when_photo_returned_resets_photo_counter(
    mock_user: PropertyMock,
    mock_random: MagicMock,
    mock_create_task: MagicMock,
) -> None:
    user = bot_user()
    mock_user.return_value = user
    llm_client = make_llm_client()
    llm_client.complete.return_value.photo = b"\xff\xd8\xff"
    store = make_photo_cooldown_store(
        PhotoCooldown(messages_since_photo=55, cooldown=50)
    )
    bot = make_bot(llm_client=llm_client, photo_cooldown_store=store)
    channel = make_channel()
    bot._queue.add(make_message(author=other_user(), mentions=[user], channel=channel))

    await bot._attempt_response()

    saved = store.save.call_args.args[0]
    assert saved.messages_since_photo == 0


@patch("asyncio.create_task", side_effect=lambda coro: coro.close())
@patch("random.random", return_value=0.0)
@patch.object(LivingBot, "user", new_callable=PropertyMock)
async def test_attempt_response_when_no_photo_does_not_reset_counter(
    mock_user: PropertyMock,
    mock_random: MagicMock,
    mock_create_task: MagicMock,
) -> None:
    user = bot_user()
    mock_user.return_value = user
    store = make_photo_cooldown_store(
        PhotoCooldown(messages_since_photo=10, cooldown=50)
    )
    bot = make_bot(photo_cooldown_store=store)
    channel = make_channel()
    bot._queue.add(make_message(author=other_user(), mentions=[user], channel=channel))

    await bot._attempt_response()

    store.save.assert_not_called()


@patch.object(LivingBot, "user", new_callable=PropertyMock)
async def test_on_message_increments_message_counter(mock_user: PropertyMock) -> None:
    user = bot_user()
    mock_user.return_value = user
    store = make_photo_cooldown_store(
        PhotoCooldown(messages_since_photo=5, cooldown=50)
    )
    bot = make_bot(photo_cooldown_store=store)
    bot._resting = True  # prevent attempt_response

    await bot.on_message(make_message(author=other_user(), mentions=[user]))

    saved = store.save.call_args.args[0]
    assert saved.messages_since_photo == 6


@patch("asyncio.create_task", side_effect=lambda coro: coro.close())
@patch("random.random", return_value=0.0)
@patch.object(LivingBot, "user", new_callable=PropertyMock)
async def test_attempt_response_passes_photo_hint_when_cooldown_reached(
    mock_user: PropertyMock,
    mock_random: MagicMock,
    mock_create_task: MagicMock,
) -> None:
    user = bot_user()
    mock_user.return_value = user
    llm_client = make_llm_client()
    store = make_photo_cooldown_store(
        PhotoCooldown(messages_since_photo=99, cooldown=50)
    )
    bot = make_bot(llm_client=llm_client, photo_cooldown_store=store)
    channel = make_channel()
    bot._queue.add(make_message(author=other_user(), mentions=[user], channel=channel))

    await bot._attempt_response()

    call_kwargs = llm_client.complete.call_args.kwargs
    assert call_kwargs["photo_hint"] != ""


@patch("asyncio.create_task", side_effect=lambda coro: coro.close())
@patch("random.random", return_value=0.0)
@patch.object(LivingBot, "user", new_callable=PropertyMock)
async def test_attempt_response_passes_empty_hint_when_below_cooldown(
    mock_user: PropertyMock,
    mock_random: MagicMock,
    mock_create_task: MagicMock,
) -> None:
    user = bot_user()
    mock_user.return_value = user
    llm_client = make_llm_client()
    store = make_photo_cooldown_store(
        PhotoCooldown(messages_since_photo=0, cooldown=50)
    )
    bot = make_bot(llm_client=llm_client, photo_cooldown_store=store)
    channel = make_channel()
    bot._queue.add(make_message(author=other_user(), mentions=[user], channel=channel))

    await bot._attempt_response()

    call_kwargs = llm_client.complete.call_args.kwargs
    assert call_kwargs["photo_hint"] == ""


# ---------------------------------------------------------------------------
# story slot selection
# ---------------------------------------------------------------------------


@patch("livingbot.bot.random")
def test_pick_story_slot_when_roll_favors_plan_anchors_to_entry(
    mock_random: MagicMock,
) -> None:
    entry = PlanEntry(
        activity="gym",
        location="gym",
        start=datetime(2026, 6, 4, 18, 0),
        end=datetime(2026, 6, 4, 19, 30),
    )
    calendar = Calendar(home_location="home", entries=[entry])
    mock_random.random.return_value = 0.0
    mock_random.choice.return_value = entry
    mock_random.uniform.return_value = 0.0

    occurs_at, anchor = _pick_story_slot(
        calendar, date(2026, 6, 1), datetime(2026, 6, 1, 0, 0)
    )

    assert anchor == "gym at gym"
    assert occurs_at == datetime(2026, 6, 4, 18, 0)


@patch("livingbot.bot.random")
def test_pick_story_slot_when_no_plans_returns_free_moment_without_anchor(
    mock_random: MagicMock,
) -> None:
    calendar = Calendar(home_location="home", entries=[])
    mock_random.uniform.return_value = 0.0
    mock_random.randint.return_value = 10

    occurs_at, anchor = _pick_story_slot(
        calendar, date(2026, 6, 1), datetime(2026, 6, 1, 0, 0)
    )

    assert anchor is None
    assert occurs_at.hour == 10


@patch("livingbot.bot.random")
def test_random_free_moment_skips_a_busy_slot(mock_random: MagicMock) -> None:
    busy = PlanEntry(
        activity="gym",
        location="gym",
        start=datetime(2026, 6, 1, 10, 0),
        end=datetime(2026, 6, 1, 11, 0),
    )
    calendar = Calendar(home_location="home", entries=[busy])
    mock_random.uniform.return_value = 0.0
    mock_random.randint.side_effect = [10, 30, 14, 0]

    moment = _random_free_moment(
        datetime(2026, 6, 1, 0, 0), datetime(2026, 6, 8, 0, 0), calendar
    )

    assert moment == datetime(2026, 6, 1, 14, 0)


# ---------------------------------------------------------------------------
# _generate_week_story and _render_story_image
# ---------------------------------------------------------------------------


@patch.object(
    LivingBot,
    "_render_story_image",
    new_callable=AsyncMock,
    return_value="data/story_images/abc.jpg",
)
async def test_generate_week_story_adds_story_with_rendered_image_path(
    mock_render: AsyncMock,
) -> None:
    generator = make_story_generator()
    generator.generate = AsyncMock(return_value=Story(summary="s", content="c"))
    story_store = make_story_store()
    bot = make_bot(story_generator=generator, story_store=story_store)

    await bot._generate_week_story(
        Calendar(home_location="home"), date(2026, 6, 1), datetime(2026, 6, 1)
    )

    story_store.add.assert_awaited_once()
    assert story_store.add.await_args.args[0].image_path == "data/story_images/abc.jpg"


async def test_generate_week_story_when_generation_returns_none_adds_nothing() -> None:
    generator = make_story_generator()
    story_store = make_story_store()
    bot = make_bot(story_generator=generator, story_store=story_store)

    await bot._generate_week_story(
        Calendar(home_location="home"), date(2026, 6, 1), datetime(2026, 6, 1)
    )

    story_store.add.assert_not_awaited()


async def test_generate_week_story_when_generator_raises_swallows_the_error() -> None:
    """It runs as a detached task, so a raised error would surface only as a
    'Task exception was never retrieved' warning at garbage-collection time."""
    generator = make_story_generator()
    generator.generate = AsyncMock(side_effect=RuntimeError("generator fell over"))
    story_store = make_story_store()
    bot = make_bot(story_generator=generator, story_store=story_store)

    await bot._generate_week_story(
        Calendar(home_location="home"), date(2026, 6, 1), datetime(2026, 6, 1)
    )

    story_store.add.assert_not_awaited()


async def test_generate_week_story_passes_her_hobbies_to_generator() -> None:
    generator = make_story_generator()
    hobbies = Hobbies(entries=[Hobby(name="gym"), Hobby(name="pottery")])
    bot = make_bot(
        story_generator=generator,
        story_store=make_story_store(),
        hobby_store=make_hobby_store(hobbies),
    )

    await bot._generate_week_story(
        Calendar(home_location="home"), date(2026, 6, 1), datetime(2026, 6, 1)
    )

    assert generator.generate.call_args.args[1] == hobbies


@patch(
    "livingbot.bot.generate_image", new_callable=AsyncMock, return_value=b"img-bytes"
)
async def test_render_story_image_writes_file_and_returns_path(
    mock_gen: AsyncMock, tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(config, "STORY_IMAGE_PATH", tmp_path / "imgs")
    bot = make_bot()
    story = Story(summary="s", content="c")

    path = await bot._render_story_image(story)

    assert Path(path).read_bytes() == b"img-bytes"
    assert path.endswith(f"{story.id}.jpg")


@patch("livingbot.bot.generate_image", new_callable=AsyncMock, return_value=b"img")
async def test_render_story_image_sends_story_content_to_image_service(
    mock_gen: AsyncMock, tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(config, "STORY_IMAGE_PATH", tmp_path / "imgs")
    bot = make_bot()

    await bot._render_story_image(Story(summary="s", content="A wild tale"))

    assert mock_gen.call_args.kwargs["description"] == "A wild tale"
    assert mock_gen.call_args.kwargs["include_mugda"] is True


@patch("livingbot.bot.generate_image", new_callable=AsyncMock, return_value=b"img")
async def test_render_story_image_passes_the_hobby_the_story_is_about(
    mock_gen: AsyncMock, tmp_path, monkeypatch
) -> None:
    """The picture has to be drawn at the level she has actually reached."""
    monkeypatch.setattr(config, "STORY_IMAGE_PATH", tmp_path / "imgs")
    painting = Hobby(name="painting", level=HobbyLevel.novice)
    bot = make_bot(hobby_store=make_hobby_store(Hobbies(entries=[painting])))

    await bot._render_story_image(
        Story(summary="s", content="Her first canvas", hobby="painting")
    )

    assert mock_gen.call_args.kwargs["hobby"] == painting


@patch("livingbot.bot.generate_image", new_callable=AsyncMock, return_value=b"img")
async def test_render_story_image_for_a_story_about_no_hobby_passes_none(
    mock_gen: AsyncMock, tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(config, "STORY_IMAGE_PATH", tmp_path / "imgs")
    bot = make_bot(hobby_store=make_hobby_store(Hobbies(entries=[Hobby(name="gym")])))

    await bot._render_story_image(Story(summary="s", content="A tram ride"))

    assert mock_gen.call_args.kwargs["hobby"] is None


@patch(
    "livingbot.bot.generate_image",
    new_callable=AsyncMock,
    side_effect=RuntimeError("endpoint down"),
)
async def test_render_story_image_returns_none_when_generation_fails(
    mock_gen: AsyncMock,
) -> None:
    bot = make_bot()

    result = await bot._render_story_image(Story(summary="s", content="c"))

    assert result is None


@patch("livingbot.bot.asyncio.create_task", side_effect=lambda coro: coro.close())
@patch("livingbot.bot.clock")
async def test_ensure_week_planned_schedules_story_generation_for_new_week(
    mock_clock: MagicMock, mock_create_task: MagicMock
) -> None:
    mock_clock.now.return_value = datetime(2026, 6, 3, 14, 30)
    bot = make_bot(
        calendar_store=make_calendar_store(Calendar(home_location="home")),
        week_planner=make_week_planner([]),
        hobby_store=make_hobby_store(Hobbies(entries=[Hobby(name="gym")])),
    )

    await bot._ensure_week_planned()

    mock_create_task.assert_called_once()


# ---------------------------------------------------------------------------
# proactive commitment follow-up
# ---------------------------------------------------------------------------

AWAKE_NOW = datetime(2026, 6, 24, 15, 0)
ASLEEP_NOW = datetime(2026, 6, 24, 3, 0)


def make_messageable_channel(history: list[MagicMock] | None = None) -> MagicMock:
    """A channel that passes bot.py's isinstance(..., Messageable) guard."""
    channel = MagicMock(spec=discord.TextChannel)
    channel.send = AsyncMock()

    async def fake_history(limit: int):
        for message in history or []:
            yield message

    channel.history = MagicMock(side_effect=fake_history)
    return channel


def make_commitment(
    status: str = "open",
    nudged_at: datetime | None = None,
    check_after: datetime | None = None,
    made_at: datetime = datetime(2026, 6, 24, 12, 0),
) -> Commitment:
    return Commitment(
        user_id="42",
        channel_id=777,
        description="show a screenshot of my BG3 character",
        due_hint="next time I'm at my computer",
        made_at=made_at,
        status=status,
        nudged_at=nudged_at,
        check_after=check_after,
    )


def make_timing_decision(
    should_follow_up: bool = True,
    retry_in_hours: float | None = None,
) -> CommitmentTimingDecision:
    return CommitmentTimingDecision(
        should_follow_up=should_follow_up,
        reason="conditions met",
        retry_in_hours=retry_in_hours,
    )


@patch("livingbot.bot.clock")
async def test_maybe_follow_up_when_asleep_does_not_consult_the_timing_judge(
    mock_clock: MagicMock,
) -> None:
    mock_clock.now.return_value = ASLEEP_NOW
    judge = make_commitment_timing_judge()
    bot = make_bot(
        commitment_store=make_commitment_store(
            Commitments(entries=[make_commitment()])
        ),
        commitment_timing_judge=judge,
    )

    await bot._maybe_follow_up_on_commitments()

    judge.decide.assert_not_called()


@patch("livingbot.bot.clock")
async def test_maybe_follow_up_skips_already_nudged_commitment(
    mock_clock: MagicMock,
) -> None:
    mock_clock.now.return_value = AWAKE_NOW
    judge = make_commitment_timing_judge()
    bot = make_bot(
        commitment_store=make_commitment_store(
            Commitments(
                entries=[make_commitment(nudged_at=datetime(2026, 6, 24, 13, 0))]
            )
        ),
        commitment_timing_judge=judge,
    )

    await bot._maybe_follow_up_on_commitments()

    judge.decide.assert_not_called()


@patch("livingbot.bot.clock")
async def test_maybe_follow_up_skips_fulfilled_commitment(
    mock_clock: MagicMock,
) -> None:
    mock_clock.now.return_value = AWAKE_NOW
    judge = make_commitment_timing_judge()
    bot = make_bot(
        commitment_store=make_commitment_store(
            Commitments(entries=[make_commitment(status="fulfilled")])
        ),
        commitment_timing_judge=judge,
    )

    await bot._maybe_follow_up_on_commitments()

    judge.decide.assert_not_called()


@patch.object(LivingBot, "get_channel")
@patch("livingbot.bot.clock")
async def test_maybe_follow_up_when_judge_declines_sends_nothing(
    mock_clock: MagicMock, mock_get_channel: MagicMock
) -> None:
    mock_clock.now.return_value = AWAKE_NOW
    channel = make_messageable_channel()
    mock_get_channel.return_value = channel
    judge = make_commitment_timing_judge()
    judge.decide = AsyncMock(return_value=make_timing_decision(should_follow_up=False))
    bot = make_bot(
        commitment_store=make_commitment_store(
            Commitments(entries=[make_commitment()])
        ),
        commitment_timing_judge=judge,
    )

    await bot._maybe_follow_up_on_commitments()

    channel.send.assert_not_called()


@patch.object(LivingBot, "get_channel")
@patch("livingbot.bot.clock")
async def test_maybe_follow_up_when_judge_declines_does_not_mark_nudged(
    mock_clock: MagicMock, mock_get_channel: MagicMock
) -> None:
    mock_clock.now.return_value = AWAKE_NOW
    mock_get_channel.return_value = make_messageable_channel()
    judge = make_commitment_timing_judge()
    judge.decide = AsyncMock(return_value=make_timing_decision(should_follow_up=False))
    store = make_commitment_store(Commitments(entries=[make_commitment()]))
    bot = make_bot(commitment_store=store, commitment_timing_judge=judge)

    await bot._maybe_follow_up_on_commitments()

    saved = store.save.call_args.args[0]
    assert saved.entries[0].nudged_at is None


@patch.object(LivingBot, "get_channel")
@patch("livingbot.bot.clock")
async def test_maybe_follow_up_when_judge_declines_defers_by_its_estimate(
    mock_clock: MagicMock, mock_get_channel: MagicMock
) -> None:
    mock_clock.now.return_value = AWAKE_NOW
    mock_get_channel.return_value = make_messageable_channel()
    judge = make_commitment_timing_judge()
    judge.decide = AsyncMock(
        return_value=make_timing_decision(should_follow_up=False, retry_in_hours=4.0)
    )
    store = make_commitment_store(Commitments(entries=[make_commitment()]))
    bot = make_bot(commitment_store=store, commitment_timing_judge=judge)

    await bot._maybe_follow_up_on_commitments()

    saved = store.save.call_args.args[0]
    assert saved.entries[0].check_after == AWAKE_NOW + timedelta(hours=4)


@patch.object(LivingBot, "get_channel")
@patch("livingbot.bot.clock")
async def test_maybe_follow_up_when_judge_gives_no_estimate_defers_by_default(
    mock_clock: MagicMock, mock_get_channel: MagicMock
) -> None:
    mock_clock.now.return_value = AWAKE_NOW
    mock_get_channel.return_value = make_messageable_channel()
    judge = make_commitment_timing_judge()
    judge.decide = AsyncMock(return_value=make_timing_decision(should_follow_up=False))
    store = make_commitment_store(Commitments(entries=[make_commitment()]))
    bot = make_bot(commitment_store=store, commitment_timing_judge=judge)

    await bot._maybe_follow_up_on_commitments()

    saved = store.save.call_args.args[0]
    assert saved.entries[0].check_after == AWAKE_NOW + timedelta(
        hours=config.COMMITMENT_DEFAULT_RETRY_HOURS
    )


@patch.object(LivingBot, "get_channel")
@patch("livingbot.bot.clock")
async def test_maybe_follow_up_skips_commitment_still_inside_its_wait(
    mock_clock: MagicMock, mock_get_channel: MagicMock
) -> None:
    mock_clock.now.return_value = AWAKE_NOW
    mock_get_channel.return_value = make_messageable_channel()
    judge = make_commitment_timing_judge()
    bot = make_bot(
        commitment_store=make_commitment_store(
            Commitments(
                entries=[make_commitment(check_after=AWAKE_NOW + timedelta(hours=2))]
            )
        ),
        commitment_timing_judge=judge,
    )

    await bot._maybe_follow_up_on_commitments()

    judge.decide.assert_not_called()


@patch.object(LivingBot, "get_channel")
@patch("livingbot.bot.clock")
async def test_maybe_follow_up_consults_timing_judge_once_the_wait_has_passed(
    mock_clock: MagicMock, mock_get_channel: MagicMock
) -> None:
    mock_clock.now.return_value = AWAKE_NOW
    mock_get_channel.return_value = make_messageable_channel()
    judge = make_commitment_timing_judge()
    judge.decide = AsyncMock(return_value=make_timing_decision())
    bot = make_bot(
        commitment_store=make_commitment_store(
            Commitments(
                entries=[make_commitment(check_after=AWAKE_NOW - timedelta(minutes=1))]
            )
        ),
        commitment_timing_judge=judge,
    )

    await bot._maybe_follow_up_on_commitments()

    judge.decide.assert_called_once()


@patch.object(LivingBot, "get_channel")
@patch("livingbot.bot.clock")
async def test_maybe_follow_up_sends_at_most_one_message_per_waking(
    mock_clock: MagicMock, mock_get_channel: MagicMock
) -> None:
    mock_clock.now.return_value = AWAKE_NOW
    channel = make_messageable_channel()
    mock_get_channel.return_value = channel
    judge = make_commitment_timing_judge()
    judge.decide = AsyncMock(return_value=make_timing_decision())
    llm_client = make_llm_client("hej, mam ten screen")
    bot = make_bot(
        commitment_store=make_commitment_store(
            Commitments(entries=[make_commitment(), make_commitment()])
        ),
        commitment_timing_judge=judge,
        llm_client=llm_client,
    )

    await bot._maybe_follow_up_on_commitments()

    channel.send.assert_called_once_with("hej, mam ten screen")


@patch.object(LivingBot, "get_channel")
@patch("livingbot.bot.clock")
async def test_maybe_follow_up_re_attaches_images_from_channel_history(
    mock_clock: MagicMock, mock_get_channel: MagicMock
) -> None:
    """Promises are often about a picture someone already posted, so she has to be
    able to see it when she comes back to the promise."""
    mock_clock.now.return_value = AWAKE_NOW
    photo = with_image(MagicMock(spec=discord.Message), 30, b"the-screenshot")
    photo.author = other_user()
    mock_get_channel.return_value = make_messageable_channel([photo])
    judge = make_commitment_timing_judge()
    judge.decide = AsyncMock(return_value=make_timing_decision())
    llm_client = make_llm_client()
    bot = make_bot(
        commitment_store=make_commitment_store(
            Commitments(entries=[make_commitment()])
        ),
        commitment_timing_judge=judge,
        llm_client=llm_client,
    )

    await bot._maybe_follow_up_on_commitments()

    images = llm_client.complete.call_args.kwargs["images"]
    assert [(i.message_id, i.content.data) for i in images] == [(30, b"the-screenshot")]


@patch.object(LivingBot, "get_channel")
@patch("livingbot.bot.clock")
async def test_maybe_follow_up_when_judge_declines_does_not_download_images(
    mock_clock: MagicMock, mock_get_channel: MagicMock
) -> None:
    """Most check-ins end in "not yet", and downloading the channel's pictures for
    every one of those would cost far more than the follow-ups themselves."""
    mock_clock.now.return_value = AWAKE_NOW
    photo = with_image(MagicMock(spec=discord.Message), 30, b"the-screenshot")
    photo.author = other_user()
    mock_get_channel.return_value = make_messageable_channel([photo])
    judge = make_commitment_timing_judge()
    judge.decide = AsyncMock(return_value=make_timing_decision(should_follow_up=False))
    bot = make_bot(
        commitment_store=make_commitment_store(
            Commitments(entries=[make_commitment()])
        ),
        commitment_timing_judge=judge,
    )

    await bot._maybe_follow_up_on_commitments()

    photo.attachments[0].read.assert_not_awaited()


async def test_life_loop_sleeps_a_jittered_interval_rather_than_a_fixed_hour() -> None:
    bot = make_bot()
    slept: list[float] = []

    async def capture_and_stop(delay: float) -> None:
        slept.append(delay)
        raise asyncio.CancelledError

    with patch("livingbot.bot.asyncio.sleep", side_effect=capture_and_stop):
        with contextlib.suppress(asyncio.CancelledError):
            await bot._life_loop()

    assert (
        config.LIFE_LOOP_INTERVAL_MIN_SECONDS
        <= slept[0]
        <= config.LIFE_LOOP_INTERVAL_MAX_SECONDS
    )


@patch("livingbot.bot.clock")
async def test_retire_stale_commitments_drops_a_promise_past_its_shelf_life(
    mock_clock: MagicMock,
) -> None:
    mock_clock.now.return_value = AWAKE_NOW
    stale = make_commitment(
        made_at=AWAKE_NOW - config.COMMITMENT_RETIREMENT_PERIOD - timedelta(days=1)
    )
    store = make_commitment_store(Commitments(entries=[stale]))
    bot = make_bot(commitment_store=store)

    await bot._retire_stale_commitments(AWAKE_NOW)

    saved = store.save.call_args.args[0]
    assert saved.entries[0].status == "dropped"


@patch("livingbot.bot.clock")
async def test_retire_stale_commitments_keeps_a_recent_promise(
    mock_clock: MagicMock,
) -> None:
    mock_clock.now.return_value = AWAKE_NOW
    store = make_commitment_store(Commitments(entries=[make_commitment()]))
    bot = make_bot(commitment_store=store)

    await bot._retire_stale_commitments(AWAKE_NOW)

    store.save.assert_not_called()


# ---------------------------------------------------------------------------
# admin-scheduled topic posts: _maybe_post_scheduled
# ---------------------------------------------------------------------------


def make_scheduled_post(
    topic: str = "her new gym shoes",
    run_at: datetime = AWAKE_NOW,
    mention_user_id: str | None = None,
) -> ScheduledPost:
    return ScheduledPost(topic=topic, run_at=run_at, mention_user_id=mention_user_id)


@patch.object(LivingBot, "get_channel")
async def test_maybe_post_scheduled_when_store_is_none_does_not_look_up_a_channel(
    mock_get_channel: MagicMock, monkeypatch
) -> None:
    monkeypatch.setattr(config, "RANDOM_POST_CHANNEL_ID", 555)
    bot = make_bot()  # scheduled_post_store defaults to None

    await bot._maybe_post_scheduled()

    mock_get_channel.assert_not_called()


@patch.object(LivingBot, "get_channel")
async def test_maybe_post_scheduled_when_channel_not_configured_does_not_look_up_a_channel(
    mock_get_channel: MagicMock, monkeypatch
) -> None:
    monkeypatch.setattr(config, "RANDOM_POST_CHANNEL_ID", None)
    store = make_scheduled_post_store(
        ScheduledPosts(entries=[make_scheduled_post(run_at=AWAKE_NOW)])
    )
    bot = make_bot(scheduled_post_store=store)

    await bot._maybe_post_scheduled()

    mock_get_channel.assert_not_called()


@patch.object(LivingBot, "get_channel")
@patch("livingbot.bot.clock")
async def test_maybe_post_scheduled_when_none_due_does_not_send(
    mock_clock: MagicMock, mock_get_channel: MagicMock, monkeypatch
) -> None:
    monkeypatch.setattr(config, "RANDOM_POST_CHANNEL_ID", 555)
    mock_clock.now.return_value = AWAKE_NOW
    channel = make_messageable_channel()
    mock_get_channel.return_value = channel
    store = make_scheduled_post_store(
        ScheduledPosts(
            entries=[make_scheduled_post(run_at=AWAKE_NOW + timedelta(hours=1))]
        )
    )
    bot = make_bot(scheduled_post_store=store)

    await bot._maybe_post_scheduled()

    channel.send.assert_not_called()


@patch.object(LivingBot, "get_channel")
@patch("livingbot.bot.clock")
async def test_maybe_post_scheduled_when_due_sends_the_llm_response_to_the_channel(
    mock_clock: MagicMock, mock_get_channel: MagicMock, monkeypatch
) -> None:
    monkeypatch.setattr(config, "RANDOM_POST_CHANNEL_ID", 555)
    mock_clock.now.return_value = AWAKE_NOW
    channel = make_messageable_channel()
    mock_get_channel.return_value = channel
    llm_client = make_llm_client("o kurczę, dzisiaj było na siłce niesamowicie")
    store = make_scheduled_post_store(
        ScheduledPosts(
            entries=[make_scheduled_post(run_at=AWAKE_NOW - timedelta(minutes=1))]
        )
    )
    bot = make_bot(scheduled_post_store=store, llm_client=llm_client)

    await bot._maybe_post_scheduled()

    channel.send.assert_called_once_with("o kurczę, dzisiaj było na siłce niesamowicie")


@patch.object(LivingBot, "get_channel")
@patch("livingbot.bot.clock")
async def test_maybe_post_scheduled_marks_the_due_post_as_posted(
    mock_clock: MagicMock, mock_get_channel: MagicMock, monkeypatch
) -> None:
    monkeypatch.setattr(config, "RANDOM_POST_CHANNEL_ID", 555)
    mock_clock.now.return_value = AWAKE_NOW
    mock_get_channel.return_value = make_messageable_channel()
    store = make_scheduled_post_store(
        ScheduledPosts(
            entries=[make_scheduled_post(run_at=AWAKE_NOW - timedelta(minutes=1))]
        )
    )
    bot = make_bot(scheduled_post_store=store)

    await bot._maybe_post_scheduled()

    saved = store.save.call_args.args[0]
    assert saved.entries[0].status == "posted"
    assert saved.entries[0].posted_at == AWAKE_NOW


@patch.object(LivingBot, "get_channel")
@patch("livingbot.bot.clock")
async def test_maybe_post_scheduled_passes_a_trigger_built_from_the_topic(
    mock_clock: MagicMock, mock_get_channel: MagicMock, monkeypatch
) -> None:
    monkeypatch.setattr(config, "RANDOM_POST_CHANNEL_ID", 555)
    mock_clock.now.return_value = AWAKE_NOW
    mock_get_channel.return_value = make_messageable_channel()
    llm_client = make_llm_client()
    store = make_scheduled_post_store(
        ScheduledPosts(
            entries=[
                make_scheduled_post(
                    topic="jej nowe buty na siłkę",
                    run_at=AWAKE_NOW - timedelta(minutes=1),
                )
            ]
        )
    )
    bot = make_bot(scheduled_post_store=store, llm_client=llm_client)

    await bot._maybe_post_scheduled()

    call_kwargs = llm_client.complete.call_args.kwargs
    assert call_kwargs["trigger"] == prompts.build_scheduled_post_trigger(
        "jej nowe buty na siłkę"
    )


@patch.object(LivingBot, "get_channel")
@patch("livingbot.bot.clock")
async def test_maybe_post_scheduled_names_the_mentioned_user_in_the_trigger(
    mock_clock: MagicMock, mock_get_channel: MagicMock, monkeypatch
) -> None:
    monkeypatch.setattr(config, "RANDOM_POST_CHANNEL_ID", 555)
    mock_clock.now.return_value = AWAKE_NOW
    mock_get_channel.return_value = make_messageable_channel()
    llm_client = make_llm_client()
    store = make_scheduled_post_store(
        ScheduledPosts(
            entries=[
                make_scheduled_post(
                    run_at=AWAKE_NOW - timedelta(minutes=1), mention_user_id="42"
                ),
            ]
        )
    )
    bot = make_bot(scheduled_post_store=store, llm_client=llm_client)
    monkeypatch.setattr(LivingBot, "_directory", lambda self: Directory({"42": "Kuba"}))

    await bot._maybe_post_scheduled()

    call_kwargs = llm_client.complete.call_args.kwargs
    assert call_kwargs["trigger"] == prompts.build_scheduled_post_trigger(
        "her new gym shoes", "Kuba"
    )


@patch.object(LivingBot, "get_channel")
@patch("livingbot.bot.clock")
async def test_maybe_post_scheduled_posts_at_most_one_message_per_check(
    mock_clock: MagicMock, mock_get_channel: MagicMock, monkeypatch
) -> None:
    monkeypatch.setattr(config, "RANDOM_POST_CHANNEL_ID", 555)
    mock_clock.now.return_value = AWAKE_NOW
    channel = make_messageable_channel()
    mock_get_channel.return_value = channel
    store = make_scheduled_post_store(
        ScheduledPosts(
            entries=[
                make_scheduled_post(run_at=AWAKE_NOW - timedelta(hours=2)),
                make_scheduled_post(run_at=AWAKE_NOW - timedelta(hours=1)),
            ]
        )
    )
    bot = make_bot(scheduled_post_store=store)

    await bot._maybe_post_scheduled()

    channel.send.assert_called_once()


@patch.object(LivingBot, "get_channel", return_value=None)
@patch("livingbot.bot.clock")
async def test_maybe_post_scheduled_when_channel_unavailable_does_not_call_the_llm(
    mock_clock: MagicMock, mock_get_channel: MagicMock, monkeypatch
) -> None:
    monkeypatch.setattr(config, "RANDOM_POST_CHANNEL_ID", 555)
    mock_clock.now.return_value = AWAKE_NOW
    llm_client = make_llm_client()
    store = make_scheduled_post_store(
        ScheduledPosts(
            entries=[make_scheduled_post(run_at=AWAKE_NOW - timedelta(minutes=1))]
        )
    )
    bot = make_bot(scheduled_post_store=store, llm_client=llm_client)

    await bot._maybe_post_scheduled()

    llm_client.complete.assert_not_called()


@patch.object(LivingBot, "get_channel")
@patch("livingbot.bot.clock")
async def test_maybe_follow_up_does_not_consult_timing_judge_for_a_retired_promise(
    mock_clock: MagicMock, mock_get_channel: MagicMock
) -> None:
    mock_clock.now.return_value = AWAKE_NOW
    mock_get_channel.return_value = make_messageable_channel()
    judge = make_commitment_timing_judge()
    store = make_commitment_store(
        Commitments(
            entries=[
                make_commitment(
                    made_at=AWAKE_NOW
                    - config.COMMITMENT_RETIREMENT_PERIOD
                    - timedelta(days=1)
                )
            ]
        )
    )
    bot = make_bot(commitment_store=store, commitment_timing_judge=judge)

    await bot._maybe_follow_up_on_commitments()

    judge.decide.assert_not_called()


@patch.object(LivingBot, "get_channel")
@patch("livingbot.bot.clock")
async def test_maybe_follow_up_when_judge_agrees_sends_the_main_agents_message(
    mock_clock: MagicMock, mock_get_channel: MagicMock
) -> None:
    mock_clock.now.return_value = AWAKE_NOW
    channel = make_messageable_channel()
    mock_get_channel.return_value = channel
    judge = make_commitment_timing_judge()
    judge.decide = AsyncMock(return_value=make_timing_decision())
    llm_client = make_llm_client("hej, mam ten screen")
    bot = make_bot(
        commitment_store=make_commitment_store(
            Commitments(entries=[make_commitment()])
        ),
        commitment_timing_judge=judge,
        llm_client=llm_client,
    )

    await bot._maybe_follow_up_on_commitments()

    channel.send.assert_called_once_with("hej, mam ten screen")


@patch.object(LivingBot, "get_channel")
@patch("livingbot.bot.clock")
async def test_maybe_follow_up_when_judge_agrees_hands_off_to_the_main_agent(
    mock_clock: MagicMock, mock_get_channel: MagicMock
) -> None:
    mock_clock.now.return_value = AWAKE_NOW
    mock_get_channel.return_value = make_messageable_channel()
    judge = make_commitment_timing_judge()
    judge.decide = AsyncMock(return_value=make_timing_decision())
    commitment = make_commitment()
    llm_client = make_llm_client()
    bot = make_bot(
        commitment_store=make_commitment_store(Commitments(entries=[commitment])),
        commitment_timing_judge=judge,
        llm_client=llm_client,
    )

    await bot._maybe_follow_up_on_commitments()

    call_kwargs = llm_client.complete.call_args.kwargs
    assert call_kwargs["commitments"] == [commitment]
    assert call_kwargs["trigger"] == prompts.COMMITMENT_TRIGGER_MESSAGE


@patch.object(LivingBot, "get_channel")
@patch("livingbot.bot.clock")
async def test_maybe_follow_up_preserves_fulfilled_status_set_during_the_run(
    mock_clock: MagicMock, mock_get_channel: MagicMock
) -> None:
    """The main agent may call resolve_commitment itself while handling this; the
    bookkeeping afterwards must not clobber that back to open."""
    mock_clock.now.return_value = AWAKE_NOW
    mock_get_channel.return_value = make_messageable_channel()
    judge = make_commitment_timing_judge()
    judge.decide = AsyncMock(return_value=make_timing_decision())
    commitment = make_commitment()
    store = make_commitment_store(Commitments(entries=[commitment]))
    llm_client = make_llm_client()

    async def fake_complete(*args, **kwargs):
        commitment.status = "fulfilled"
        return llm_client.complete.return_value

    llm_client.complete = AsyncMock(side_effect=fake_complete)
    bot = make_bot(
        commitment_store=store, commitment_timing_judge=judge, llm_client=llm_client
    )

    await bot._maybe_follow_up_on_commitments()

    saved = store.save.call_args.args[0]
    assert saved.entries[0].status == "fulfilled"


@patch.object(LivingBot, "get_channel")
@patch("livingbot.bot.clock")
async def test_maybe_follow_up_after_sending_marks_commitment_nudged(
    mock_clock: MagicMock, mock_get_channel: MagicMock
) -> None:
    mock_clock.now.return_value = AWAKE_NOW
    mock_get_channel.return_value = make_messageable_channel()
    judge = make_commitment_timing_judge()
    judge.decide = AsyncMock(return_value=make_timing_decision())
    commitment = make_commitment()
    store = make_commitment_store(Commitments(entries=[commitment]))
    bot = make_bot(commitment_store=store, commitment_timing_judge=judge)

    await bot._maybe_follow_up_on_commitments()

    saved = store.save.call_args.args[0]
    assert saved.entries[0].nudged_at == AWAKE_NOW


@patch.object(LivingBot, "get_channel", return_value=None)
@patch("livingbot.bot.clock")
async def test_maybe_follow_up_when_channel_unavailable_does_not_consult_timing_judge(
    mock_clock: MagicMock, mock_get_channel: MagicMock
) -> None:
    mock_clock.now.return_value = AWAKE_NOW
    judge = make_commitment_timing_judge()
    bot = make_bot(
        commitment_store=make_commitment_store(
            Commitments(entries=[make_commitment()])
        ),
        commitment_timing_judge=judge,
    )

    await bot._maybe_follow_up_on_commitments()

    judge.decide.assert_not_called()


@patch("livingbot.bot.clock")
def test_build_commitment_timing_context_states_promise_and_timing_hint(
    mock_clock: MagicMock,
) -> None:
    bot = make_bot(mood_store=make_mood_store(Mood(value=60.0)))
    commitment = make_commitment()

    context = bot._build_commitment_timing_context(commitment, AWAKE_NOW, [])

    assert "show a screenshot of my BG3 character" in context
    assert "next time I'm at my computer" in context
    assert "User 42" in context


@patch("livingbot.bot.clock")
def test_build_commitment_timing_context_reports_being_free_at_home(
    mock_clock: MagicMock,
) -> None:
    bot = make_bot(
        calendar_store=make_calendar_store(Calendar(home_location="home")),
        mood_store=make_mood_store(Mood(value=60.0)),
    )

    context = bot._build_commitment_timing_context(make_commitment(), AWAKE_NOW, [])

    assert "You are at home with nothing scheduled." in context


@patch("livingbot.bot.clock")
def test_build_commitment_timing_context_reports_a_current_activity(
    mock_clock: MagicMock,
) -> None:
    ongoing = PlanEntry(
        activity="gym session",
        location="gym",
        start=datetime(2026, 6, 24, 14, 0),
        end=datetime(2026, 6, 24, 16, 0),
    )
    bot = make_bot(
        calendar_store=make_calendar_store(
            Calendar(home_location="home", entries=[ongoing])
        ),
        mood_store=make_mood_store(Mood(value=60.0)),
    )

    context = bot._build_commitment_timing_context(make_commitment(), AWAKE_NOW, [])

    assert "You are at gym, busy with gym session until 16:00." in context


@patch("livingbot.bot.clock")
def test_build_commitment_timing_context_includes_recent_channel_messages(
    mock_clock: MagicMock,
) -> None:
    bot = make_bot(mood_store=make_mood_store(Mood(value=60.0)))

    context = bot._build_commitment_timing_context(
        make_commitment(), AWAKE_NOW, ["[id:1] [2026-06-24 14:00:00] Hardik: no i jak?"]
    )

    assert "Hardik: no i jak?" in context


@patch("livingbot.bot.clock")
def test_build_commitment_timing_context_when_channel_silent_says_so(
    mock_clock: MagicMock,
) -> None:
    bot = make_bot(mood_store=make_mood_store(Mood(value=60.0)))

    context = bot._build_commitment_timing_context(make_commitment(), AWAKE_NOW, [])

    assert "Nothing has been said in that channel since she promised it" in context


async def test_send_chunked_turns_a_written_name_into_a_ping() -> None:
    channel = make_messageable_channel()

    await _send_chunked(channel, "hej @Kuba", Directory({"42": "Kuba"}))

    channel.send.assert_awaited_once_with("hej <@42>")
