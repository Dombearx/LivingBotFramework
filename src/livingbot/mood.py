import random
from datetime import date, datetime
from pathlib import Path

from pydantic import BaseModel, Field

from livingbot.calendar import Calendar

SLEEP_WINDOW_START = 7
SLEEP_WINDOW_END = 9
_DRIFT_PER_HOUR = 1.0
_FATIGUE_DECAY_PER_HOUR = 3.0
_FATIGUE_RELIEF_PER_ACTIVITY = 3.0
_FATIGUE_SLEEP_RETENTION = 0.1


class Mood(BaseModel):
    value: float = Field(default=50.0, ge=0.0, le=100.0)
    fatigue: float = Field(default=0.0, ge=0.0)
    last_sleep_date: date | None = None
    last_gym_boost_at: datetime | None = None
    last_activity_relief_at: datetime | None = None
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
    fatigue = mood.fatigue
    last_sleep_date = mood.last_sleep_date
    last_gym_boost_at = mood.last_gym_boost_at
    last_activity_relief_at = mood.last_activity_relief_at

    if mood.last_refreshed_at is not None:
        hours_elapsed = (now - mood.last_refreshed_at).total_seconds() / 3600.0
        drift = _DRIFT_PER_HOUR * hours_elapsed
        if value > 50.0:
            value = max(50.0, value - drift)
        elif value < 50.0:
            value = min(50.0, value + drift)
        fatigue = max(0.0, fatigue - _FATIGUE_DECAY_PER_HOUR * hours_elapsed)

    if SLEEP_WINDOW_START <= now.hour < SLEEP_WINDOW_END:
        if last_sleep_date is None or last_sleep_date < now.date():
            value += random.uniform(15.0, 25.0)
            fatigue *= _FATIGUE_SLEEP_RETENTION
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

    # Time spent at any activity is time away from the chat, so finishing one
    # eases how worn out she is from messaging.
    relief_cutoff = (
        last_activity_relief_at if last_activity_relief_at is not None else datetime.min
    )
    finished_activities = [e for e in calendar.entries if relief_cutoff < e.end <= now]
    if finished_activities:
        latest_activity = max(finished_activities, key=lambda e: e.end)
        fatigue = max(
            0.0, fatigue - _FATIGUE_RELIEF_PER_ACTIVITY * len(finished_activities)
        )
        last_activity_relief_at = latest_activity.end

    return Mood(
        value=max(0.0, min(100.0, value)),
        fatigue=fatigue,
        last_sleep_date=last_sleep_date,
        last_gym_boost_at=last_gym_boost_at,
        last_activity_relief_at=last_activity_relief_at,
        last_refreshed_at=now,
    )


def add_fatigue(mood: Mood, amount: float) -> Mood:
    if amount <= 0:
        return mood
    return mood.model_copy(update={"fatigue": mood.fatigue + amount})


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


_MOOD_BEHAVIOURS: list[tuple[float, str]] = [
    (
        20,
        "You're really struggling right now — flat, drained, not much energy for anyone. "
        "Replies are short and a bit blunt. You don't extend conversations; you close them off. "
        "Not rude, just clearly not in the mood to chat.",
    ),
    (
        35,
        "You're feeling low. Not a disaster, but you're not yourself. "
        "Replies are shorter than usual, enthusiasm is missing. "
        "You answer but don't really dig in. Humour is rare.",
    ),
    (
        45,
        "You're a bit meh — not bad, not good. Replies are normal length but a little flat. "
        "You engage, but you're not going out of your way. "
        "Small talk feels like mild effort.",
    ),
    (
        55,
        "You're in a neutral baseline mood — normal, relaxed. "
        "Replies are natural and at a comfortable length. "
        "You're friendly and engaged without being over the top.",
    ),
    (
        70,
        "You're in a pretty good mood — warm and a bit more talkative than usual. "
        "Humour comes naturally. You're more likely to ask follow-up questions or share something "
        "tangential. Messages are a little longer, more alive.",
    ),
    (
        85,
        "You're feeling great — genuinely upbeat and chatty. "
        "You're warmer, funnier, more generous with your time. "
        "You might volunteer things you wouldn't normally share. "
        "Energy is high and it shows in how you write.",
    ),
]

_MOOD_TOP = (
    "You're on top of the world right now — bubbly, enthusiastic, hard to bring down. "
    "Replies are expressive and warm. You joke around freely, you're interested in everything. "
    "It's a good day and you can't quite hide it."
)


def _mood_behaviour(value: float) -> str:
    for threshold, description in _MOOD_BEHAVIOURS:
        if value < threshold:
            return description
    return _MOOD_TOP


def build_mood_block(mood: Mood, now: datetime) -> str:
    lines = [
        f"Your mood right now: {mood.value:.0f}/100.",
        _mood_behaviour(mood.value),
    ]
    if (
        mood.last_gym_boost_at is not None
        and (now - mood.last_gym_boost_at).total_seconds() < 4 * 3600
    ):
        lines.append("You just got back from the gym and still feel the buzz.")
    elif mood.last_sleep_date == now.date() and now.hour < 14:
        lines.append("You woke up feeling refreshed today.")
    lines.append("Don't announce your mood score or label — just let it come through.")
    return "\n".join(lines) + "\n\n"
