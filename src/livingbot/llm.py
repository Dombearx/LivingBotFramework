from datetime import datetime

import discord
from pydantic_ai import Agent, AgentRunResult, BinaryContent
from pydantic_ai.messages import UserContent
from pydantic_ai.models.openai import OpenAIChatModel

from livingbot import config
from livingbot.calendar import Calendar, CalendarStore
from livingbot.hobbies import Hobbies, HobbyLevel, HobbyStore, recent_hobbies
from livingbot.inventory import InventoryItem, InventoryStore
from livingbot.mood import Mood, build_mood_block
from livingbot.relations import Relation
from livingbot.spending import SpendingStore
from livingbot.stories import Story, StoryStore
from livingbot.timeformat import humanize_ago
from livingbot.tools import (
    BotDeps,
    add_hobby,
    add_item,
    add_plan,
    buy_item,
    check_budget,
    load_context,
    mark_story_told,
    recall_story,
    remove_item,
    remove_plan,
    search_inventory,
    show_story_image,
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
                add_hobby,
                recall_story,
                mark_story_told,
                show_story_image,
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
        hobby_store: HobbyStore,
        story_store: StoryStore,
        now: datetime,
        memories: list[str] | None = None,
        relations: list[Relation] | None = None,
        mood: Mood | None = None,
        photo_hint: str = "",
        images: list[BinaryContent] | None = None,
    ) -> LLMResult:
        deps = BotDeps(
            channel=channel,
            calendar_store=calendar_store,
            inventory_store=inventory_store,
            spending_store=spending_store,
            hobby_store=hobby_store,
            story_store=story_store,
        )
        parts: list[str] = []
        if photo_hint:
            parts.append(f"{photo_hint}\n\n")
        parts.append(_build_calendar_block(calendar_store.load(), now))
        hobbies = hobby_store.load()
        parts.append(_build_hobbies_block(hobbies))
        recent_items = await inventory_store.recently_acquired(
            now - config.RECENT_PURCHASE_WINDOW
        )
        recent_block = _build_recent_block(hobbies, recent_items, now)
        if recent_block:
            parts.append(recent_block)
        if mood is not None:
            parts.append(build_mood_block(mood, now))
        parts.append(spending_store.summary() + "\n\n")
        parts.append(_build_inventory_block(await inventory_store.recent()))
        if relations:
            parts.append(_build_relations_block(relations))
        parts.append(_build_stories_block(await story_store.untold()))
        if memories:
            memory_block = "\n".join(f"- {m}" for m in memories)
            parts.append(f"What I remember:\n{memory_block}\n\n")
        parts.append("\n".join(user_messages))
        prompt: list[UserContent] = ["".join(parts), *(images or [])]
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


_HOBBY_LEVEL_TONE: dict[HobbyLevel, str] = {
    HobbyLevel.novice: (
        "you're still new to it — curious, a little unsure of yourself, "
        "easily impressed by people who are better at it"
    ),
    HobbyLevel.beginner: (
        "you've got the basics down — more confident, but still learning "
        "and happy to ask questions"
    ),
    HobbyLevel.intermediate: (
        "you're comfortable with it — you know your way around and have "
        "your own preferences and little routines"
    ),
    HobbyLevel.advanced: (
        "you're quite skilled — you can speak with real authority and "
        "notice details that beginners wouldn't"
    ),
    HobbyLevel.expert: (
        "you're an expert — you talk about it with deep, casual knowledge "
        "and don't hold back your opinions"
    ),
}


def _build_hobbies_block(hobbies: Hobbies) -> str:
    if not hobbies.entries:
        return "You don't have any particular hobbies right now.\n\n"
    lines = ["Your hobbies, and how skilled you are at each:"]
    for hobby in hobbies.entries:
        lines.append(
            f"  {hobby.name} — {hobby.level.value}: {_HOBBY_LEVEL_TONE[hobby.level]}"
        )
    return "\n".join(lines) + "\n\n"


def _build_recent_block(
    hobbies: Hobbies, recent_items: list[InventoryItem], now: datetime
) -> str:
    highlights: list[tuple[datetime, str]] = []
    for hobby in recent_hobbies(hobbies, now, config.RECENT_HOBBY_WINDOW):
        highlights.append(
            (
                hobby.acquired_at,
                f"You took up {hobby.name} {humanize_ago(hobby.acquired_at, now)}.",
            )
        )
    for item in recent_items:
        highlights.append(
            (
                item.acquired_at,
                f"You got {item.name} {humanize_ago(item.acquired_at, now)}.",
            )
        )
    if not highlights:
        return ""
    highlights.sort(key=lambda highlight: highlight[0], reverse=True)
    lines = ["Recently in your life:"]
    lines.extend(f"  {text}" for _, text in highlights)
    return "\n".join(lines) + "\n\n"


def _build_stories_block(stories: list[Story]) -> str:
    lines = ["Stories from your life you haven't shared with this group yet:"]
    if stories:
        for story in stories:
            line = f"  [id:{story.id}] {story.summary}"
            if story.image_path:
                line += " (has a photo)"
            lines.append(line)
    else:
        lines.append("  (nothing new to tell right now)")
    lines.append(
        "Share one naturally if it genuinely fits the moment — don't force it in. "
        "After telling one, call mark_story_told so you don't repeat it later. Use "
        "recall_story to find one that matches the conversation, including stories "
        "you've already told, so you can casually refer back to them. When a story has "
        "a photo, attach it with show_story_image as you tell it."
    )
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
