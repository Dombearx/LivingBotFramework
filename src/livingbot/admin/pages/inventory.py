from nicegui import ui

from livingbot.admin.context import AdminContext
from livingbot.admin.pages.layout import page_layout
from livingbot.inventory import InventoryItem


def register(context: AdminContext) -> None:
    store = context.inventory_store

    @ui.page("/inventory")
    async def inventory() -> None:
        with page_layout("Inventory"):
            search_box = ui.input("Semantic search (blank lists all)").classes("w-full")
            search_box.on("keydown.enter", lambda: item_list.refresh())
            with ui.row():
                ui.button("Search", on_click=lambda: item_list.refresh())
                ui.button("Add item", icon="add", on_click=lambda: _open_editor(None))

            @ui.refreshable
            async def item_list() -> None:
                query = search_box.value.strip()
                items = (
                    await store.search(query, limit=20) if query else await store.all()
                )
                if not items:
                    ui.label("No items.")
                    return
                for item in items:
                    _render_item(item)

            def _render_item(item: InventoryItem) -> None:
                with ui.card().classes("w-full"):
                    with ui.row().classes("w-full items-center justify-between"):
                        with ui.column().classes("gap-0"):
                            ui.label(item.name).classes("font-semibold")
                            if item.description:
                                ui.label(item.description).classes(
                                    "text-sm text-gray-500"
                                )
                            ui.label(
                                f"id:{item.id} · acquired {item.acquired_at:%Y-%m-%d}"
                            ).classes("text-xs text-gray-400")
                        with ui.row():
                            ui.button(
                                icon="edit", on_click=lambda i=item: _open_editor(i)
                            )
                            ui.button(
                                icon="delete",
                                color="red",
                                on_click=lambda i=item: _delete(i.id),
                            )

            async def _delete(item_id: str) -> None:
                await store.remove(item_id)
                ui.notify("Removed")
                item_list.refresh()

            def _open_editor(item: InventoryItem | None) -> None:
                with ui.dialog() as dialog, ui.card().classes("w-96"):
                    ui.label("Edit item" if item else "Add item").classes(
                        "text-lg font-semibold"
                    )
                    name = ui.input("Name", value=item.name if item else "").classes(
                        "w-full"
                    )
                    description = ui.input(
                        "Description", value=item.description if item else ""
                    ).classes("w-full")

                    async def _save() -> None:
                        if not name.value.strip():
                            ui.notify("Name is required", color="negative")
                            return
                        if item is not None:
                            saved = item.model_copy(
                                update={
                                    "name": name.value.strip(),
                                    "description": description.value.strip(),
                                }
                            )
                        else:
                            saved = InventoryItem(
                                name=name.value.strip(),
                                description=description.value.strip(),
                            )
                        await store.add(saved)
                        dialog.close()
                        ui.notify("Saved")
                        item_list.refresh()

                    with ui.row():
                        ui.button("Save", on_click=_save)
                        ui.button("Cancel", on_click=dialog.close).props("flat")
                dialog.open()

            await item_list()
