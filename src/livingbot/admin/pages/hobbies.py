from nicegui import ui

from livingbot.admin.context import AdminContext
from livingbot.admin.pages.layout import page_layout
from livingbot.hobbies import Hobby, HobbyLevel


def register(context: AdminContext) -> None:
    store = context.hobby_store

    @ui.page("/hobbies")
    def hobbies_page() -> None:
        with page_layout("Hobbies"):
            ui.button("Add hobby", icon="add", on_click=lambda: _open_editor(None))

            @ui.refreshable
            def hobby_list() -> None:
                entries = store.load().entries
                if not entries:
                    ui.label("No hobbies.")
                    return
                for hobby in entries:
                    _render_hobby(hobby)

            def _render_hobby(hobby: Hobby) -> None:
                with ui.card().classes("w-full"):
                    with ui.row().classes("w-full items-center justify-between"):
                        with ui.column().classes("gap-0"):
                            ui.label(hobby.name).classes("font-semibold")
                            ui.label(
                                f"{hobby.level.value} · {hobby.experience} xp"
                            ).classes("text-sm text-gray-500")
                        with ui.row():
                            ui.button(
                                icon="edit", on_click=lambda h=hobby: _open_editor(h)
                            )
                            ui.button(
                                icon="delete",
                                color="red",
                                on_click=lambda h=hobby: _delete(h.name),
                            )

            def _delete(name: str) -> None:
                hobbies = store.load()
                hobbies.entries = [h for h in hobbies.entries if h.name != name]
                store.save(hobbies)
                ui.notify("Removed")
                hobby_list.refresh()

            def _open_editor(hobby: Hobby | None) -> None:
                with ui.dialog() as dialog, ui.card().classes("w-96"):
                    ui.label("Edit hobby" if hobby else "Add hobby").classes(
                        "text-lg font-semibold"
                    )
                    name = ui.input("Name", value=hobby.name if hobby else "").classes(
                        "w-full"
                    )
                    if hobby is not None:
                        name.props("readonly")
                    level = ui.select(
                        [level.value for level in HobbyLevel],
                        value=hobby.level.value if hobby else HobbyLevel.novice.value,
                        label="Level",
                    ).classes("w-full")
                    experience = ui.number(
                        "Experience", value=hobby.experience if hobby else 0, min=0
                    ).classes("w-full")

                    def _save() -> None:
                        if not name.value.strip():
                            ui.notify("Name is required", color="negative")
                            return
                        hobbies = store.load()
                        if hobby is None and any(
                            h.name == name.value.strip() for h in hobbies.entries
                        ):
                            ui.notify("Hobby already exists", color="negative")
                            return
                        hobbies.entries = [
                            h for h in hobbies.entries if h.name != name.value.strip()
                        ]
                        hobbies.entries.append(
                            Hobby(
                                name=name.value.strip(),
                                level=HobbyLevel(level.value),
                                experience=int(experience.value or 0),
                            )
                        )
                        store.save(hobbies)
                        dialog.close()
                        ui.notify("Saved")
                        hobby_list.refresh()

                    with ui.row():
                        ui.button("Save", on_click=_save)
                        ui.button("Cancel", on_click=dialog.close).props("flat")
                dialog.open()

            hobby_list()
