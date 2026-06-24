from nicegui import ui

from livingbot.admin.context import AdminContext
from livingbot.admin.pages.layout import page_layout


def register(context: AdminContext) -> None:
    store = context.mood_store

    @ui.page("/mood")
    def mood_page() -> None:
        with page_layout("Mood"):
            mood = store.load()

            ui.label("Mood value (0–100)")
            value = (
                ui.slider(min=0, max=100, value=round(mood.value))
                .props("label-always")
                .classes("w-96")
            )

            ui.label(f"Fatigue: {mood.fatigue:.1f}").classes("text-sm text-gray-500")
            ui.label(f"Last sleep date: {mood.last_sleep_date or '—'}").classes(
                "text-sm text-gray-500"
            )
            ui.label(f"Last gym boost: {mood.last_gym_boost_at or '—'}").classes(
                "text-sm text-gray-500"
            )
            ui.label(f"Last refreshed: {mood.last_refreshed_at or '—'}").classes(
                "text-sm text-gray-500"
            )

            def _save() -> None:
                current = store.load()
                current.value = float(value.value)
                store.save(current)
                ui.notify("Saved")

            ui.button("Save", on_click=_save)
