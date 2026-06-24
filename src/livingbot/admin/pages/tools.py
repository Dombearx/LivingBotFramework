import base64
import inspect
from datetime import datetime
from enum import Enum
from types import SimpleNamespace
from typing import Any, Callable, cast, get_type_hints

import discord
from nicegui import ui
from nicegui.elements.mixins.value_element import ValueElement

from livingbot.admin.context import AdminContext
from livingbot.admin.pages.layout import page_layout
from livingbot.bot import LivingBot
from livingbot.tools import (
    BotDeps,
    add_hobby,
    add_item,
    add_plan,
    buy_item,
    check_budget,
    load_context,
    mark_story_told,
    recall_story,
    remove_item,
    remove_plan,
    search_inventory,
    show_story_image,
    take_photo,
)

_TOOL_FUNCTIONS: list[Callable[..., Any]] = [
    load_context,
    add_plan,
    remove_plan,
    add_item,
    remove_item,
    search_inventory,
    add_hobby,
    recall_story,
    mark_story_told,
    show_story_image,
    check_budget,
    buy_item,
    take_photo,
]

TOOLS: dict[str, Callable[..., Any]] = {func.__name__: func for func in _TOOL_FUNCTIONS}

CHANNEL_TOOLS = {"load_context"}
_DT_FORMAT = "%Y-%m-%d %H:%M"


def register(context: AdminContext) -> None:
    @ui.page("/tools")
    def tools_page() -> None:
        with page_layout("Tools"):
            bot = context.bot
            channel_options = _text_channels(bot)

            ui.label(
                "Run a tool against the live stores. Effects are real — items added "
                "here are really added."
            ).classes("text-sm text-gray-500")

            channel_select = ui.select(
                channel_options or {0: "no channels (bot not ready)"},
                label="Channel (only used by load_context)",
            ).classes("w-96")
            tool_select = ui.select(
                list(TOOLS), value="add_item", label="Tool"
            ).classes("w-96")

            form_area = ui.column().classes("w-96")
            result_area = ui.column().classes("w-full")
            getters: dict[str, Callable[[], object]] = {}

            def build_form() -> None:
                form_area.clear()
                getters.clear()
                func = TOOLS[tool_select.value]
                hints = get_type_hints(func)
                params = list(inspect.signature(func).parameters.items())[1:]
                with form_area:
                    ui.label(inspect.getdoc(func) or "").classes(
                        "text-xs text-gray-500 whitespace-pre-wrap"
                    )
                    for name, param in params:
                        annotation = hints.get(name, str)
                        getters[name] = _make_field(name, annotation, param.default)

            async def run_tool() -> None:
                result_area.clear()
                func = TOOLS[tool_select.value]
                try:
                    kwargs = {name: getter() for name, getter in getters.items()}
                except Exception as error:
                    ui.notify(f"Invalid input: {error}", color="negative")
                    return
                channel = None
                if tool_select.value in CHANNEL_TOOLS and channel_select.value:
                    channel = bot.get_channel(int(channel_select.value))
                deps = BotDeps(
                    channel=cast("discord.abc.Messageable", channel),
                    calendar_store=context.calendar_store,
                    inventory_store=context.inventory_store,
                    spending_store=context.spending_store,
                    hobby_store=context.hobby_store,
                    story_store=context.story_store,
                )
                ctx = SimpleNamespace(deps=deps)
                with result_area:
                    try:
                        output = await func(ctx, **kwargs)
                    except Exception as error:
                        ui.label(f"Error: {error}").classes("text-red-600")
                        return
                    ui.label("Result").classes("font-semibold")
                    ui.label(str(output)).classes("whitespace-pre-wrap")
                    if deps.photo_result:
                        encoded = base64.b64encode(deps.photo_result).decode()
                        ui.image(f"data:image/jpeg;base64,{encoded}").classes("w-80")

            tool_select.on("update:model-value", lambda: build_form())
            ui.button("Run", icon="play_arrow", on_click=run_tool)
            build_form()


def _make_field(name: str, annotation: object, default: object) -> Callable[[], object]:
    has_default = default is not inspect.Parameter.empty

    widget: ValueElement[Any]
    if annotation is bool:
        widget = ui.checkbox(name, value=bool(default) if has_default else False)
        return lambda: widget.value

    if isinstance(annotation, type) and issubclass(annotation, Enum):
        options = [member.value for member in annotation]
        value = default.value if isinstance(default, Enum) else options[0]
        widget = ui.select(options, value=value, label=name).classes("w-full")
        return lambda: annotation(widget.value)

    if annotation is int:
        widget = ui.number(
            name, value=cast(float, default) if has_default else 0
        ).classes("w-full")
        return lambda: int(widget.value)

    if annotation is datetime:
        widget = ui.input(f"{name} ({_DT_FORMAT})").classes("w-full")
        return lambda: datetime.strptime(widget.value.strip(), _DT_FORMAT)

    widget = ui.input(name, value=str(default) if has_default else "").classes("w-full")
    return lambda: widget.value


def _text_channels(bot: LivingBot) -> dict[int, str]:
    if not bot.is_ready():
        return {}
    return {
        channel.id: f"{guild.name} #{channel.name}"
        for guild in bot.guilds
        for channel in guild.text_channels
    }
