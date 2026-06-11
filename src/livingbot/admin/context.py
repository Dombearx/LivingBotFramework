from dataclasses import dataclass

from livingbot.bot import LivingBot


@dataclass
class AdminContext:
    bot: LivingBot

    @property
    def calendar_store(self):
        return self.bot.calendar_store

    @property
    def inventory_store(self):
        return self.bot.inventory_store

    @property
    def spending_store(self):
        return self.bot.spending_store

    @property
    def hobby_store(self):
        return self.bot.hobby_store

    @property
    def story_store(self):
        return self.bot.story_store

    @property
    def mood_store(self):
        return self.bot.mood_store

    @property
    def relation_store(self):
        return self.bot.relation_store

    @property
    def memory_store(self):
        return self.bot.memory_store
