import inspect
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from pydantic_ai import Agent
from pydantic_ai.messages import ModelResponse, ToolCallPart

from livingbot import image
from livingbot.activity_notes import ActivityNotesStore
from livingbot.commitments import CommitmentStore
from livingbot.hobbies import HobbyStore
from livingbot.preferences import PreferenceStore
from livingbot.spending import SpendingStore
from livingbot.stories import StoryStore

# USD per million input/output tokens, matching the models in llm_config.
MODEL_PRICES_PER_MILLION: dict[str, tuple[float, float]] = {
    "openai/gpt-5.6-terra": (1.25, 7.50),
    "openai/gpt-5.6-luna": (0.50, 3.00),
    "openai/gpt-5.4-mini": (0.75, 4.50),
    "openai/gpt-5.4-nano": (0.20, 1.25),
    "openai/gpt-5-nano": (0.05, 0.40),
}

MAX_OUTPUT_SNIPPET = 300
MAX_FAILURE_SNIPPET = 700

# Images the tests generate are written here, then uploaded as a build artifact
# and pushed to IMAGE_BRANCH by the workflow.
IMAGE_DIR = Path(os.environ.get("INTEGRATION_IMAGE_DIR", "integration-images"))
# A step summary can only show an image it can fetch over https — GitHub's
# markdown sanitiser strips data: URIs — so the workflow publishes them to this
# orphan branch and the summary points at their raw URLs. It is force-pushed
# with only the current run's images, so links in older summaries stop
# resolving; the run's artifact is the durable copy.
IMAGE_BRANCH = "integration-images"


@dataclass
class GeneratedImage:
    filename: str
    caption: str


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
class ImageCall:
    endpoint: str
    duration: float
    cost: float | None


@dataclass
class TestRecord:
    nodeid: str
    description: str
    calls: list[AgentCall] = field(default_factory=list)
    image_calls: list[ImageCall] = field(default_factory=list)
    images: list[GeneratedImage] = field(default_factory=list)
    outcome: str = "not run"
    duration: float = 0.0
    failure: str = ""

    @property
    def llm_cost(self) -> float:
        return sum(call.cost or 0.0 for call in self.calls)

    @property
    def image_cost(self) -> float:
        return sum(call.cost or 0.0 for call in self.image_calls)

    @property
    def cost(self) -> float:
        return self.llm_cost + self.image_cost

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

    # Rendering costs real money on top of the tokens, and the image service
    # reports what each job actually cost, so this is measured rather than
    # estimated from a price table the way the model calls are.
    original_request_image = image._request_image

    async def recording_request_image(endpoint, payload):
        start = time.perf_counter()
        result = await original_request_image(endpoint, payload)
        record.image_calls.append(
            ImageCall(
                endpoint=endpoint,
                duration=time.perf_counter() - start,
                cost=result.get("cost"),
            )
        )
        return result

    monkeypatch.setattr(image, "_request_image", recording_request_image)
    yield


@pytest.fixture
def save_image(request):
    """Write a generated image out for review, and list it in the run's summary."""

    def save(name: str, image_bytes: bytes, caption: str) -> Path:
        IMAGE_DIR.mkdir(parents=True, exist_ok=True)
        filename = f"{name}.jpg"
        path = IMAGE_DIR / filename
        path.write_bytes(image_bytes)
        _records[request.node.nodeid].images.append(
            GeneratedImage(filename=filename, caption=caption)
        )
        return path

    return save


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
# Failures first: they are what a reader is looking for. Passing tests follow,
# in full, because a green run still has to be read when what is being checked
# is her voice or a picture rather than an assertion.
_OUTCOME_ORDER = {"failed": 0, "skipped": 1, "passed": 2}


def _for_review(records: list[TestRecord]) -> list[TestRecord]:
    return sorted(records, key=lambda r: _OUTCOME_ORDER.get(r.outcome, 3))


def _snippet(text: str) -> str:
    text = text.replace("\n", " ")
    if len(text) > MAX_OUTPUT_SNIPPET:
        return text[:MAX_OUTPUT_SNIPPET] + "…"
    return text


def _image_cost(call: ImageCall) -> str:
    return f"${call.cost:.4f}" if call.cost is not None else "cost not reported"


