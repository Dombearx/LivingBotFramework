import random
from datetime import date, datetime, timedelta
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field

from livingbot import clock


class SpendCategory(str, Enum):
    trivial = "trivial"
    small = "small"
    medium = "medium"
    large = "large"
    splurge = "splurge"


POINT_COST: dict[SpendCategory, int] = {
    SpendCategory.trivial: 0,
    SpendCategory.small: 1,
    SpendCategory.medium: 2,
    SpendCategory.large: 4,
    SpendCategory.splurge: 8,
}

WEEKLY_POINTS_MIN = 3
WEEKLY_POINTS_MAX = 5
POINTS_CAP = 20


class Purchase(BaseModel):
    name: str
    category: SpendCategory
    bought_at: datetime = Field(default_factory=clock.now)


class SpendingState(BaseModel):
    week_start: date
    points_available: int
    purchases: list[Purchase] = Field(default_factory=list)


class SpendingStore:
    def __init__(self, data_path: Path) -> None:
        self._path = data_path / "spending.json"
        data_path.mkdir(parents=True, exist_ok=True)

    def load(self) -> SpendingState:
        current = _current_week_start()

        if not self._path.exists():
            state = SpendingState(
                week_start=current,
                points_available=random.randint(WEEKLY_POINTS_MIN, WEEKLY_POINTS_MAX),
            )
            self._write(state)
            return state

        state = SpendingState.model_validate_json(self._path.read_text())

        if state.week_start < current:
            while state.week_start < current:
                earned = random.randint(WEEKLY_POINTS_MIN, WEEKLY_POINTS_MAX)
                state.points_available = min(
                    state.points_available + earned, POINTS_CAP
                )
                state.week_start += timedelta(weeks=1)
            state.purchases = []
            self._write(state)

        return state

    def save(self, state: SpendingState) -> None:
        self._write(state)

    def can_afford(self, category: SpendCategory) -> bool:
        return self.load().points_available >= POINT_COST[category]

    def record(self, name: str, category: SpendCategory) -> Purchase:
        state = self.load()
        state.points_available = max(0, state.points_available - POINT_COST[category])
        purchase = Purchase(name=name, category=category)
        state.purchases.append(purchase)
        self._write(state)
        return purchase

    def summary(self) -> str:
        state = self.load()
        pts = state.points_available
        if state.purchases:
            bought = ", ".join(p.name for p in state.purchases)
            return f"Spending budget: {pts} pts left this week (bought this week: {bought})."
        return f"Spending budget: {pts} pts left this week."

    def _write(self, state: SpendingState) -> None:
        self._path.write_text(state.model_dump_json(indent=2))


def _current_week_start() -> date:
    today = clock.now().date()
    return today - timedelta(days=today.weekday())
