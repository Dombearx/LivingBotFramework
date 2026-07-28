from nicegui import ui

from livingbot.admin.context import AdminContext
from livingbot.admin.pages.layout import page_layout
from livingbot.commitments import Commitment, CommitmentStatus

STATUS_COLOR: dict[CommitmentStatus, str] = {
    "open": "orange",
    "fulfilled": "green",
    "dropped": "grey",
}


def register(context: AdminContext) -> None:
    store = context.commitment_store

    @ui.page("/promises")
    def promises_page() -> None:
        with page_layout("Promises"):
            commitments = store.load().entries
            open_count = sum(1 for c in commitments if c.status == "open")
            fulfilled_count = sum(1 for c in commitments if c.status == "fulfilled")
            dropped_count = sum(1 for c in commitments if c.status == "dropped")

            with ui.row().classes("gap-4"):
                ui.label(f"Open: {open_count}").classes("text-sm text-gray-500")
                ui.label(f"Fulfilled: {fulfilled_count}").classes(
                    "text-sm text-gray-500"
                )
                ui.label(f"Dropped: {dropped_count}").classes("text-sm text-gray-500")

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
                    f"To user {commitment.user_id} · channel {commitment.channel_id} "
                    f"· due {commitment.due_hint}"
                ).classes("text-sm text-gray-500")
                ui.label(f"Made at {commitment.made_at:%Y-%m-%d %H:%M}").classes(
                    "text-xs text-gray-400"
                )
                if commitment.nudged_at is not None:
                    ui.label(
                        f"Nudged at {commitment.nudged_at:%Y-%m-%d %H:%M}"
                    ).classes("text-xs text-gray-400")
                elif commitment.check_after is not None:
                    ui.label(
                        f"Next follow-up check after "
                        f"{commitment.check_after:%Y-%m-%d %H:%M}"
                    ).classes("text-xs text-gray-400")
            ui.badge(commitment.status, color=STATUS_COLOR[commitment.status])
