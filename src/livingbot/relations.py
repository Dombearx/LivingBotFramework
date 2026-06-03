import logging
from pathlib import Path

from pydantic import BaseModel, Field
from pydantic_ai import Agent

logger = logging.getLogger(__name__)


class Relation(BaseModel):
    user_id: str
    attitude: int = Field(default=0, ge=-100, le=100)
    inside_jokes: list[str] = Field(default_factory=list, max_length=5)
    most_important_memory: str = Field(default="", max_length=200)
    topics_of_interest: list[str] = Field(default_factory=list, max_length=5)


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


_UPDATE_SYSTEM_PROMPT = """\
You maintain a relationship record for a Discord bot that behaves like a real person.
Given the current relation state and a conversation excerpt, return an updated relation as JSON.

Rules:
- attitude: integer from -100 (hostile) to 100 (very close). Adjust based on tone and content.
- inside_jokes: references that are funny or meaningful specifically between these two. Max 5 items. Drop old ones if needed.
- most_important_memory: the single most defining moment or fact about this person. Max 200 characters.
- topics_of_interest: subjects this user genuinely cares about. Max 5 items. Only add something if clearly evidenced.
- user_id must not change.
Return only valid JSON matching the relation schema. No extra text.\
"""


class RelationUpdater:
    def __init__(self, model: str) -> None:
        self._agent: Agent[None, Relation] = Agent(
            model,
            system_prompt=_UPDATE_SYSTEM_PROMPT,
            output_type=Relation,
        )

    async def update(self, relation: Relation, conversation: list[dict]) -> Relation:
        conversation_text = "\n".join(
            f"{turn['role'].upper()}: {turn['content']}" for turn in conversation
        )
        prompt = (
            f"Current relation:\n{relation.model_dump_json(indent=2)}\n\n"
            f"Conversation:\n{conversation_text}"
        )
        try:
            result = await self._agent.run(prompt)
            updated = result.output
            updated = updated.model_copy(update={"user_id": relation.user_id})
            return updated
        except Exception:
            logger.exception(
                "Failed to update relation for user_id=%s", relation.user_id
            )
            return relation
