from datetime import datetime, timedelta
from pathlib import Path

from livingbot.scheduled_posts import ScheduledPost, ScheduledPosts, ScheduledPostStore

NOW = datetime(2026, 6, 24, 15, 0)


def _post(status: str = "pending", run_at: datetime = NOW) -> ScheduledPost:
    return ScheduledPost(topic="her new gym shoes", run_at=run_at, status=status)


def test_due_includes_a_pending_post_whose_run_at_has_passed() -> None:
    post = _post(run_at=NOW - timedelta(minutes=1))
    posts = ScheduledPosts(entries=[post])

    result = posts.due(NOW)

    assert result == [post]


def test_due_includes_a_pending_post_whose_run_at_is_exactly_now() -> None:
    post = _post(run_at=NOW)
    posts = ScheduledPosts(entries=[post])

    result = posts.due(NOW)

    assert result == [post]


def test_due_excludes_a_pending_post_whose_run_at_is_in_the_future() -> None:
    posts = ScheduledPosts(entries=[_post(run_at=NOW + timedelta(minutes=1))])

    result = posts.due(NOW)

    assert result == []


def test_due_excludes_a_posted_post() -> None:
    posts = ScheduledPosts(
        entries=[_post(status="posted", run_at=NOW - timedelta(minutes=1))]
    )

    result = posts.due(NOW)

    assert result == []


def test_due_excludes_a_cancelled_post() -> None:
    posts = ScheduledPosts(
        entries=[_post(status="cancelled", run_at=NOW - timedelta(minutes=1))]
    )

    result = posts.due(NOW)

    assert result == []


def test_scheduled_post_id_defaults_to_a_generated_value() -> None:
    first = _post()
    second = _post()

    assert first.id != second.id


def test_scheduled_post_mention_user_id_defaults_to_none() -> None:
    post = _post()

    assert post.mention_user_id is None


def test_store_save_then_load_round_trips_scheduled_posts(tmp_path: Path) -> None:
    store = ScheduledPostStore(tmp_path)
    posts = ScheduledPosts(entries=[_post()])

    store.save(posts)
    loaded = store.load()

    assert loaded.entries[0].topic == "her new gym shoes"
    assert loaded.entries[0].run_at == NOW


def test_store_save_then_load_round_trips_the_mention_user_id(tmp_path: Path) -> None:
    store = ScheduledPostStore(tmp_path)
    post = _post()
    post.mention_user_id = "42"
    posts = ScheduledPosts(entries=[post])

    store.save(posts)
    loaded = store.load()

    assert loaded.entries[0].mention_user_id == "42"


def test_store_load_when_file_absent_returns_empty_scheduled_posts(
    tmp_path: Path,
) -> None:
    store = ScheduledPostStore(tmp_path)

    loaded = store.load()

    assert loaded.entries == []