def _total_cost(records: list[TestRecord]) -> str:
    """Total spend, split when rendering contributed — the two differ by orders
    of magnitude, and a single number hides which one a run actually cost."""
    llm = sum(r.llm_cost for r in records)
    images = sum(r.image_cost for r in records)
    if not images:
        return f"~${llm:.4f}"
    return f"~${llm + images:.4f} (models ~${llm:.4f}, images ~${images:.4f})"


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
    for record in _for_review(records):
        icon = _OUTCOME_ICONS.get(record.outcome, "?")
        name = record.nodeid.split("::")[-1]
        tokens = sum(c.input_tokens + c.output_tokens for c in record.calls)
        tr.line("")
        tr.line(
            f"{icon} {name}  "
            f"[{record.duration:.1f}s, {len(record.calls)} LLM call(s), "
            f"{tokens} tokens, ~${record.cost:.4f}]"
        )
        if record.failure:
            tr.line(f"   why it failed: {record.failure}")
        for call in record.calls:
            tr.line(f"   {call.agent_name} said: {_snippet(call.output)}")
        for call in record.image_calls:
            tr.line(
                f"   rendered {call.endpoint} in {call.duration:.1f}s, "
                f"{_image_cost(call)}"
            )
        for generated in record.images:
            tr.line(f"   image: {generated.filename} — {generated.caption}")
    total_time = sum(r.duration for r in records)
    passed = sum(1 for r in records if r.outcome == "passed")
    tr.line("")
    tr.line(
        f"Total: {passed}/{len(records)} passed, {total_time:.1f}s, "
        f"{_total_cost(records)}"
    )
    generated = [image for record in records for image in record.images]
    if generated:
        tr.line(f"{len(generated)} image(s) written to {IMAGE_DIR}/")


def _markdown_summary(records: list[TestRecord]) -> str:
    lines = ["## Integration test summary", ""]
    passed = sum(1 for r in records if r.outcome == "passed")
    total_time = sum(r.duration for r in records)
    lines.append(
        f"**{passed}/{len(records)} passed** · "
        f"total {total_time:.1f}s · cost {_total_cost(records)}"
    )
    lines.append("")
    lines.append("| Test | Result | Time | LLM calls | Tokens (in/out) | Est. cost |")
    lines.append("| --- | --- | ---: | ---: | ---: | ---: |")
    for record in _for_review(records):
        icon = _OUTCOME_ICONS.get(record.outcome, "?")
        name = record.nodeid.split("::")[-1]
        tokens_in = sum(c.input_tokens for c in record.calls)
        tokens_out = sum(c.output_tokens for c in record.calls)
        lines.append(
            f"| `{name}` | {icon} {record.outcome} | {record.duration:.1f}s "
            f"| {len(record.calls)} | {tokens_in}/{tokens_out} | ${record.cost:.4f} |"
        )
    lines.append("")
    lines.extend(_markdown_images(records))
    failed = [r for r in records if r.outcome == "failed"]
    rest = [r for r in _for_review(records) if r.outcome != "failed"]
    if failed:
        lines.append("## Failed")
        lines.append("")
        for record in failed:
            lines.extend(_markdown_test_details(record))
    if rest:
        lines.append("## Passed")
        lines.append("")
        for record in rest:
            lines.extend(_markdown_test_details(record))
    return "\n".join(lines) + "\n"


def _image_url(filename: str) -> str | None:
    """Where the workflow will have published this image by the time anyone reads
    the summary. Nothing to point at outside Actions, where nobody publishes it."""
    repo = os.environ.get("GITHUB_REPOSITORY")
    run_id = os.environ.get("GITHUB_RUN_ID")
    if not repo or not run_id:
        return None
    return (
        f"https://raw.githubusercontent.com/{repo}/{IMAGE_BRANCH}"
        f"/runs/{run_id}/{filename}"
    )


def _markdown_images(records: list[TestRecord]) -> list[str]:
    images = [
        (record, image) for record in _for_review(records) for image in record.images
    ]
    if not images:
        return []
    lines = ["## Generated images", ""]
    for record, generated in images:
        name = record.nodeid.split("::")[-1]
        lines.append(f"**{generated.caption}** — `{generated.filename}`, from `{name}`")
        lines.append("")
        url = _image_url(generated.filename)
        if url:
            lines.append(f"![{generated.caption}]({url})")
            lines.append("")
    return lines


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
    for generated in record.images:
        lines.append(f"**Image:** `{generated.filename}` — {generated.caption}")
        lines.append("")
    for i, call in enumerate(record.image_calls, 1):
        lines.append(
            f"- Render {i}: `{call.endpoint}` — {call.duration:.1f}s, "
            f"{_image_cost(call)}"
        )
    for i, call in enumerate(record.calls, 1):
        cost = f"${call.cost:.4f}" if call.cost is not None else "unknown"
        lines.append(
            f"- Call {i}: `{call.agent_name}` ({call.model_name}) — "
            f"{call.duration:.1f}s, {call.input_tokens} in / {call.output_tokens} out "
            f"tokens, {cost}"
        )
        if call.tools_called:
            lines.append(f"  - Tools called: {', '.join(call.tools_called)}")
        lines.append(f"  - Output: {_snippet(call.output)}")
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


@pytest.fixture
def preference_store(tmp_path) -> PreferenceStore:
    return PreferenceStore(tmp_path / "preferences")


@pytest.fixture
def commitment_store(tmp_path) -> CommitmentStore:
    return CommitmentStore(tmp_path / "commitments")
