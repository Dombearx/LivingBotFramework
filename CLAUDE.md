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
- Write tests only if the current step requests them.
- Tests must exercise real behaviour, not just satisfy coverage metrics.

## Python Conventions

- Python 3.11+
- Use type hints on all function signatures.
- Use `dataclasses` or `pydantic` models for structured data (choose one per step, stay consistent).
- Keep functions small and single-purpose.
- Prefer `pathlib.Path` over `os.path`.
- Use `logging` (not `print`) for diagnostic output in library code.
- Format with `black`, lint with `ruff`.

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

## Git Workflow

- Branch: `claude/create-claude-md-BvVMa` (active development branch)
- Commit messages: short imperative sentence describing what changed, e.g. `add basic bot runner scaffold`.
- Push after each completed step.
- Do not open a pull request unless explicitly asked.
