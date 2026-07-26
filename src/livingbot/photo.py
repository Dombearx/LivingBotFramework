import random
from pathlib import Path

from pydantic import BaseModel, Field

from livingbot import config


def _random_cooldown() -> int:
    return random.randint(config.PHOTO_COOLDOWN_MIN, config.PHOTO_COOLDOWN_MAX)


class PhotoCooldown(BaseModel):
    messages_since_photo: int = 0
    cooldown: int = Field(default_factory=_random_cooldown)


class PhotoCooldownStore:
    def __init__(self, data_path: Path) -> None:
        self._path = data_path / "photo_cooldown.json"
        data_path.mkdir(parents=True, exist_ok=True)

    def load(self) -> PhotoCooldown:
        if not self._path.exists():
            return PhotoCooldown()
        return PhotoCooldown.model_validate_json(self._path.read_text())

    def save(self, photo_cooldown: PhotoCooldown) -> None:
        self._path.write_text(photo_cooldown.model_dump_json(indent=2))
