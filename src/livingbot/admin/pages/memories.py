from nicegui import ui

from livingbot.admin.context import AdminContext
from livingbot.admin.pages.layout import page_layout
from livingbot.memory import GLOBAL_USER_ID


def register(context: AdminContext) -> None:
    store = context.memory_store
    relation_store = context.relation_store

    @ui.page("/memories")
    async def memories() -> None:
        with page_layout("Memories"):
            user_ids = [GLOBAL_USER_ID] + [
                r.user_id for r in relation_store.all() if r.user_id != GLOBAL_USER_ID
            ]
            user_select = ui.select(
                user_ids, value=GLOBAL_USER_ID, label="Memory bank"
            ).classes("w-64")
            user_select.on("update:model-value", lambda: memory_list.refresh())

            @ui.refreshable
            async def memory_list() -> None:
                entries = await store.all(user_select.value)
                if not entries:
                    ui.label("No memories.")
                    return
                for entry in entries:
                    _render_memory(entry)

            def _render_memory(entry: dict) -> None:
                with ui.card().classes("w-full"):
                    with ui.row().classes("w-full items-center justify-between"):
                        ui.label(entry.get("memory", "")).classes("grow")
                        ui.button(
                            icon="delete",
                            color="red",
                            on_click=lambda e=entry: _delete(e["id"]),
                        )

            async def _delete(memory_id: str) -> None:
                await store.delete(memory_id)
                ui.notify("Removed")
                memory_list.refresh()

            await memory_list()
