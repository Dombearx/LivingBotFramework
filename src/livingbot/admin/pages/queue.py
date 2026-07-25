from datetime import datetime

import discord
from nicegui import ui

from livingbot import clock
from livingbot.admin.context import AdminContext
from livingbot.admin.pages.layout import page_layout

REFRESH_SECONDS = 5.0


def register(context: AdminContext) -> None:
    @ui.page("/queue")
    def queue_page() -> None:
        with page_layout("Queue"):

            @ui.refreshable
            def queue_view() -> None:
                now = clock.now()
                bot = context.bot
                pending = bot.pending_messages

                with ui.card().classes("w-full"):
                    ui.label("Response state").classes("text-lg font-semibold")
                    ui.label(f"Messages waiting: {len(pending)}")
                    ui.label(f"Resting: {'yes' if bot.resting else 'no'}")
                    ui.label(f"Fatigue: {bot.fatigue:.2f}")
                    ui.label(f"Next reply attempt: {_next_attempt(context, now)}")
                    ui.label(
                        f"Next spontaneous post: {_next_spontaneous_post(context, now)}"
                    )

                if not pending:
                    ui.label("Nothing in the queue.")
                    return
                for message in pending:
                    _render_message(message, now)

            ui.timer(REFRESH_SECONDS, queue_view.refresh)
            queue_view()


def _next_attempt(context: AdminContext, now: datetime) -> str:
    if not context.bot.resting:
        return "as soon as the next message arrives"
    return _describe_moment(context.bot.next_attempt_at, now)


def _next_spontaneous_post(context: AdminContext, now: datetime) -> str:
    store = context.spontaneous_store
    if store is None:
        return "—"
    return _describe_moment(store.load().next_post_at, now)


def _describe_moment(moment: datetime | None, now: datetime) -> str:
    if moment is None:
        return "—"
    minutes = (moment - now).total_seconds() / 60.0
    if minutes <= 0:
        return f"{moment:%Y-%m-%d %H:%M} (due now)"
    if minutes < 60:
        return f"{moment:%Y-%m-%d %H:%M} (in {minutes:.0f} min)"
    return f"{moment:%Y-%m-%d %H:%M} (in {minutes / 60:.1f} h)"


def _render_message(message: discord.Message, now: datetime) -> None:
    sent_at = clock.to_local(message.created_at)
    channel = getattr(message.channel, "name", None) or str(message.channel.id)
    with ui.card().classes("w-full"):
        ui.label(
            f"{message.author.display_name} · #{channel} · "
            f"{sent_at:%Y-%m-%d %H:%M:%S} · waiting "
            f"{(now - sent_at).total_seconds() / 60:.0f} min"
        ).classes("text-sm text-gray-500")
        ui.label(message.content or "(no text)")
