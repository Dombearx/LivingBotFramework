import logging
from pathlib import Path
from typing import Any, Self

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel

from livingbot import llm_config
from livingbot.prompts import RELATION_UPDATE_SYSTEM_PROMPT

logger = logging.getLogger(__name__)

MAX_INSIDE_JOKES = 5
MAX_TOPICS_OF_INTEREST = 5

# Positive movement is scaled down and damped by the remaining headroom, so
# closeness approaches 100 asymptotically and the last stretch takes months of
# real conversation. Negative movement is applied at full weight: trust is lost
# faster than it is earned.
ATTITUDE_GAIN = 0.35


class Relation(BaseModel):
    user_id: str
    attitude: float = Field(default=0.0, ge=-100, le=100)
    inside_jokes: list[str] = Field(default_factory=list, max_length=MAX_INSIDE_JOKES)
    most_important_memory: str = Field(default="", max_length=200)
    topics_of_interest: list[str] = Field(
        default_factory=list, max_length=MAX_TOPICS_OF_INTEREST
    )
    last_attitude_reason: str = Field(default="", max_length=300)


class RelationUpdate(BaseModel):
    attitude_delta: int = Field(ge=-10, le=10)
    reason: str = Field(max_length=300)
    new_inside_joke: str | None = None
    remove_inside_jokes: list[str] = Field(default_factory=list)
    new_most_important_memory: str | None = Field(default=None, max_length=200)
    new_topics_of_interest: list[str] = Field(default_factory=list)


def apply_attitude_delta(attitude: float, delta: int) -> float:
    if delta <= 0:
        return max(-100.0, attitude + delta)
    headroom = 1.0 - max(attitude, 0.0) / 100.0
    return min(100.0, attitude + delta * ATTITUDE_GAIN * headroom)


def apply_update(relation: Relation, update: RelationUpdate) -> Relation:
    inside_jokes = [
        joke for joke in relation.inside_jokes if joke not in update.remove_inside_jokes
    ]
    if (
        update.new_inside_joke is not None
        and update.new_inside_joke not in inside_jokes
    ):
        inside_jokes.append(update.new_inside_joke)

    topics = list(relation.topics_of_interest)
    for topic in update.new_topics_of_interest:
        if topic not in topics:
            topics.append(topic)

    return relation.model_copy(
        update={
            "attitude": apply_attitude_delta(relation.attitude, update.attitude_delta),
            "inside_jokes": inside_jokes[-MAX_INSIDE_JOKES:],
            "most_important_memory": update.new_most_important_memory
            or relation.most_important_memory,
            "topics_of_interest": topics[-MAX_TOPICS_OF_INTEREST:],
            "last_attitude_reason": update.reason
            if update.attitude_delta != 0
            else relation.last_attitude_reason,
        }
    )


class RelationStore:
    def __init__(self, data_path: Path) -> None:
        self._data_path = data_path
        self._data_path.mkdir(parents=True, exist_ok=True)

    def _path_for(self, user_id: str) -> Path:
        return self._data_path / f"{user_id}.json"

    def load(self, user_id: str) -> Relation:
        path = self._path_for(user_id)
        if not path.exists():
            return Relation(user_id=user_id)
        return Relation.model_validate_json(path.read_text())

    def save(self, relation: Relation) -> None:
        path = self._path_for(relation.user_id)
        path.write_text(relation.model_dump_json(indent=2))

    def all(self) -> list[Relation]:
        return [
            Relation.model_validate_json(path.read_text())
            for path in sorted(self._data_path.glob("*.json"))
        ]


class RelationUpdater:
    @classmethod
    def create(cls) -> Self:
        return cls(llm_config.build_chat_model(llm_config.RELATION_UPDATER_MODEL))

    def __init__(self, model: OpenAIChatModel) -> None:
        self._agent: Agent[None, RelationUpdate] = Agent(
            model,
            name="relation_updater",
            instructions=RELATION_UPDATE_SYSTEM_PROMPT,
            output_type=RelationUpdate,
        )

    async def update(
        self,
        relation: Relation,
        conversation: list[dict[str, Any]],
        own_interests: list[str],
    ) -> RelationUpdate | None:
        conversation_text = "\n".join(
            f"{turn['role'].upper()}: {turn['content']}" for turn in conversation
        )
        interests_text = "\n".join(f"- {interest}" for interest in own_interests) or (
            "(nothing recorded yet)"
        )
        prompt = (
            f"Current relation:\n{relation.model_dump_json(indent=2)}\n\n"
            f"Mugda's own interests and tastes:\n{interests_text}\n\n"
            f"Conversation:\n{conversation_text}"
        )
        try:
            result = await self._agent.run(prompt)
            return result.output
        except Exception:
            logger.exception(
                "Failed to update relation for user_id=%s", relation.user_id
            )
            return None
