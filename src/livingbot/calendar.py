import logging
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Self

from pydantic import BaseModel, Field, field_validator
from pydantic_ai import Agent, ModelRetry, RunContext
from pydantic_ai.models.openai import OpenAIChatModel

from livingbot import clock, llm_config
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

    # LLMs sometimes emit timezone-aware datetimes; the life layer reasons in
    # Mugda's naive local wall clock (see clock.now), so normalise on the way in.
    @field_validator("start", "end")
    @classmethod
    def _to_naive_local(cls, value: datetime) -> datetime:
        return clock.to_local(value)


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
        cutoff = now - timedelta(days=30)
        self.entries = [e for e in self.entries if e.end >= cutoff]


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


def _reject_unknown_hobbies(ctx: RunContext[list[str]], plan: WeekPlan) -> WeekPlan:
    unknown = sorted(
        {a.hobby for a in plan.activities if a.hobby and a.hobby not in ctx.deps}
    )
    if unknown:
        raise ModelRetry(
            f"These are not her hobbies: {', '.join(unknown)}. "
            f"hobby must be exactly one of: {', '.join(ctx.deps)} — or empty for "
            "anything that is not her practising a hobby. Fix those activities and "
            "return the whole plan again."
        )
    return plan


class WeekPlanner:
    @classmethod
    def create(cls) -> Self:
        return cls(llm_config.build_chat_model(llm_config.WEEK_PLANNER_MODEL))

    def __init__(self, model: OpenAIChatModel) -> None:
        # A hobby name the planner invents matches nothing downstream, so the week's
        # experience is dropped silently; the validator sends it back to correct.
        # Two attempts because exhausting them raises, and plan() turns that into an
        # empty week — a worse outcome than the lost experience.
        self._agent: Agent[list[str], WeekPlan] = Agent(
            model,
            name="week_planner",
            instructions=WEEK_PLAN_SYSTEM_PROMPT,
            output_type=WeekPlan,
            deps_type=list[str],
            retries={"output": 2},
        )
        self._agent.output_validator(_reject_unknown_hobbies)

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
            result = await self._agent.run(prompt, deps=hobbies)
            return [PlanEntry(**a.model_dump()) for a in result.output.activities]
        except Exception:
            logger.exception("Failed to plan week starting %s", week_start)
            return []
