from nicegui import ui

from livingbot.admin.context import AdminContext
from livingbot.admin.pages.layout import page_layout
from livingbot.relations import Relation


def register(context: AdminContext) -> None:
    store = context.relation_store

    @ui.page("/relations")
    def relations_page() -> None:
        with page_layout("Relations"):

            @ui.refreshable
            def relation_list() -> None:
                relations = store.all()
                if not relations:
                    ui.label("No relations tracked yet.")
                    return
                for relation in relations:
                    _render_relation(relation)

            def _render_relation(relation: Relation) -> None:
                with ui.card().classes("w-full"):
                    with ui.row().classes("w-full items-center justify-between"):
                        with ui.column().classes("gap-0"):
                            ui.label(f"User {relation.user_id}").classes(
                                "font-semibold"
                            )
                            ui.label(f"Attitude: {relation.attitude}/100").classes(
                                "text-sm text-gray-500"
                            )
                            if relation.most_important_memory:
                                ui.label(relation.most_important_memory).classes(
                                    "text-sm text-gray-500"
                                )
                            if relation.inside_jokes:
                                ui.label(
                                    "Jokes: " + ", ".join(relation.inside_jokes)
                                ).classes("text-xs text-gray-400")
                            if relation.topics_of_interest:
                                ui.label(
                                    "Topics: " + ", ".join(relation.topics_of_interest)
                                ).classes("text-xs text-gray-400")
                        ui.button(
                            icon="edit", on_click=lambda r=relation: _open_editor(r)
                        )

            def _open_editor(relation: Relation) -> None:
                with ui.dialog() as dialog, ui.card().classes("w-[32rem]"):
                    ui.label(f"Edit relation · user {relation.user_id}").classes(
                        "text-lg font-semibold"
                    )
                    attitude = ui.number(
                        "Attitude (-100 to 100)",
                        value=relation.attitude,
                        min=-100,
                        max=100,
                    ).classes("w-full")
                    memory = ui.textarea(
                        "Most important memory (max 200 chars)",
                        value=relation.most_important_memory,
                    ).classes("w-full")
                    jokes = ui.textarea(
                        "Inside jokes (one per line, max 5)",
                        value="\n".join(relation.inside_jokes),
                    ).classes("w-full")
                    topics = ui.textarea(
                        "Topics of interest (one per line, max 5)",
                        value="\n".join(relation.topics_of_interest),
                    ).classes("w-full")

                    def _save() -> None:
                        joke_lines = [
                            j.strip() for j in jokes.value.splitlines() if j.strip()
                        ]
                        topic_lines = [
                            t.strip() for t in topics.value.splitlines() if t.strip()
                        ]
                        try:
                            saved = relation.model_copy(
                                update={
                                    "attitude": int(attitude.value or 0),
                                    "most_important_memory": memory.value.strip(),
                                    "inside_jokes": joke_lines,
                                    "topics_of_interest": topic_lines,
                                }
                            )
                            Relation.model_validate(saved.model_dump())
                        except Exception as error:
                            ui.notify(f"Invalid: {error}", color="negative")
                            return
                        store.save(saved)
                        dialog.close()
                        ui.notify("Saved")
                        relation_list.refresh()

                    with ui.row():
                        ui.button("Save", on_click=_save)
                        ui.button("Cancel", on_click=dialog.close).props("flat")
                dialog.open()

            relation_list()
