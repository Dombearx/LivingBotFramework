from datetime import datetime, timedelta

from livingbot import config
from livingbot.ignoring import IgnoreLog, IgnoreStore, may_ignore, record_ignore
from livingbot.relations import Relation

NOW = datetime(2026, 6, 3, 14, 30)
DISLIKED = config.IGNORE_ATTITUDE_THRESHOLD
BARELY_MINDED = config.IGNORE_ATTITUDE_THRESHOLD + 1


def test_may_ignore_when_she_only_mildly_minds_them_returns_false() -> None:
    relations = [Relation(user_id="1", attitude=BARELY_MINDED)]

    allowed = may_ignore(relations, IgnoreLog(), NOW)

    assert allowed is False


def test_may_ignore_when_she_dislikes_them_enough_returns_true() -> None:
    relations = [Relation(user_id="1", attitude=DISLIKED)]

    allowed = may_ignore(relations, IgnoreLog(), NOW)

    assert allowed is True


def test_may_ignore_when_only_one_of_them_provoked_her_returns_false() -> None:
    relations = [
        Relation(user_id="1", attitude=DISLIKED),
        Relation(user_id="2", attitude=60.0),
    ]

    allowed = may_ignore(relations, IgnoreLog(), NOW)

    assert allowed is False


def test_may_ignore_when_she_ignored_them_recently_returns_false() -> None:
    relations = [Relation(user_id="1", attitude=DISLIKED)]
    log = IgnoreLog(
        last_ignored_at={"1": NOW - config.IGNORE_COOLDOWN + timedelta(minutes=1)}
    )

    allowed = may_ignore(relations, log, NOW)

    assert allowed is False


def test_may_ignore_when_the_earlier_silence_is_off_cooldown_returns_true() -> None:
    relations = [Relation(user_id="1", attitude=DISLIKED)]
    log = IgnoreLog(last_ignored_at={"1": NOW - config.IGNORE_COOLDOWN})

    allowed = may_ignore(relations, log, NOW)

    assert allowed is True


def test_may_ignore_when_one_of_them_is_still_on_cooldown_returns_false() -> None:
    relations = [
        Relation(user_id="1", attitude=DISLIKED),
        Relation(user_id="2", attitude=DISLIKED),
    ]
    log = IgnoreLog(last_ignored_at={"2": NOW - timedelta(hours=1)})

    allowed = may_ignore(relations, log, NOW)

    assert allowed is False


def test_may_ignore_without_relations_returns_false() -> None:
    allowed = may_ignore([], IgnoreLog(), NOW)

    assert allowed is False


def test_record_ignore_stamps_every_author_in_the_batch() -> None:
    log = IgnoreLog()

    updated = record_ignore(log, ["1", "2"], NOW)

    assert updated.last_ignored_at == {"1": NOW, "2": NOW}


def test_record_ignore_leaves_the_original_log_untouched() -> None:
    log = IgnoreLog()

    record_ignore(log, ["1"], NOW)

    assert log.last_ignored_at == {}


def test_ignore_store_load_without_a_saved_file_returns_an_empty_log(tmp_path) -> None:
    store = IgnoreStore(tmp_path)

    log = store.load()

    assert log.last_ignored_at == {}


def test_ignore_store_load_returns_the_stamps_it_saved(tmp_path) -> None:
    store = IgnoreStore(tmp_path)
    store.save(IgnoreLog(last_ignored_at={"1": NOW}))

    log = store.load()

    assert log.last_ignored_at == {"1": NOW}
