from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field

from livingbot import config
from livingbot.relations import Relation


class IgnoreLog(BaseModel):
    last_ignored_at: dict[str, datetime] = Field(default_factory=dict)


class IgnoreStore:
    def __init__(self, data_path: Path) -> None:
        self._path = data_path / "ignores.json"
        data_path.mkdir(parents=True, exist_ok=True)

    def load(self) -> IgnoreLog:
        if not self._path.exists():
            return IgnoreLog()
        return IgnoreLog.model_validate_json(self._path.read_text())

    def save(self, log: IgnoreLog) -> None:
        self._path.write_text(log.model_dump_json(indent=2))


def may_ignore(relations: list[Relation], log: IgnoreLog, now: datetime) -> bool:
    """Whether staying silent is even on the table for this batch of messages.

    Both limits are deliberately outside the model's reach: it decides whether this
    particular message deserves silence, not whether silence is available at all.

    Silence falls on the whole batch, so everyone in it has to have earned it — one
    person she can't stand doesn't let her blank the friend who spoke next to them.
    """
    if not relations:
        return False
    if max(r.attitude for r in relations) > config.IGNORE_ATTITUDE_THRESHOLD:
        return False
    return all(_off_cooldown(log, r.user_id, now) for r in relations)


def _off_cooldown(log: IgnoreLog, user_id: str, now: datetime) -> bool:
    last_ignored_at = log.last_ignored_at.get(user_id)
    return last_ignored_at is None or now - last_ignored_at >= config.IGNORE_COOLDOWN


def record_ignore(log: IgnoreLog, user_ids: list[str], now: datetime) -> IgnoreLog:
    stamped = dict(log.last_ignored_at)
    for user_id in user_ids:
        stamped[user_id] = now
    return log.model_copy(update={"last_ignored_at": stamped})
