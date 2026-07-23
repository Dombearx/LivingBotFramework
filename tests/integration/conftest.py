import inspect
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from pydantic_ai import Agent
from pydantic_ai.messages import ModelResponse, ToolCallPart

from livingbot.activity_notes import ActivityNotesStore
from livingbot.hobbies import HobbyStore
from livingbot.spending import SpendingStore
from livingbot.stories import StoryStore

# USD per million input/output tokens, matching the models in llm_config.
MODEL_PRICES_PER_MILLION: dict[str, tuple[float, float]] = {
    "openai/gpt-5.4-mini": (0.75, 4.50),
    "openai/gpt-5-nano": (0.05, 0.40),
}

MAX_OUTPUT_SNIPPET = 300
MAX_FAILURE_SNIPPET = 700


@dataclass
class AgentCall:
    agent_name: str
    model_name: str
    duration: float
    input_tokens: int
    output_tokens: int
    cost: float | None
    tools_called: list[str]
    output: str


@dataclass
class TestRecord:
    nodeid: str
    description: str
    calls: list[AgentCall] = field(default_factory=list)
    outcome: str = "not run"
    duration: float = 0.0
    failure: str = ""

    @property
    def cost(self) -> float:
        return sum(call.cost or 0.0 for call in self.calls)

    @property
    def llm_time(self) -> float:
        return sum(call.duration for call in self.calls)


_records: dict[str, TestRecord] = {}


def _estimate_cost(
    model_name: str, input_tokens: int, output_tokens: int
) -> float | None:
    prices = MODEL_PRICES_PER_MILLION.get(model_name)
    if prices is None:
        return None
    input_price, output_price = prices
    return (input_tokens * input_price + output_tokens * output_price) / 1_000_000


def _tools_called(result) -> list[str]:
    tools: list[str] = []
    for message in result.all_messages():
        if isinstance(message, ModelResponse):
            for part in message.parts:
                if isinstance(part, ToolCallPart):
                    tools.append(part.tool_name)
    return tools


@pytest.fixture(autouse=True)
def record_agent_calls(request, monkeypatch):
    record = TestRecord(
        nodeid=request.node.nodeid,
        description=inspect.getdoc(request.function) or "",
    )
    _records[request.node.nodeid] = record
    original_run = Agent.run

    async def recording_run(self, *args, **kwargs):
        start = time.perf_counter()
        result = await original_run(self, *args, **kwargs)
        duration = time.perf_counter() - start
        usage = result.usage
        model_name = getattr(self.model, "model_name", str(self.model))
        record.calls.append(
            AgentCall(
                agent_name=self.name or model_name,
                model_name=model_name,
                duration=duration,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                cost=_estimate_cost(
                    model_name, usage.input_tokens, usage.output_tokens
                ),
                tools_called=_tools_called(result),
                output=str(result.output),
            )
        )
        return result

    monkeypatch.setattr(Agent, "run", recording_run)
    yield


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if report.when != "call":
        return
    record = _records.get(item.nodeid)
    if record is None:
        return
    record.outcome = report.outcome
    record.duration = report.duration
    if report.failed:
        record.failure = _failure_snippet(report.longreprtext)


def _failure_snippet(longrepr: str) -> str:
    # The assertion message (after "AssertionError:") carries the expected-vs-got
    # explanation the tests write; fall back to the tail of the traceback.
    marker = "AssertionError: "
    index = longrepr.rfind(marker)
    text = (
        longrepr[index + len(marker) :]
        if index != -1
        else longrepr[-MAX_FAILURE_SNIPPET:]
    )
    return text[:MAX_FAILURE_SNIPPET]


_OUTCOME_ICONS = {"passed": "✅", "failed": "❌", "skipped": "⏭️"}


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    records = [r for r in _records.values() if r.outcome != "not run"]
    if not records:
        return
    _write_console_summary(terminalreporter, records)
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with Path(summary_path).open("a", encoding="utf-8") as f:
            f.write(_markdown_summary(records))


