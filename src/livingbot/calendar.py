import logging
import uuid
from datetime import date, datetime, timedelta
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field
from pydantic_ai import Agent

logger = logging.getLogger(__name__)


class Busyness(str, Enum):
    light = "light"
    moderate = "moderate"
    deep = "deep"


class PlanEntry(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    activity: str
    location: str
    start: datetime
    end: datetime
    busyness: Busyness = Busyness.moderate
    note: str = ""


class Calendar(BaseModel):
    home_location: str
    planned_week_start: date | None = None
    entries: list[PlanEntry] = Field(default_factory=list)

    def current_entry(self, now: datetime) -> PlanEntry | None:
        ongoing = [e for e in self.entries if e.start <= now <= e.end]
        if not ongoing:
            return None
        return max(ongoing, key=lambda e: e.start)

    def current_location(self, now: datetime) -> str:
        entry = self.current_entry(now)
        return entry.location if entry else self.home_location

    def upcoming(self, now: datetime) -> list[PlanEntry]:
        return sorted((e for e in self.entries if e.end >= now), key=lambda e: e.start)

    def prune_past(self, now: datetime) -> None:
        self.entries = [e for e in self.entries if e.end >= now]


class CalendarStore:
    def __init__(self, data_path: Path, home_location: str) -> None:
        self._path = data_path / "calendar.json"
        self._home_location = home_location
        data_path.mkdir(parents=True, exist_ok=True)

    def load(self) -> Calendar:
        if not self._path.exists():
            return Calendar(home_location=self._home_location)
        return Calendar.model_validate_json(self._path.read_text())

    def save(self, calendar: Calendar) -> None:
        self._path.write_text(calendar.model_dump_json(indent=2))


class PlannedActivity(BaseModel):
    activity: str
    location: str
    start: datetime
    end: datetime
    busyness: Busyness = Busyness.moderate
    note: str = ""


class WeekPlan(BaseModel):
    activities: list[PlannedActivity]


_WEEK_PLAN_SYSTEM_PROMPT = """\
You plan the week for a Discord bot that lives like a real young woman somewhere in Poland.
Given the week's start date and her hobbies, return a rough, realistic weekly plan as JSON.

Rules:
- Schedule her hobbies at concrete days and times within the week. The gym is her main hobby:
  give it 3-4 sessions of about 1.5 hours, on varied days, usually in the evening.
- Add a few ordinary bits of life (errands, seeing friends, a relaxed weekend) so the week feels lived-in.
- Do not overschedule. Leave most of her time open.
- Each activity needs a start and end datetime that fall within the planned week.
- location is where she physically is during the activity (e.g. "gym", "home", "city centre").
- busyness is how unreachable the activity makes her, one of:
    "deep": fully absorbed, phone away (gym, cinema, an important meeting).
    "moderate": occupied but can glance at her phone now and then (coffee with a friend, cooking).
    "light": barely occupied, easily reachable (errands, a relaxed walk, visiting parents).
Return only valid JSON matching the schema. No extra text.\
"""


class WeekPlanner:
    def __init__(self, model: str) -> None:
        self._agent: Agent[None, WeekPlan] = Agent(
            model,
            system_prompt=_WEEK_PLAN_SYSTEM_PROMPT,
            output_type=WeekPlan,
        )

    async def plan(
        self, week_start: date, hobbies: list[str], home_location: str
    ) -> list[PlanEntry]:
        week_end = week_start + timedelta(days=6)
        prompt = (
            f"Week to plan: Monday {week_start} to Sunday {week_end}.\n"
            f"Her hobbies: {', '.join(hobbies)}.\n"
            f"Her home base: {home_location}."
        )
        try:
            result = await self._agent.run(prompt)
            return [PlanEntry(**a.model_dump()) for a in result.output.activities]
        except Exception:
            logger.exception("Failed to plan week starting %s", week_start)
            return []
