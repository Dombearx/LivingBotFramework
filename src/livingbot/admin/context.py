from dataclasses import dataclass

from livingbot.bot import LivingBot
from livingbot.calendar import CalendarStore
from livingbot.hobbies import HobbyStore
from livingbot.inventory import InventoryStore
from livingbot.memory import MemoryStore
from livingbot.mood import MoodStore
from livingbot.relations import RelationStore
from livingbot.spending import SpendingStore
from livingbot.stories import StoryStore


@dataclass
class AdminContext:
    bot: LivingBot

    @property
    def calendar_store(self) -> CalendarStore:
        return self.bot.calendar_store

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