def _write_console_summary(terminalreporter, records: list[TestRecord]) -> None:
    tr = terminalreporter
    tr.section("integration test summary")
    for record in records:
        icon = _OUTCOME_ICONS.get(record.outcome, "?")
        name = record.nodeid.split("::")[-1]
        tokens = sum(c.input_tokens + c.output_tokens for c in record.calls)
        tr.line(
            f"{icon} {name}  "
            f"[{record.duration:.1f}s, {len(record.calls)} LLM call(s), "
            f"{tokens} tokens, ~${record.cost:.4f}]"
        )
        if record.failure:
            tr.line(f"   failed: {record.failure}")
    total_cost = sum(r.cost for r in records)
    total_time = sum(r.duration for r in records)
    tr.line(f"Total: {len(records)} tests, {total_time:.1f}s, ~${total_cost:.4f}")


def _markdown_summary(records: list[TestRecord]) -> str:
    lines = ["## Integration test summary", ""]
    passed = sum(1 for r in records if r.outcome == "passed")
    total_cost = sum(r.cost for r in records)
    total_time = sum(r.duration for r in records)
    lines.append(
        f"**{passed}/{len(records)} passed** · "
        f"total {total_time:.1f}s · estimated cost ~${total_cost:.4f}"
    )
    lines.append("")
    lines.append("| Test | Result | Time | LLM calls | Tokens (in/out) | Est. cost |")
    lines.append("| --- | --- | ---: | ---: | ---: | ---: |")
    for record in records:
        icon = _OUTCOME_ICONS.get(record.outcome, "?")
        name = record.nodeid.split("::")[-1]
        tokens_in = sum(c.input_tokens for c in record.calls)
        tokens_out = sum(c.output_tokens for c in record.calls)
        lines.append(
            f"| `{name}` | {icon} {record.outcome} | {record.duration:.1f}s "
            f"| {len(record.calls)} | {tokens_in}/{tokens_out} | ${record.cost:.4f} |"
        )
    lines.append("")
    for record in records:
        lines.extend(_markdown_test_details(record))
    return "\n".join(lines) + "\n"


def _markdown_test_details(record: TestRecord) -> list[str]:
    icon = _OUTCOME_ICONS.get(record.outcome, "?")
    name = record.nodeid.split("::")[-1]
    lines = [f"### {icon} `{name}`", ""]
    if record.description:
        lines.append(f"**What was tested:** {record.description}")
        lines.append("")
    if record.failure:
        lines.append(f"**Why it failed:** {record.failure}")
        lines.append("")
    for i, call in enumerate(record.calls, 1):
        cost = f"${call.cost:.4f}" if call.cost is not None else "unknown"
        lines.append(
            f"- Call {i}: `{call.agent_name}` ({call.model_name}) — "
            f"{call.duration:.1f}s, {call.input_tokens} in / {call.output_tokens} out "
            f"tokens, {cost}"
        )
        if call.tools_called:
            lines.append(f"  - Tools called: {', '.join(call.tools_called)}")
        output = call.output.replace("\n", " ")
        if len(output) > MAX_OUTPUT_SNIPPET:
            output = output[:MAX_OUTPUT_SNIPPET] + "…"
        lines.append(f"  - Output: {output}")
    lines.append("")
    return lines


@pytest.fixture
def activity_notes_store(tmp_path) -> ActivityNotesStore:
    return ActivityNotesStore(tmp_path / "activity_notes")


@pytest.fixture
def spending_store(tmp_path) -> SpendingStore:
    return SpendingStore(tmp_path / "spending")


@pytest.fixture
def hobby_store(tmp_path) -> HobbyStore:
    return HobbyStore(tmp_path / "hobbies", default_hobbies=[])


@pytest.fixture
def story_store(tmp_path) -> StoryStore:
    return StoryStore.create(tmp_path / "stories")
