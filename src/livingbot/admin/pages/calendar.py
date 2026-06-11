from datetime import datetime

from nicegui import ui

from livingbot.admin.context import AdminContext
from livingbot.admin.pages.layout import page_layout
from livingbot.calendar import PlanEntry

_DT_FORMAT = "%Y-%m-%d %H:%M"


def register(context: AdminContext) -> None:
    store = context.calendar_store

    @ui.page("/calendar")
    def calendar_page() -> None:
        with page_layout("Calendar"):
            calendar = store.load()
            ui.label(f"Home location: {calendar.home_location}")
            ui.button("Add entry", icon="add", on_click=lambda: _open_editor(None))

            @ui.refreshable
            def entry_list() -> None:
                entries = sorted(store.load().entries, key=lambda e: e.start)
                if not entries:
                    ui.label("No calendar entries.")
                    return
                for entry in entries:
                    _render_entry(entry)

            def _render_entry(entry: PlanEntry) -> None:
                with ui.card().classes("w-full"):
                    with ui.row().classes("w-full items-center justify-between"):
                        with ui.column().classes("gap-0"):
                            ui.label(f"{entry.activity} @ {entry.location}").classes(
                                "font-semibold"
                            )
                            ui.label(
                                f"{entry.start:{_DT_FORMAT}} → {entry.end:{_DT_FORMAT}}"
                            ).classes("text-sm text-gray-500")
                            meta = f"id:{entry.id}"
                            if entry.hobby:
                                meta += f" · hobby:{entry.hobby}"
                            if entry.note:
                                meta += f" · {entry.note}"
                            ui.label(meta).classes("text-xs text-gray-400")
                        with ui.row():
                            ui.button(
                                icon="edit", on_click=lambda e=entry: _open_editor(e)
                            )
                            ui.button(
                                icon="delete",
                                color="red",
                                on_click=lambda e=entry: _delete(e.id),
                            )

            def _delete(entry_id: str) -> None:
                calendar = store.load()
                calendar.entries = [e for e in calendar.entries if e.id != entry_id]
                store.save(calendar)
                ui.notify("Removed")
                entry_list.refresh()

            def _open_editor(entry: PlanEntry | None) -> None:
                with ui.dialog() as dialog, ui.card().classes("w-96"):
                    ui.label("Edit entry" if entry else "Add entry").classes(
                        "text-lg font-semibold"
                    )
                    activity = ui.input(
                        "Activity", value=entry.activity if entry else ""
                    ).classes("w-full")
                    location = ui.input(
                        "Location", value=entry.location if entry else ""
                    ).classes("w-full")
                    start = ui.input(
                        "Start (YYYY-MM-DD HH:MM)",
                        value=f"{entry.start:{_DT_FORMAT}}" if entry else "",
                    ).classes("w-full")
                    end = ui.input(
                        "End (YYYY-MM-DD HH:MM)",
                        value=f"{entry.end:{_DT_FORMAT}}" if entry else "",
                    ).classes("w-full")
                    note = ui.input("Note", value=entry.note if entry else "").classes(
                        "w-full"
                    )
                    hobby = ui.input(
                        "Hobby (exact name, optional)",
                        value=entry.hobby if entry else "",
                    ).classes("w-full")

                    def _save() -> None:
                        try:
                            start_dt = datetime.strptime(
                                start.value.strip(), _DT_FORMAT
                            )
                            end_dt = datetime.strptime(end.value.strip(), _DT_FORMAT)
                        except ValueError:
                            ui.notify(
                                "Use date format YYYY-MM-DD HH:MM", color="negative"
                            )
                            return
                        if not activity.value.strip() or not location.value.strip():
                            ui.notify(
                                "Activity and location are required", color="negative"
                            )
                            return
                        calendar = store.load()
                        if entry is not None:
                            calendar.entries = [
                                e for e in calendar.entries if e.id != entry.id
                            ]
                            saved = entry.model_copy(
                                update={
                                    "activity": activity.value.strip(),
                                    "location": location.value.strip(),
                                    "start": start_dt,
                                    "end": end_dt,
                                    "note": note.value.strip(),
                                    "hobby": hobby.value.strip(),
                                }
                            )
                        else:
                            saved = PlanEntry(
                                activity=activity.value.strip(),
                                location=location.value.strip(),
                                start=start_dt,
                                end=end_dt,
                                note=note.value.strip(),
                                hobby=hobby.value.strip(),
                            )
                        calendar.entries.append(saved)
                        store.save(calendar)
                        dialog.close()
                        ui.notify("Saved")
                        entry_list.refresh()

                    with ui.row():
                        ui.button("Save", on_click=_save)
                        ui.button("Cancel", on_click=dialog.close).props("flat")
                dialog.open()

            entry_list()
