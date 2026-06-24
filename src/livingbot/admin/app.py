import asyncio
import os

from nicegui import app, ui

from livingbot.admin.context import AdminContext
from livingbot.admin.pages import (
    calendar,
    hobbies,
    inventory,
    memories,
    mood,
    overview,
    relations,
    spending,
    stories,
    tools,
)
from livingbot.bot import build
from livingbot.observability import configure_logfire

ADMIN_HOST = "127.0.0.1"
ADMIN_PORT = 8080


def run() -> None:
    configure_logfire(service_name="livingbot-admin")
    token = os.environ["DISCORD_BOT_TOKEN"]
    bot = build()
    context = AdminContext(bot=bot)

    for page in (
        overview,
        inventory,
        stories,
        memories,
        calendar,
        hobbies,
        spending,
        mood,
        relations,
        tools,
    ):
        page.register(context)

    @app.on_startup
    async def _start_bot() -> None:
        asyncio.create_task(bot.start(token))

    ui.run(
        host=ADMIN_HOST,
        port=ADMIN_PORT,
        reload=False,
        show=False,
        title="Mugda admin",
    )
