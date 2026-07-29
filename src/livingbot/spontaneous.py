from datetime import datetime
from pathlib import Path

from pydantic import BaseModel


class SpontaneousState(BaseModel):
    next_post_at: datetime | None = None


class SpontaneousStore:
    def __init__(self, data_path: Path) -> None:
        self._path = data_path / "spontaneous.json"
        data_path.mkdir(parents=True, exist_ok=True)

    def load(self) -> SpontaneousState:
        if not self._path.exists():
            return SpontaneousState()
        return SpontaneousState.model_validate_json(self._path.read_text())

    def save(self, state: SpontaneousState) -> None:
        self._path.write_text(state.model_dump_json(indent=2))
