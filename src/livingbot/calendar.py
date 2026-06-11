import logging
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel

from livingbot.prompts import WEEK_PLAN_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


class PlanEntry(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    activity: str
    location: str
    start: datetime
    end: datetime
    note: str = ""
    hobby: str = ""


class Calendar(BaseModel):
    home_location: str
    planned_week_start: date | None = None
    entries: list[PlanEntry] = Field(default_factory=list)

    def current_entry(self, now: datetime) -> PlanEntry | None:
        ongoing = [e for e in self.entries if e.start <= now <= e.end]
        if not ongoing:
            return None
        return max(ongoing, key=lambda e: e.start)

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
    note: str = ""
    hobby: str = ""


class WeekPlan(BaseModel):
    activities: list[PlannedActivity]


class WeekPlanner:
    def __init__(self, model: OpenAIChatModel) -> None:
        self._agent: Agent[None, WeekPlan] = Agent(
            model,
            system_prompt=WEEK_PLAN_SYSTEM_PROMPT,
            output_type=WeekPlan,
        )

    async def plan(
        self,
        week_start: date,
        hobbies: list[str],
        home_location: str,
        new_hobbies: list[str] | None = None,
    ) -> list[PlanEntry]:
        week_end = week_start + timedelta(days=6)
        prompt = (
            f"Week to plan: Monday {week_start} to Sunday {week_end}.\n"
            f"Her hobbies: {', '.join(hobbies)}.\n"
            f"Her home base: {home_location}."
        )
        if new_hobbies:
            prompt += (
                f"\nShe recently took up: {', '.join(new_hobbies)}. "
                "Give these new hobbies real time in the week."
            )
        try:
            result = await self._agent.run(prompt)
            return [PlanEntry(**a.model_dump()) for a in result.output.activities]
        except Exception:
            logger.exception("Failed to plan week starting %s", week_start)
            return []
