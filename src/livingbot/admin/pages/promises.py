from datetime import datetime
from typing import get_args

from nicegui import ui

from livingbot.admin.context import AdminContext
from livingbot.admin.pages.layout import page_layout
from livingbot.commitments import Commitment, CommitmentStatus

STATUS_COLOR: dict[CommitmentStatus, str] = {
    "open": "orange",
    "fulfilled": "green",
    "dropped": "grey",
}

STATUS_OPTIONS: list[str] = list(get_args(CommitmentStatus))


def register(context: AdminContext) -> None:
    store = context.commitment_store

    @ui.page("/promises")
    def promises_page() -> None:
        with page_layout("Promises"):
            ui.button("Add promise", icon="add", on_click=lambda: _open_editor(None))

            @ui.refreshable
            def promise_list() -> None:
                commitments = store.load().entries
                open_count = sum(1 for c in commitments if c.status == "open")
                fulfilled_count = sum(1 for c in commitments if c.status == "fulfilled")
                dropped_count = sum(1 for c in commitments if c.status == "dropped")

                with ui.row().classes("gap-4"):
                    ui.label(f"Open: {open_count}").classes("text-sm text-gray-500")
                    ui.label(f"Fulfilled: {fulfilled_count}").classes(
                        "text-sm text-gray-500"
                    )
                    ui.label(f"Dropped: {dropped_count}").classes(
                        "text-sm text-gray-500"
                    )

                if not commitments:
                    ui.label("No promises made yet.")
                    return

                for commitment in sorted(
                    commitments, key=lambda c: c.made_at, reverse=True
                ):
                    _render_commitment(commitment)

            def _render_commitment(commitment: Commitment) -> None:
                with ui.card().classes("w-full"):
                    with ui.row().classes("w-full items-center justify-between"):
                        with ui.column().classes("gap-0"):
                            ui.label(commitment.description).classes("font-semibold")
                            ui.label(
                                f"To user {commitment.user_id} · channel "
                                f"{commitment.channel_id} · due {commitment.due_hint}"
                            ).classes("text-sm text-gray-500")
                            ui.label(
                                f"Made at {commitment.made_at:%Y-%m-%d %H:%M}"
                            ).classes("text-xs text-gray-400")
                            if commitment.nudged_at is not None:
                                ui.label(
                                    f"Nudged at {commitment.nudged_at:%Y-%m-%d %H:%M}"
                                ).classes("text-xs text-gray-400")
                            elif commitment.check_after is not None:
                                ui.label(
                                    f"Next follow-up check after "
                                    f"{commitment.check_after:%Y-%m-%d %H:%M}"
                                ).classes("text-xs text-gray-400")
                        with ui.row().classes("items-center"):
                            ui.badge(
                                commitment.status, color=STATUS_COLOR[commitment.status]
                            )
                            ui.button(
                                icon="edit",
                                on_click=lambda c=commitment: _open_editor(c),
                            )
                            ui.button(
                                icon="delete",
                                color="red",
                                on_click=lambda c=commitment: _delete(c.id),
                            )

            def _delete(commitment_id: str) -> None:
                commitments = store.load()
                commitments.entries = [
                    c for c in commitments.entries if c.id != commitment_id
                ]
                store.save(commitments)
                ui.notify("Removed")
                promise_list.refresh()

            def _open_editor(commitment: Commitment | None) -> None:
                with ui.dialog() as dialog, ui.card().classes("w-96"):
                    ui.label("Edit promise" if commitment else "Add promise").classes(
                        "text-lg font-semibold"
                    )
                    description = ui.input(
                        "Description",
                        value=commitment.description if commitment else "",
                    ).classes("w-full")
                    user_id = ui.input(
                        "User ID", value=commitment.user_id if commitment else ""
                    ).classes("w-full")
                    channel_id = ui.number(
                        "Channel ID",
                        value=commitment.channel_id if commitment else 0,
                    ).classes("w-full")
                    due_hint = ui.input(
                        "Due hint", value=commitment.due_hint if commitment else ""
                    ).classes("w-full")
                    status = ui.select(
                        STATUS_OPTIONS,
                        value=commitment.status if commitment else "open",
                        label="Status",
                    ).classes("w-full")

                    def _save() -> None:
                        if not description.value.strip():
                            ui.notify("Description is required", color="negative")
                            return
                        if not user_id.value.strip():
                            ui.notify("User ID is required", color="negative")
                            return
                        commitments = store.load()
                        if commitment is None:
                            commitments.entries.append(
                                Commitment(
                                    user_id=user_id.value.strip(),
                                    channel_id=int(channel_id.value or 0),
                                    description=description.value.strip(),
                                    due_hint=due_hint.value.strip(),
                                    made_at=datetime.now(),
                                    status=status.value,
                                )
                            )
                        else:
                            for entry in commitments.entries:
                                if entry.id == commitment.id:
                                    entry.user_id = user_id.value.strip()
                                    entry.channel_id = int(channel_id.value or 0)
                                    entry.description = description.value.strip()
                                    entry.due_hint = due_hint.value.strip()
                                    entry.status = status.value
                                    break
                        store.save(commitments)
                        dialog.close()
                        ui.notify("Saved")
                        promise_list.refresh()

                    with ui.row():
                        ui.button("Save", on_click=_save)
                        ui.button("Cancel", on_click=dialog.close).props("flat")
                dialog.open()

            promise_list()
