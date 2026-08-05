from datetime import datetime, timedelta
from typing import Self

import discord
from pydantic_ai import Agent, AgentRunResult, BinaryContent
from pydantic_ai.messages import ModelMessage, UserContent
from pydantic_ai.models.openai import OpenAIChatModel

from livingbot import config, llm_config, prompts
from livingbot.activity_notes import ActivityNotes, ActivityNotesStore
from livingbot.calendar import Calendar, CalendarStore, PlanEntry
from livingbot.commitments import Commitment, CommitmentStore
from livingbot.hobbies import Hobbies, HobbyLevel, HobbyStore, recent_hobbies
from livingbot.inventory import InventoryItem, InventoryStore
from livingbot.mood import Mood, build_mood_block, is_awake
from livingbot.preferences import Preferences, PreferenceStore
from livingbot.directory import Directory
from livingbot.relations import Relation, attitude_behaviour
from livingbot.spending import SpendingStore
from livingbot.stories import Story, StoryStore
from livingbot.timeformat import humanize_ago
from livingbot.tools import (
    OWN_MESSAGE_MARKER,
    BotDeps,
    add_activity_note,
    add_commitment,
    add_hobby,
    add_item,
    add_plan,
    buy_item,
    check_budget,
    fetch_link,
    load_context,
    mark_story_told,
    recall_story,
    record_preference,
    remove_activity_note,
    remove_item,
    remove_plan,
    resolve_commitment,
    search_inventory,
    show_story_image,
    take_photo,
)


class LLMResult:
    def __init__(self, run_result: AgentRunResult[str], deps: BotDeps) -> None:
        self._run_result = run_result
        self.output: str = run_result.output
        self.photo: bytes | None = deps.photo_result

    def all_messages(self) -> list[ModelMessage]:
        return self._run_result.all_messages()


class LLMClient:
    @classmethod
    def create(cls) -> Self:
        return cls(
            llm_config.build_chat_model(llm_config.CHAT_MODEL, reasoning_effort="low"),
            prompts.SYSTEM_PROMPT,
        )

    def __init__(self, model: OpenAIChatModel, instructions: str) -> None:
        self._agent: Agent[BotDeps, str] = Agent(
            model,
            name="chat",
            instructions=instructions,
            tools=[
                fetch_link,
                load_context,
                add_plan,
                remove_plan,
                add_activity_note,
                remove_activity_note,
                add_item,
                remove_item,
                search_inventory,
                add_hobby,
                record_preference,
                recall_story,
                mark_story_told,
                show_story_image,
                check_budget,
                buy_item,
                take_photo,
                add_commitment,
                resolve_commitment,
            ],
        )

    async def complete(
        self,
        user_messages: list[str],
        channel: discord.abc.Messageable,
        channel_id: int,
        calendar_store: CalendarStore,
        activity_notes_store: ActivityNotesStore,
        inventory_store: InventoryStore,
        spending_store: SpendingStore,
        hobby_store: HobbyStore,
        story_store: StoryStore,
        preference_store: PreferenceStore,
        commitment_store: CommitmentStore,
        now: datetime,
        memories: list[str] | None = None,
        relations: list[Relation] | None = None,
        mood: Mood | None = None,
        photo_hint: str = "",
        images: list[BinaryContent] | None = None,
        waiting_since: datetime | None = None,
        history: list[str] | None = None,
        shared_ending: str | None = None,
        commitments: list[Commitment] | None = None,
        trigger: str | None = None,
        server_emojis: list[str] | None = None,
        directory: Directory | None = None,
    ) -> LLMResult:
        directory = directory if directory is not None else Directory({})
        deps = BotDeps(
            channel=channel,
            channel_id=channel_id,
            calendar_store=calendar_store,
            activity_notes_store=activity_notes_store,
            inventory_store=inventory_store,
            spending_store=spending_store,
            hobby_store=hobby_store,
            story_store=story_store,
            preference_store=preference_store,
            commitment_store=commitment_store,
            directory=directory,
        )
        parts: list[str] = []
        if photo_hint:
            parts.append(f"{photo_hint}\n\n")
        calendar = calendar_store.load()
        parts.append(_build_calendar_block(calendar, now))
        if waiting_since is not None:
            parts.append(_build_delay_block(calendar, waiting_since, now))
        parts.append(_build_activity_notes_block(activity_notes_store.load()))
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
        parts.append(_build_preferences_block(preference_store.load()))
        if relations:
            parts.append(_build_relations_block(relations, directory))
        if commitments:
            parts.append(_build_commitments_block(commitments, now, directory))
        parts.append(_build_stories_block(await story_store.untold()))
        if memories:
            memory_block = "\n".join(f"- {m}" for m in memories)
            parts.append(f"What I remember:\n{memory_block}\n\n")
        if server_emojis:
            parts.append(_build_server_emojis_block(server_emojis))
        if history:
            parts.append(_build_history_block(history))
        if shared_ending:
            parts.append(_build_shared_ending_block(shared_ending))
        parts.append(
            trigger if trigger is not None else _build_new_messages_block(user_messages)
        )
        prompt: list[UserContent] = ["".join(parts), *(images or [])]
        run_result = await self._agent.run(prompt, deps=deps)
        return LLMResult(run_result, deps)


