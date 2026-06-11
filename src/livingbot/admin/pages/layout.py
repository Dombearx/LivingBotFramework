from contextlib import contextmanager
from collections.abc import Iterator

from nicegui import ui

NAV: list[tuple[str, str]] = [
    ("/", "Overview"),
    ("/inventory", "Inventory"),
    ("/stories", "Stories"),
    ("/memories", "Memories"),
    ("/calendar", "Calendar"),
    ("/hobbies", "Hobbies"),
    ("/spending", "Spending"),
    ("/mood", "Mood"),
    ("/relations", "Relations"),
    ("/tools", "Tools"),
]


@contextmanager
def page_layout(title: str) -> Iterator[None]:
    with ui.header().classes("items-center gap-4"):
        ui.label("Mugda admin").classes("text-lg font-bold")
        for path, label in NAV:
            ui.link(label, path).classes("text-white no-underline")
    with ui.column().classes("w-full max-w-5xl mx-auto p-4 gap-4"):
        ui.label(title).classes("text-2xl font-bold")
        yield
