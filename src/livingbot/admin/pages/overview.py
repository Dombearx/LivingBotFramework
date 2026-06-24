from datetime import datetime

from nicegui import ui

from livingbot import clock
from livingbot.admin.context import AdminContext
from livingbot.admin.pages.layout import page_layout
from livingbot.bot import LivingBot


def register(context: AdminContext) -> None:
    @ui.page("/")
    async def overview() -> None:
        with page_layout("Overview"):
            now = clock.now()
            bot = context.bot

            with ui.row().classes("w-full gap-4 flex-wrap"):
                _connection_card(bot)
                _runtime_card(bot)
                _mood_card(context, now)

            with ui.row().classes("w-full gap-4 flex-wrap"):
                _calendar_card(context, now)
                _hobbies_card(context)
                _spending_card(context)

            await _counts_card(context)


def _card(title: str) -> ui.card:
    card = ui.card().classes("min-w-64 grow")
    with card:
        ui.label(title).classes("text-lg font-semibold")
    return card


def _connection_card(bot: LivingBot) -> None:
    with _card("Discord"):
        ready = bot.is_ready()
        ui.label(f"Connected: {'yes' if ready else 'no'}")
        if ready:
            ui.label(f"User: {bot.user}")
            ui.label(f"Latency: {bot.latency * 1000:.0f} ms")
            ui.label(f"Guilds: {len(bot.guilds)}")


def _runtime_card(bot: LivingBot) -> None:
    with _card("Runtime"):
        ui.label(f"Fatigue: {bot.fatigue:.2f}")
        ui.label(f"Resting: {'yes' if bot.resting else 'no'}")
        ui.label(
            f"Messages since photo: {bot.messages_since_photo} / {bot.photo_cooldown}"
        )


def _mood_card(context: AdminContext, now: datetime) -> None:
    mood = context.mood_store.load()
    with _card("Mood"):
        ui.linear_progress(value=mood.value / 100.0, show_value=False).classes("w-full")
        ui.label(f"{mood.value:.0f} / 100")
        ui.label(f"Last sleep: {mood.last_sleep_date or '—'}")
        gym = mood.last_gym_boost_at
        ui.label(
            f"Last gym boost: {gym:%Y-%m-%d %H:%M}" if gym else "Last gym boost: —"
        )


def _calendar_card(context: AdminContext, now: datetime) -> None:
    calendar = context.calendar_store.load()
    current = calendar.current_entry(now)
    upcoming = calendar.upcoming(now)
    with _card("Calendar"):
        if current is not None:
            ui.label(f"Now: {current.activity} @ {current.location}")
        else:
            ui.label(f"Now: idle at {calendar.home_location}")
        ui.label(f"Upcoming entries: {len(upcoming)}")
        for entry in upcoming[:3]:
            ui.label(
                f"{entry.start:%a %H:%M} {entry.activity} @ {entry.location}"
            ).classes("text-sm text-gray-500")


def _hobbies_card(context: AdminContext) -> None:
    hobbies = context.hobby_store.load()
    with _card("Hobbies"):
        if not hobbies.entries:
            ui.label("None")
        for hobby in hobbies.entries:
            ui.label(f"{hobby.name} — {hobby.level.value} ({hobby.experience} xp)")


def _spending_card(context: AdminContext) -> None:
    state = context.spending_store.load()
    with _card("Spending"):
        ui.label(f"Points available: {state.points_available}")
        ui.label(f"Purchases this week: {len(state.purchases)}")


async def _counts_card(context: AdminContext) -> None:
    inventory = await context.inventory_store.all()
    stories = await context.story_store.all()
    relations = context.relation_store.all()
    told = sum(1 for story in stories if story.told_at is not None)
    with _card("Databases"):
        ui.label(f"Inventory items: {len(inventory)}")
        ui.label(f"Stories: {len(stories)} ({told} told, {len(stories) - told} untold)")
        ui.label(f"Relations tracked: {len(relations)}")