def _build_calendar_block(calendar: Calendar, now: datetime) -> str:
    lines: list[str] = [f"Right now it is {now:%A, %Y-%m-%d %H:%M}."]
    current = calendar.current_entry(now)
    if current is not None:
        line = (
            f"You are at {current.location}, busy with {current.activity} "
            f"until {current.end:%H:%M}."
        )
        if current.note:
            line += f" ({current.note})"
        lines.append(line)
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


def _build_delay_block(
    calendar: Calendar, waiting_since: datetime, now: datetime
) -> str:
    """Explain a long silence only when her life accounts for it.

    Being worn out from too much messaging is deliberately left unexplained: it is
    a mechanic, not something a person would narrate, so she is simply late.
    """
    if now - waiting_since < config.DELAY_EXPLANATION_THRESHOLD:
        return ""
    reasons: list[str] = []
    if _asleep_between(waiting_since, now):
        reasons.append("you were asleep")
    entry = _entry_between(calendar, waiting_since, now)
    if entry is not None:
        reasons.append(f"you were at {entry.location}, busy with {entry.activity}")
    if not reasons:
        return ""
    return (
        f"That message came in {humanize_ago(waiting_since, now)} and you're only "
        f"getting to it now — {' and '.join(reasons)} in the meantime. React the way "
        "anyone does picking their phone back up after a while: bring it up in passing "
        "if it fits, keep it light rather than a formal apology, and never explain the "
        "gap in mechanical terms.\n\n"
    )


def _asleep_between(start: datetime, end: datetime) -> bool:
    moment = start
    while moment < end:
        if not is_awake(moment):
            return True
        moment += timedelta(hours=1)
    return not is_awake(end)


def _entry_between(
    calendar: Calendar, start: datetime, end: datetime
) -> PlanEntry | None:
    overlapping = [e for e in calendar.entries if e.start < end and e.end > start]
    if not overlapping:
        return None
    return max(overlapping, key=lambda e: e.end)


