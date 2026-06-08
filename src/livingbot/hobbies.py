from pathlib import Path

from pydantic import BaseModel, Field


class Hobbies(BaseModel):
    names: list[str] = Field(default_factory=list)


class HobbyStore:
    def __init__(self, data_path: Path, default_hobbies: list[str]) -> None:
        self._path = data_path / "hobbies.json"
        self._default_hobbies = default_hobbies
        data_path.mkdir(parents=True, exist_ok=True)

    def load(self) -> Hobbies:
        if not self._path.exists():
            return Hobbies(names=list(self._default_hobbies))
        return Hobbies.model_validate_json(self._path.read_text())

    def save(self, hobbies: Hobbies) -> None:
        self._path.write_text(hobbies.model_dump_json(indent=2))
