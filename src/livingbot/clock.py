from datetime import datetime
from zoneinfo import ZoneInfo

LOCAL_TZ = ZoneInfo("Europe/Warsaw")


def now() -> datetime:
    # Mugda lives in Poland; the whole life layer reasons about her local wall
    # clock. We keep datetimes naive so they compare cleanly with the LLM's own
    # (naive) datetime outputs and with previously persisted data.
    return datetime.now(LOCAL_TZ).replace(tzinfo=None)


def to_local(moment: datetime) -> datetime:
    # Discord stamps messages in aware UTC; convert to Mugda's naive wall clock
    # so her sense of time matches the timestamps she sees.
    if moment.tzinfo is None:
        return moment
    return moment.astimezone(LOCAL_TZ).replace(tzinfo=None)
