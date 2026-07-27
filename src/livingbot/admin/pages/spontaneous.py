from datetime import datetime

from nicegui import ui

from livingbot.admin.context import AdminContext
from livingbot.admin.pages.layout import page_layout

_DT_FORMAT = "%Y-%m-%d %H:%M"


def register(context: AdminContext) -> None:
    @ui.page("/spontaneous")
    def spontaneous_page() -> None:
        with page_layout("Spontaneous"):
            store = context.spontaneous_store
            if store is None:
                ui.label("Not configured")
                return

            state = store.load()
            next_post_at = ui.input(
                "Next post at (YYYY-MM-DD HH:MM)",
                value=f"{state.next_post_at:{_DT_FORMAT}}"
                if state.next_post_at
                else "",
            ).classes("w-96")

            def _save() -> None:
                raw = next_post_at.value.strip()
                if not raw:
                    ui.notify("Enter a date and time", color="negative")
                    return
                try:
                    parsed = datetime.strptime(raw, _DT_FORMAT)
                except ValueError:
                    ui.notify("Use date format YYYY-MM-DD HH:MM", color="negative")
                    return
                current = store.load()
                current.next_post_at = parsed
                store.save(current)
                ui.notify("Saved")

            ui.button("Save", on_click=_save)
