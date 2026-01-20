# AGENTS

Repo engineering practices and preferences.

## Development model
- Trunk-based development; direct pushes to `master` are OK; keep changes small.

## TDD
- Tests-first for behavior changes (features/bug fixes).
- Refactors can rely on existing tests; add characterization tests if behavior is unclear.
- Prefer deterministic tests; mock external services.

## Tests and CI
- CI gate is pytest passing.
- Run locally:
  - `uv run pytest tests/ -v`
  - `uv run pytest tests/ --cov=backend --cov-report=term-missing` (as needed)
- Integration tests in CI must mock OpenRouter/Tavily; live API tests should be scheduled separately.

## Tooling
- Python lint/format: Ruff + `ruff format`.
- Type checking: Pyright, `typeCheckingMode = "basic"`, `pythonVersion = "3.10"`, scope all code.
- Keep tooling gentle; ask before enforcing lint/type checks in CI.

## Architecture
- SOLID/DI refactor is planned; do not introduce DI unless requested.
