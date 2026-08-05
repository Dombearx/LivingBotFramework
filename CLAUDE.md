# LivingBotFramework

## Project Overview

A Python framework built incrementally across multiple implementation steps.

## Development Philosophy

### Scope Discipline
- Implement **only** what the current step explicitly requests — nothing more.
- Do not add "nice to have" features, future-proofing, or speculative abstractions.
- Do not refactor code outside the scope of the current step.
- If something seems missing or wrong but is outside the current step, note it as a comment for the user rather than fixing it silently.

### Code Quality
- Prioritize **readability** first: clear naming, logical structure, obvious intent.
- Prioritize **maintainability**: prefer simple, flat code over clever abstractions.
- Prioritize **correctness**: no half-implemented features, no silent failures.
- Three similar lines is better than a premature abstraction.
- Only introduce an abstraction when it is required by the current step.

### Comments
- Write no comments by default.
- Add a comment only when the **why** is non-obvious: a hidden constraint, a subtle invariant, or a workaround for a specific bug.
- Never write comments that describe what the code does — well-named identifiers do that.

### Error Handling
- Only validate at system boundaries (user input, external APIs, file I/O).
- Do not add defensive checks for scenarios that cannot happen given internal invariants.
- Do not add fallbacks or retries unless the current step explicitly requires them.

### Testing
- **Never add or modify tests until the user has explicitly accepted the code changes.** Write tests only after the implementation is approved.
- Write tests only if the current step requests them.
- Tests must exercise real behaviour, not just satisfy coverage metrics.
- Use `pytest`.
- Test mechanisms, not permutations. Each test should verify a distinct code path or guard against a meaningful failure; if you can't articulate what specific behaviour would break if this test didn't exist, skip it.
- Mock external dependencies with `unittest.mock.patch`. Prefer the `@patch` decorator over `with patch(...)` context managers — it keeps mock setup out of the test body. Patch at the point of use, not at the point of definition.
- Every test function must have a descriptive name that states what behaviour it verifies: `test_<unit>_<condition>_<expected_result>`, e.g. `test_on_message_when_bot_mentioned_sends_response`.
- Each test function tests exactly one behaviour. Split tests that need multiple assertions to verify one logical outcome into separate functions.
- Arrange–Act–Assert: set up state, call the unit under test, then assert the outcome — in that order, with a blank line between each phase.
- Assert the exact value you expect — a test that only checks `result > 3` is a test that would pass for any answer except "wrong enough".
- Prefer testing observable outputs and side-effects (return values, calls on mocks) over testing internal state.

### Integration Tests

Tests under `tests/integration/` send real requests to the LLM. They cost money and
take minutes, and because the model is non-deterministic they fail intermittently
without anything being broken.

- **Never start an integration run on your own initiative — not the full suite, not a
  single group, not locally and not through GitHub Actions.** Every run needs the user
  to approve that specific run first. Propose it, say which group you would run and
  roughly what it costs and how long it takes, and then wait. Deciding a run is
  warranted is not the same as being allowed to start it.
- An approval covers the run it was given for. Wanting to re-check after a fix means
  asking again.
- Run only the group covering the code you changed — the workflow's `test_group` input
  exists for exactly this. `all` is never a default; it needs its own approval.
- A failure in a test unrelated to your change is not yours to chase. Report it and
  move on; do not re-run it hoping for green, and do not "fix" the assertion.
- Re-running a group you did change is fine when you are verifying a fix.

#### Running them via GitHub Actions

`OPENROUTER_API_KEY` is usually absent from the dev environment, in which case every
integration test skips itself and `uv run pytest tests/integration/` is a no-op. The
key does exist as a repository secret, so the way to actually run them is the
**Integration Tests** workflow (`.github/workflows/integration-tests.yml`).

- It is `workflow_dispatch` only — trigger it manually, against the branch you want
  tested, once the user has approved that run. The workflow file must exist on that
  branch, so push before triggering.
- Pass the `test_group` input to pick what runs; it defaults to `all`, which is the one
  value covered by the "ask first" rule above. The group names and the files each maps
  to are listed in the workflow itself — read them there rather than guessing.
- Watch the run and read its logs to get the result.

Reading the results — the two outputs are not equivalent:

- **Job logs** carry the console summary: pass/fail, duration, token counts and
  estimated cost per test. The model's actual replies appear only for tests that
  failed, inside the assertion message.
- **The run's Step Summary** carries the full detail — every agent call with its model,
  tools called and the text the model produced, passing or not. It is written to
  `GITHUB_STEP_SUMMARY` and is visible in the GitHub UI, but is not retrievable through
  the API, so an agent reading logs alone cannot see what the bot said on a passing
  test. When the point of the run is to inspect her voice rather than check assertions,
  say so instead of assuming a green run proves anything about tone.

## Python Conventions

- Python 3.14
- Use type hints on all function signatures.
- Use `pydantic` models for all structured data.
- Keep functions small and single-purpose.
- Prefer `pathlib.Path` over `os.path`.
- Use `logging` (not `print`) for diagnostic output in library code.
- Format and lint with `ruff`.

## Package Management

- Use `uv` for all package management tasks.
- Add dependencies with `uv add <package>`.
- Run scripts and tools with `uv run <command>`.
- Keep `pyproject.toml` as the single source of truth for dependencies.

## Project Structure

```
LivingBotFramework/
├── CLAUDE.md
├── pyproject.toml        # created when the project is initialised
├── src/
│   └── livingbot/        # main package
└── tests/
```

## Step-by-Step Implementation

Each step will be described in the task or issue. Before implementing:

1. Read the step description carefully.
2. Identify the minimal set of files and changes required.
3. Implement only those changes.
4. Verify the implementation matches the step description — no more, no less.
5. Commit with a clear message referencing the step.

## After Making Changes

After any code change, run in order:

1. **Format and lint**: `uv run ruff format . && uv run ruff check .`
2. **Tests**: `uv run pytest`

Both must pass before committing.

## Git Workflow

- Branch: `claude/create-claude-md-BvVMa` (active development branch)
- Commit messages: short imperative sentence describing what changed, e.g. `add basic bot runner scaffold`.
- Push after each completed step.
- Do not open a pull request unless explicitly asked.
