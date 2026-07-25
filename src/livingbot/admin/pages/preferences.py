from nicegui import ui

from livingbot.admin.context import AdminContext
from livingbot.admin.pages.layout import page_layout
from livingbot.preferences import Preference


def register(context: AdminContext) -> None:
    store = context.preference_store

    @ui.page("/preferences")
    def preferences_page() -> None:
        with page_layout("Preferences"):
            ui.button("Add preference", icon="add", on_click=lambda: _open_editor(None))

            @ui.refreshable
            def preference_list() -> None:
                entries = store.load().entries
                if not entries:
                    ui.label("No preferences settled yet.")
                    return
                for preference in entries:
                    _render_preference(preference)

            def _render_preference(preference: Preference) -> None:
                with ui.card().classes("w-full"):
                    with ui.row().classes("w-full items-center justify-between"):
                        with ui.column().classes("gap-0"):
                            ui.label(preference.topic).classes("font-semibold")
                            ui.label(preference.stance).classes("text-sm text-gray-500")
                            ui.label(
                                f"Since {preference.created_at:%Y-%m-%d %H:%M}"
                            ).classes("text-xs text-gray-400")
                        with ui.row():
                            ui.button(
                                icon="edit",
                                on_click=lambda p=preference: _open_editor(p),
                            )
                            ui.button(
                                icon="delete",
                                color="red",
                                on_click=lambda p=preference: _delete(p.id),
                            )

            def _delete(preference_id: str) -> None:
                preferences = store.load()
                preferences.entries = [
                    entry for entry in preferences.entries if entry.id != preference_id
                ]
                store.save(preferences)
                ui.notify("Removed")
                preference_list.refresh()

            def _open_editor(preference: Preference | None) -> None:
                with ui.dialog() as dialog, ui.card().classes("w-[32rem]"):
                    ui.label(
                        "Edit preference" if preference else "Add preference"
                    ).classes("text-lg font-semibold")
                    topic = ui.input(
                        "Topic", value=preference.topic if preference else ""
                    ).classes("w-full")
                    stance = ui.textarea(
                        "Stance", value=preference.stance if preference else ""
                    ).classes("w-full")

                    def _save() -> None:
                        if not topic.value.strip() or not stance.value.strip():
                            ui.notify("Topic and stance are required", color="negative")
                            return
                        preferences = store.load()
                        preferences.entries = [
                            entry
                            for entry in preferences.entries
                            if preference is None or entry.id != preference.id
                        ]
                        preferences.entries.append(
                            Preference(
                                topic=topic.value.strip(),
                                stance=stance.value.strip(),
                            )
                            if preference is None
                            else preference.model_copy(
                                update={
                                    "topic": topic.value.strip(),
                                    "stance": stance.value.strip(),
                                }
                            )
                        )
                        store.save(preferences)
                        dialog.close()
                        ui.notify("Saved")
                        preference_list.refresh()

                    with ui.row():
                        ui.button("Save", on_click=_save)
                        ui.button("Cancel", on_click=dialog.close).props("flat")
                dialog.open()

            preference_list()
