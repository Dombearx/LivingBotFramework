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
