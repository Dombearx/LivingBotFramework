from datetime import datetime
from typing import get_args

from nicegui import ui

from livingbot.admin.context import AdminContext
from livingbot.admin.pages.layout import page_layout
from livingbot.scheduled_posts import ScheduledPost, ScheduledPostStatus

STATUS_COLOR: dict[ScheduledPostStatus, str] = {
    "pending": "orange",
    "posted": "green",
    "cancelled": "grey",
}

STATUS_OPTIONS: list[str] = list(get_args(ScheduledPostStatus))
_DT_FORMAT = "%Y-%m-%d %H:%M"


def register(context: AdminContext) -> None:
    @ui.page("/scheduled-posts")
    def scheduled_posts_page() -> None:
        with page_layout("Scheduled Posts"):
            store = context.scheduled_post_store
            if store is None:
                ui.label("Scheduled posts are not available.")
                return

            ui.label(
                "Have Mugda post about a topic in her allowed channel at a given "
                "time. Checked once per life loop cycle, so it may fire a little "
                "after the time set here."
            ).classes("text-sm text-gray-500")
            ui.button("Schedule post", icon="add", on_click=lambda: _open_editor(None))

            @ui.refreshable
            def post_list() -> None:
                posts = store.load().entries
                if not posts:
                    ui.label("No posts scheduled yet.")
                    return

                for post in sorted(posts, key=lambda p: p.run_at):
                    _render_post(post)

            def _render_post(post: ScheduledPost) -> None:
                with ui.card().classes("w-full"):
                    with ui.row().classes("w-full items-center justify-between"):
                        with ui.column().classes("gap-0"):
                            ui.label(post.topic).classes("font-semibold")
                            ui.label(f"Run at {post.run_at:%Y-%m-%d %H:%M}").classes(
                                "text-sm text-gray-500"
                            )
                            if post.posted_at is not None:
                                ui.label(
                                    f"Posted at {post.posted_at:%Y-%m-%d %H:%M}"
                                ).classes("text-xs text-gray-400")
                        with ui.row().classes("items-center"):
                            ui.badge(post.status, color=STATUS_COLOR[post.status])
                            ui.button(
                                icon="edit", on_click=lambda p=post: _open_editor(p)
                            )
                            ui.button(
                                icon="delete",
                                color="red",
                                on_click=lambda p=post: _delete(p.id),
                            )

            def _delete(post_id: str) -> None:
                posts = store.load()
                posts.entries = [p for p in posts.entries if p.id != post_id]
                store.save(posts)
                ui.notify("Removed")
                post_list.refresh()

            def _open_editor(post: ScheduledPost | None) -> None:
                with ui.dialog() as dialog, ui.card().classes("w-96"):
                    ui.label("Edit post" if post else "Schedule post").classes(
                        "text-lg font-semibold"
                    )
                    topic = ui.input("Topic", value=post.topic if post else "").classes(
                        "w-full"
                    )
                    run_at = ui.input(
                        f"Run at ({_DT_FORMAT})",
                        value=post.run_at.strftime(_DT_FORMAT) if post else "",
                    ).classes("w-full")
                    status = ui.select(
                        STATUS_OPTIONS,
                        value=post.status if post else "pending",
                        label="Status",
                    ).classes("w-full")

                    def _save() -> None:
                        if not topic.value.strip():
                            ui.notify("Topic is required", color="negative")
                            return
                        try:
                            run_at_value = datetime.strptime(
                                run_at.value.strip(), _DT_FORMAT
                            )
                        except ValueError:
                            ui.notify(
                                f"Run at must match {_DT_FORMAT}", color="negative"
                            )
                            return
                        posts = store.load()
                        if post is None:
                            posts.entries.append(
                                ScheduledPost(
                                    topic=topic.value.strip(),
                                    run_at=run_at_value,
                                    status=status.value,
                                )
                            )
                        else:
                            for entry in posts.entries:
                                if entry.id == post.id:
                                    entry.topic = topic.value.strip()
                                    entry.run_at = run_at_value
                                    entry.status = status.value
                                    break
                        store.save(posts)
                        dialog.close()
                        ui.notify("Saved")
                        post_list.refresh()

                    with ui.row():
                        ui.button("Save", on_click=_save)
                        ui.button("Cancel", on_click=dialog.close).props("flat")
                dialog.open()

            post_list()
