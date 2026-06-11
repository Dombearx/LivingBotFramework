from nicegui import ui

from livingbot.admin.context import AdminContext
from livingbot.admin.pages.layout import page_layout
from livingbot.spending import Purchase, SpendCategory


def register(context: AdminContext) -> None:
    store = context.spending_store

    @ui.page("/spending")
    def spending_page() -> None:
        with page_layout("Spending"):
            state = store.load()
            ui.label(f"Week starting {state.week_start}")

            points = ui.number(
                "Points available", value=state.points_available, min=0
            ).classes("w-64")

            def _save_points() -> None:
                current = store.load()
                current.points_available = int(points.value or 0)
                store.save(current)
                ui.notify("Saved")

            ui.button("Save points", on_click=_save_points)

            ui.separator()
            ui.label("Purchases this week").classes("text-lg font-semibold")
            ui.button("Add purchase", icon="add", on_click=lambda: _open_editor())

            @ui.refreshable
            def purchase_list() -> None:
                purchases = store.load().purchases
                if not purchases:
                    ui.label("No purchases.")
                    return
                for index, purchase in enumerate(purchases):
                    _render_purchase(index, purchase)

            def _render_purchase(index: int, purchase: Purchase) -> None:
                with ui.card().classes("w-full"):
                    with ui.row().classes("w-full items-center justify-between"):
                        ui.label(
                            f"{purchase.name} ({purchase.category.value}) "
                            f"· {purchase.bought_at:%Y-%m-%d}"
                        )
                        ui.button(
                            icon="delete",
                            color="red",
                            on_click=lambda i=index: _delete(i),
                        )

            def _delete(index: int) -> None:
                current = store.load()
                del current.purchases[index]
                store.save(current)
                ui.notify("Removed")
                purchase_list.refresh()

            def _open_editor() -> None:
                with ui.dialog() as dialog, ui.card().classes("w-96"):
                    ui.label("Add purchase").classes("text-lg font-semibold")
                    name = ui.input("Name").classes("w-full")
                    category = ui.select(
                        [c.value for c in SpendCategory],
                        value=SpendCategory.small.value,
                        label="Category",
                    ).classes("w-full")

                    def _save() -> None:
                        if not name.value.strip():
                            ui.notify("Name is required", color="negative")
                            return
                        current = store.load()
                        current.purchases.append(
                            Purchase(
                                name=name.value.strip(),
                                category=SpendCategory(category.value),
                            )
                        )
                        store.save(current)
                        dialog.close()
                        ui.notify("Saved")
                        purchase_list.refresh()

                    with ui.row():
                        ui.button("Save", on_click=_save)
                        ui.button("Cancel", on_click=dialog.close).props("flat")
                dialog.open()

            purchase_list()
