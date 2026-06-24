from pathlib import Path

from nicegui import app, ui

from livingbot import config
from livingbot.admin.context import AdminContext
from livingbot.admin.pages.layout import page_layout
from livingbot.stories import Story

_STATIC_PREFIX = "/story_images"


def register(context: AdminContext) -> None:
    store = context.story_store
    config.STORY_IMAGE_PATH.mkdir(parents=True, exist_ok=True)
    app.add_static_files(_STATIC_PREFIX, str(config.STORY_IMAGE_PATH))

    @ui.page("/stories")
    async def stories() -> None:
        with page_layout("Stories"):
            search_box = ui.input("Semantic search (blank lists all)").classes("w-full")
            search_box.on("keydown.enter", lambda: story_list.refresh())
            with ui.row():
                ui.button("Search", on_click=lambda: story_list.refresh())
                ui.button("Add story", icon="add", on_click=lambda: _open_editor(None))

            @ui.refreshable
            async def story_list() -> None:
                query = search_box.value.strip()
                items = (
                    await store.search(query, limit=20) if query else await store.all()
                )
                items.sort(key=lambda s: s.created_at, reverse=True)
                if not items:
                    ui.label("No stories.")
                    return
                for story in items:
                    _render_story(story)

            def _render_story(story: Story) -> None:
                with ui.card().classes("w-full"):
                    with ui.row().classes("w-full items-start justify-between"):
                        with ui.column().classes("gap-1 grow"):
                            ui.label(story.summary).classes("font-semibold")
                            ui.label(story.content).classes("text-sm text-gray-600")
                            status = "told" if story.told_at else "not told yet"
                            occurs = (
                                f"occurs {story.occurs_at:%Y-%m-%d %H:%M}"
                                if story.occurs_at
                                else "no date"
                            )
                            ui.label(f"id:{story.id} · {occurs} · {status}").classes(
                                "text-xs text-gray-400"
                            )
                            if story.image_path:
                                ui.image(
                                    f"{_STATIC_PREFIX}/{Path(story.image_path).name}"
                                ).classes("w-64")
                        with ui.column():
                            ui.button(
                                icon="edit", on_click=lambda s=story: _open_editor(s)
                            )
                            toggle_label = (
                                "Mark untold" if story.told_at else "Mark told"
                            )
                            ui.button(
                                toggle_label, on_click=lambda s=story: _toggle_told(s)
                            ).props("flat")
                            ui.button(
                                icon="delete",
                                color="red",
                                on_click=lambda s=story: _delete(s.id),
                            )

            async def _toggle_told(story: Story) -> None:
                from livingbot import clock

                updated = story.model_copy(
                    update={"told_at": None if story.told_at else clock.now()}
                )
                await store.add(updated)
                ui.notify("Updated")
                story_list.refresh()

            async def _delete(story_id: str) -> None:
                await store.remove(story_id)
                ui.notify("Removed")
                story_list.refresh()

            def _open_editor(story: Story | None) -> None:
                with ui.dialog() as dialog, ui.card().classes("w-[36rem]"):
                    ui.label("Edit story" if story else "Add story").classes(
                        "text-lg font-semibold"
                    )
                    summary = ui.input(
                        "Summary", value=story.summary if story else ""
                    ).classes("w-full")
                    content = ui.textarea(
                        "Content", value=story.content if story else ""
                    ).classes("w-full")

                    async def _save() -> None:
                        if not summary.value.strip() or not content.value.strip():
                            ui.notify(
                                "Summary and content are required", color="negative"
                            )
                            return
                        if story is not None:
                            saved = story.model_copy(
                                update={
                                    "summary": summary.value.strip(),
                                    "content": content.value.strip(),
                                }
                            )
                        else:
                            saved = Story(
                                summary=summary.value.strip(),
                                content=content.value.strip(),
                            )
                        await store.add(saved)
                        dialog.close()
                        ui.notify("Saved")
                        story_list.refresh()

                    with ui.row():
                        ui.button("Save", on_click=_save)
                        ui.button("Cancel", on_click=dialog.close).props("flat")
                dialog.open()

            await story_list()
