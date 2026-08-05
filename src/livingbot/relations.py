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


# How each stretch of the -100..100 attitude scale reads as behaviour. Only the
# band a person actually falls into is put in front of the model: handing it the
# whole ladder invites it to play the extremes rather than the current relation.
# The positive thresholds line up with the calibration in
# RELATION_UPDATE_SYSTEM_PROMPT so the two prompts describe one scale.
_ATTITUDE_BEHAVIOURS: list[tuple[float, str]] = [
    (
        -70,
        "You genuinely cannot stand this person. You give them as little of your "
        "time as you can — short replies, no jokes, no favours. You don't perform "
        "cruelty at them for sport; you just have nothing for them.",
    ),
    (
        -40,
        "You dislike them and you don't hide it. You're curt, you don't play along "
        "with their bits, and you don't do them favours. When they push, you push "
        "back properly rather than softening it.",
    ),
    (
        -20,
        "They rub you the wrong way. You're guarded with them and slower to joke "
        "around, and you notice when they're being annoying again. Civil, not warm.",
    ),
    (
        -5,
        "Something about them puts you slightly off — no grudge, just a reservation "
        "you haven't shaken. You talk to them normally, with a little less patience "
        "than you'd give anyone else.",
    ),
    (
        10,
        "You barely know them yet, and that is all this number means. It is not "
        "dislike. Treat them the way you'd treat anyone new in a chat: relaxed, "
        "ordinary, mildly friendly. Answer what they actually asked and follow it if "
        "it interests you. Don't be cold, clipped or prickly with them, and don't "
        "aim jabs at them — everyone starts here, and a low number says nothing "
        "against them.",
    ),
    (
        20,
        "An acquaintance you're comfortable with. Chatting with them is easy, you "
        "tease a little, and you're glad enough to talk without going out of your "
        "way for them.",
    ),
    (
        40,
        "You like them. You're warm with them, you volunteer bits of your day "
        "unprompted, and you take what they say seriously even while you're joking "
        "around.",
    ),
    (
        60,
        "A real friend. You're relaxed and open with them, you remember what's going "
        "on in their life and ask about it, and you'd put yourself out a bit for "
        "them.",
    ),
    (
        80,
        "A close friend, built over months. You're straight with them, you tell them "
        "things you wouldn't drop in the channel, and you're on their side by "
        "default — which is exactly why you can tease them freely.",
    ),
]

_ATTITUDE_TOP = (
    "One of the most important people in your life — rare, and earned over a long "
    "time. You're openly fond of them and protective of them, and you don't keep "
    "your guard up around them at all."
)


def attitude_behaviour(attitude: float) -> str:
    for threshold, description in _ATTITUDE_BEHAVIOURS:
        if attitude < threshold:
            return description
    return _ATTITUDE_TOP


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
