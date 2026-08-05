from dataclasses import dataclass

from livingbot.activity_notes import ActivityNotesStore
from livingbot.bot import LivingBot
from livingbot.calendar import CalendarStore
from livingbot.commitments import CommitmentStore
from livingbot.hobbies import HobbyStore
from livingbot.inventory import InventoryStore
from livingbot.memory import MemoryStore
from livingbot.mood import MoodStore
from livingbot.preferences import PreferenceStore
from livingbot.relations import RelationStore
from livingbot.scheduled_posts import ScheduledPostStore
from livingbot.spending import SpendingStore
from livingbot.spontaneous import SpontaneousStore
from livingbot.stories import StoryStore


@dataclass
class AdminContext:
    bot: LivingBot

    @property
    def calendar_store(self) -> CalendarStore:
        return self.bot.calendar_store

    @property
    def activity_notes_store(self) -> ActivityNotesStore:
        return self.bot.activity_notes_store

    @property
    def inventory_store(self) -> InventoryStore:
        return self.bot.inventory_store

    @property
    def spending_store(self) -> SpendingStore:
        return self.bot.spending_store

    @property
    def hobby_store(self) -> HobbyStore:
        return self.bot.hobby_store

    @property
    def story_store(self) -> StoryStore:
        return self.bot.story_store

    @property
    def mood_store(self) -> MoodStore:
        return self.bot.mood_store

    @property
    def relation_store(self) -> RelationStore:
        return self.bot.relation_store

    @property
    def memory_store(self) -> MemoryStore:
        return self.bot.memory_store

    @property
    def preference_store(self) -> PreferenceStore:
        return self.bot.preference_store

    @property
    def spontaneous_store(self) -> SpontaneousStore | None:
        return self.bot.spontaneous_store

    @property
    def commitment_store(self) -> CommitmentStore:
        return self.bot.commitment_store

    @property
    def scheduled_post_store(self) -> ScheduledPostStore | None:
        return self.bot.scheduled_post_store

    def discord_names(self) -> dict[str, str]:
        """Discord display names by user id, empty until the bot has connected."""
        if not self.bot.is_ready():
            return {}
        return {
            str(member.id): member.display_name
            for guild in self.bot.guilds
            for member in guild.members
        }
