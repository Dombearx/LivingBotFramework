from datetime import datetime
from pathlib import Path

import discord
from pydantic_ai import Agent, AgentRunResult
from pydantic_ai.models.openai import OpenAIChatModel

from livingbot.calendar import Calendar, CalendarStore
from livingbot.inventory import InventoryItem, InventoryStore
from livingbot.mood import Mood, build_mood_block
from livingbot.relations import Relation
from livingbot.spending import SpendingStore
from livingbot.tools import (
    BotDeps,
    add_item,
    add_plan,
    buy_item,
    check_budget,
    load_context,
    remove_item,
    remove_plan,
    search_inventory,
    take_photo,
)


class LLMResult:
    def __init__(self, run_result: AgentRunResult[str], deps: BotDeps) -> None:
        self.output: str = run_result.output
        self.photo: bytes | None = deps.photo_result


class LLMClient:
    def __init__(self, model: OpenAIChatModel, system_prompt: str) -> None:
        self._agent: Agent[BotDeps, str] = Agent(
            model,
            system_prompt=system_prompt,
            tools=[
                load_context,
                add_plan,
                remove_plan,
                add_item,
                remove_item,
                search_inventory,
                check_budget,
                buy_item,
                take_photo,
            ],
        )

    async def complete(
        self,
        user_messages: list[str],
        channel: discord.abc.Messageable,
        calendar_store: CalendarStore,
        inventory_store: InventoryStore,
        spending_store: SpendingStore,
        now: datetime,
        memories: list[str] | None = None,
        relations: list[Relation] | None = None,
        mood: Mood | None = None,
        photo_hint: str = "",
        portrait_path: Path = Path(),
    ) -> LLMResult:
        deps = BotDeps(
            channel=channel,
            calendar_store=calendar_store,
            inventory_store=inventory_store,
            spending_store=spending_store,
            portrait_path=portrait_path,
        )
        parts: list[str] = []
        if photo_hint:
            parts.append(f"{photo_hint}\n\n")
        parts.append(_build_calendar_block(calendar_store.load(), now))
        if mood is not None:
            parts.append(build_mood_block(mood, now))
        parts.append(spending_store.summary() + "\n\n")
        parts.append(_build_inventory_block(await inventory_store.recent()))
        if relations:
            parts.append(_build_relations_block(relations))
        if memories:
            memory_block = "\n".join(f"- {m}" for m in memories)
            parts.append(f"What I remember:\n{memory_block}\n\n")
        parts.append("\n".join(user_messages))
        prompt = "".join(parts)
        run_result = await self._agent.run(prompt, deps=deps)
        return LLMResult(run_result, deps)


def _build_calendar_block(calendar: Calendar, now: datetime) -> str:
    lines: list[str] = [f"Right now it is {now:%A, %Y-%m-%d %H:%M}."]
    current = calendar.current_entry(now)
    if current is not None:
        lines.append(
            f"You are at {current.location}, busy with {current.activity} "
            f"until {current.end:%H:%M}."
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


def _build_inventory_block(items: list[InventoryItem]) -> str:
    lines = [
        "Your most recently used special belongings (you may own more than this; assume "
        "you always have ordinary basics like everyday clothes, food and toiletries):"
    ]
    if items:
        for item in items:
            line = f"  [id:{item.id}] {item.name}"
            if item.description:
                line += f" — {item.description}"
            lines.append(line)
    else:
        lines.append("  (nothing special yet)")
    lines.append(
        "This list is only a recent slice, so search_inventory whenever you need to know "
        "if you own something not shown above. When you get, buy or make a specific item, "
        "record it with add_item; when you use it up, lose or give it away, drop it with "
        "remove_item."
    )
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
