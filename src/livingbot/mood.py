import random
from datetime import date, datetime
from pathlib import Path

from pydantic import BaseModel, Field

from livingbot.calendar import Calendar

SLEEP_WINDOW_START = 7
SLEEP_WINDOW_END = 9
_DRIFT_PER_HOUR = 1.0


class Mood(BaseModel):
    value: float = Field(default=50.0, ge=0.0, le=100.0)
    last_sleep_date: date | None = None
    last_gym_boost_at: datetime | None = None
    last_refreshed_at: datetime | None = None


class MoodStore:
    def __init__(self, data_path: Path) -> None:
        self._path = data_path / "mood.json"
        data_path.mkdir(parents=True, exist_ok=True)

    def load(self) -> Mood:
        if not self._path.exists():
            return Mood()
        return Mood.model_validate_json(self._path.read_text())

    def save(self, mood: Mood) -> None:
        self._path.write_text(mood.model_dump_json(indent=2))


def refresh_mood(mood: Mood, now: datetime, calendar: Calendar) -> Mood:
    value = mood.value
    last_sleep_date = mood.last_sleep_date
    last_gym_boost_at = mood.last_gym_boost_at

    if mood.last_refreshed_at is not None:
        hours_elapsed = (now - mood.last_refreshed_at).total_seconds() / 3600.0
        drift = _DRIFT_PER_HOUR * hours_elapsed
        if value > 50.0:
            value = max(50.0, value - drift)
        elif value < 50.0:
            value = min(50.0, value + drift)

    if SLEEP_WINDOW_START <= now.hour < SLEEP_WINDOW_END:
        if last_sleep_date is None or last_sleep_date < now.date():
            value += random.uniform(15.0, 25.0)
            last_sleep_date = now.date()

    cutoff = last_gym_boost_at if last_gym_boost_at is not None else datetime.min
    gym_entries = [
        e
        for e in calendar.entries
        if "gym" in e.activity.lower() and cutoff < e.end <= now
    ]
    if gym_entries:
        latest = max(gym_entries, key=lambda e: e.end)
        value += random.uniform(10.0, 20.0)
        last_gym_boost_at = latest.end

    return Mood(
        value=max(0.0, min(100.0, value)),
        last_sleep_date=last_sleep_date,
        last_gym_boost_at=last_gym_boost_at,
        last_refreshed_at=now,
    )


def apply_interaction_delta(mood: Mood, attitude_delta: int) -> Mood:
    if attitude_delta == 0:
        return mood
    if attitude_delta > 0:
        boost = random.uniform(2.0, 8.0) * min(attitude_delta / 10.0, 1.0)
        new_value = min(100.0, mood.value + boost)
    else:
        drop = random.uniform(3.0, 10.0) * min(abs(attitude_delta) / 10.0, 1.0)
        new_value = max(0.0, mood.value - drop)
    return mood.model_copy(update={"value": new_value})


def _mood_label(value: float) -> str:
    if value < 20:
        return "really down"
    if value < 35:
        return "a bit low"
    if value < 45:
        return "meh, not feeling much"
    if value < 55:
        return "okay, pretty neutral"
    if value < 70:
        return "pretty good"
    if value < 85:
        return "great"
    return "on top of the world"


def build_mood_block(mood: Mood, now: datetime) -> str:
    label = _mood_label(mood.value)
    lines = [f"Your current mood: {label}."]
    if (
        mood.last_gym_boost_at is not None
        and (now - mood.last_gym_boost_at).total_seconds() < 4 * 3600
    ):
        lines.append("You just got back from the gym and feel pumped.")
    elif mood.last_sleep_date == now.date() and now.hour < 14:
        lines.append("You woke up feeling refreshed today.")
    lines.append(
        "Let this subtly colour your tone — don't announce your mood, just let it show naturally."
    )
    return "\n".join(lines) + "\n\n"
