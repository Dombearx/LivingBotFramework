from datetime import datetime

import discord
from pydantic import BaseModel
from pydantic_ai import Agent, AgentRunResult

from livingbot.calendar import Busyness, Calendar, CalendarStore
from livingbot.relations import Relation
from livingbot.tools import BotDeps, add_plan, load_context, remove_plan


class LLMConfig(BaseModel):
    model: str
    system_prompt: str


class LLMClient:
    def __init__(self, config: LLMConfig) -> None:
        self._config = config
        self._agent: Agent[BotDeps, str] = Agent(
            config.model,
            system_prompt=config.system_prompt,
            tools=[load_context, add_plan, remove_plan],
        )

    async def complete(
        self,
        user_messages: list[str],
        channel: discord.abc.Messageable,
        calendar_store: CalendarStore,
        now: datetime,
        memories: list[str] | None = None,
        relations: list[Relation] | None = None,
    ) -> AgentRunResult[str]:
        deps = BotDeps(channel=channel, calendar_store=calendar_store)
        prompt = "\n".join(user_messages)
        if memories:
            memory_block = "\n".join(f"- {m}" for m in memories)
            prompt = f"What I remember:\n{memory_block}\n\n{prompt}"
        if relations:
            prompt = _build_relations_block(relations) + prompt
        prompt = _build_calendar_block(calendar_store.load(), now) + prompt
        return await self._agent.run(prompt, deps=deps)


_BUSYNESS_DESCRIPTION = {
    Busyness.light: "barely occupied and can reply easily",
    Busyness.moderate: "occupied but glancing at your phone now and then",
    Busyness.deep: "fully absorbed and hard to reach",
}


def _build_calendar_block(calendar: Calendar, now: datetime) -> str:
    lines: list[str] = [f"Right now it is {now:%A, %Y-%m-%d %H:%M}."]
    current = calendar.current_entry(now)
    if current is not None:
        lines.append(
            f"You are at {current.location}, {current.activity} "
            f"until {current.end:%H:%M} — {_BUSYNESS_DESCRIPTION[current.busyness]}."
        )
    else:
        lines.append(f"You are at {calendar.home_location} with nothing scheduled.")
    upcoming = calendar.upcoming(now)
    if upcoming:
        lines.append("Your calendar:")
        for entry in upcoming:
            line = (
                f"  [id:{entry.id}] {entry.start:%a %m-%d %H:%M}"
                f"–{entry.end:%a %m-%d %H:%M} {entry.activity} @ {entry.location}"
            )
            if entry.note:
                line += f" ({entry.note})"
            lines.append(line)
    return "\n".join(lines) + "\n\n"


def _build_relations_block(relations: list[Relation]) -> str:
    blocks: list[str] = ["My relationships with the people in this conversation:"]
    for relation in relations:
        parts: list[str] = [
            f"  User {relation.user_id} (attitude: {relation.attitude}/100):"
        ]
        if relation.most_important_memory:
            parts.append(
                f"    - Most important memory: {relation.most_important_memory}"
            )
        if relation.inside_jokes:
            parts.append(f"    - Inside jokes: {', '.join(relation.inside_jokes)}")
        if relation.topics_of_interest:
            topics = ", ".join(relation.topics_of_interest)
            parts.append(
                f"    - Their interests: {topics}"
                " (only reference these if they are clearly relevant to what they just said)"
            )
        blocks.append("\n".join(parts))
    return "\n".join(blocks) + "\n\n"