def _build_activity_notes_block(notes: ActivityNotes) -> str:
    if not notes.entries:
        return ""
    lines = ["Standing reminders you keep for certain activities:"]
    for note in notes.entries:
        lines.append(f"  [id:{note.id}] {note.activity}: {note.note}")
    lines.append(
        "These follow you to every occurrence of the activity. Add one with "
        "add_activity_note and drop it with remove_activity_note once it no longer "
        "applies."
    )
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
        acquired_at = hobby.acquired_at
        assert acquired_at is not None
        highlights.append(
            (
                acquired_at,
                f"You took up {hobby.name} {humanize_ago(acquired_at, now)}.",
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


def _build_preferences_block(preferences: Preferences) -> str:
    lines = ["Tastes and preferences you have already settled on:"]
    if preferences.entries:
        for preference in preferences.entries:
            lines.append(f"  {preference.topic}: {preference.stance}")
    else:
        lines.append("  (you haven't pinned any down yet)")
    lines.append(
        "Stay consistent with these — they are yours. When you're asked about "
        "something not on the list, don't sit on the fence: decide, say which side "
        "you're on, and record it with record_preference so it sticks."
    )
    return "\n".join(lines) + "\n\n"


def _build_relations_block(relations: list[Relation], directory: Directory) -> str:
    blocks: list[str] = ["My relationships with the people in this conversation:"]
    for relation in relations:
        parts: list[str] = [
            f"  {directory.name_for(relation.user_id)} "
            f"(attitude: {round(relation.attitude)}/100):",
            f"    - How you feel about them: {attitude_behaviour(relation.attitude)}",
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
    if any(relation.inside_jokes for relation in relations):
        blocks.append(
            "Inside jokes are callbacks, not catchphrases. Only bring one up when this "
            "moment genuinely calls it back, and never work one into a message just to "
            "use it — repeating the same line over and over is the fastest way to stop "
            "sounding like a person."
        )
    return "\n".join(blocks) + "\n\n"


def _build_commitments_block(
    commitments: list[Commitment], now: datetime, directory: Directory
) -> str:
    lines = ["Promises you've made that you haven't followed through on yet:"]
    for commitment in commitments:
        line = (
            f"  [id:{commitment.id}] to {directory.name_for(commitment.user_id)}: "
            f"{commitment.description} (promised {humanize_ago(commitment.made_at, now)}, "
            f'you said: "{commitment.due_hint}"'
        )
        if commitment.nudged_at is not None:
            line += f"; you already brought this up {humanize_ago(commitment.nudged_at, now)}"
        lines.append(line + ")")
    lines.append(
        "If it's genuinely time and it fits the conversation, follow through now. Once "
        "you do, call resolve_commitment so you don't bring it up again. One you have "
        "already brought up doesn't need raising a second time — leave it be unless "
        "they come back to it."
    )
    return "\n".join(lines) + "\n\n"


def _build_history_block(history: list[str]) -> str:
    history_text = "\n".join(history)
    block = (
        f"Earlier in the conversation:\n{history_text}\n"
        "The lines marked (you) are your own earlier messages. They are here so you stay "
        "coherent with what you already said — not as a style to copy.\n\n"
    )
    return block + _build_own_messages_block(history)


def _build_own_messages_block(history: list[str]) -> str:
    """Repeat her own recent messages back on their own.

    Interleaved through everyone else's they are context; gathered together they are
    a pattern, which is what the instruction below actually asks her to look at.
    """
    own = own_messages(history)
    if not own:
        return ""
    recent = "\n".join(own)
    return (
        f"Your own last messages, oldest first:\n{recent}\n"
        "Read how these end. Anything they already share — a closing joke, the same "
        "emoji, the same rhythm, the same way of handing the conversation back — is a "
        "habit setting in, and you don't do it again here. Say the next thing plainly "
        "instead.\n\n"
    )


def _is_own_message(line: str) -> bool:
    header = line.split(": ", 1)[0]
    return header.endswith(OWN_MESSAGE_MARKER)


def own_messages(history: list[str]) -> list[str]:
    return [line for line in history if _is_own_message(line)][
        -config.RECENT_OWN_MESSAGE_LIMIT :
    ]


def _build_shared_ending_block(shared_ending: str) -> str:
    return (
        f"Every one of your last few messages ends the same way: {shared_ending}. That "
        "is a habit now, and one more would make it your voice rather than a thing you "
        "happened to do. This reply ends some other way — finish on the plain thing you "
        "meant, or on whatever this particular message actually calls for.\n\n"
    )


def _build_server_emojis_block(emojis: list[str]) -> str:
    lines = ["Custom emoji that exist on this Discord server:"]
    lines.extend(f"  {emoji}" for emoji in emojis)
    lines.append(
        "Write one exactly as shown, angle brackets and all, or it won't render. These "
        "are yours to use like any other emoji — once in a while, when one genuinely "
        "fits, not in every message."
    )
    return "\n".join(lines) + "\n\n"


def _build_new_messages_block(user_messages: list[str]) -> str:
    messages_text = "\n".join(user_messages)
    return f"New message(s) to respond to:\n{messages_text}"
