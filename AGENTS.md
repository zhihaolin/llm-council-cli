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
  - `uv run pytest tests/ --cov=llm_council --cov-report=term-missing` (as needed)
- Integration tests in CI must mock OpenRouter/Tavily; live API tests should be scheduled separately.

## Tooling
- Python lint/format: Ruff + `ruff format`.
- Type checking: Pyright, `typeCheckingMode = "basic"`, `pythonVersion = "3.10"`, scope all code.
- Keep tooling gentle; ask before enforcing lint/type checks in CI.

## Architecture
- SOLID/DI refactor is planned; do not introduce DI unless requested.

## Known Tech Debt / Follow-ups (as of 2026-02-15)

### Already in the roadmap (`docs/PLAN.md`)
- v1.8 Strategy pattern: unify round behavior across implementations (streaming vs non-streaming drift).
- v1.11 Observability: replace `print()`-based error handling with structured logging/tracing.
- v1.12 Tool registry: dedupe tool plumbing (`execute_tool`, tool schemas) and centralize tool execution.
- v1.13 Retry & fallback: unify `httpx` client lifecycle + retries/backoff; harden tool-call argument parsing.
- v1.10 Workflow state machine: consider replacing/augmenting JSON storage (current storage is non-atomic/brittle).

### Not currently in the roadmap (bugs/UX cleanup)
- CLI `query --debate --stream/--parallel` skips ReAct (and effectively ignores `--simple`/`--final-only` expectations).
- Textual TUI doesn’t clear prior results; repeated queries accumulate widgets and reuse IDs; placeholder removal swallows exceptions.
- Import-time env coupling: `llm_council/settings.py` calls `load_dotenv()` at import; `llm_council/adapters/tavily_search.py` reads `TAVILY_API_KEY` once at import time.
- Type-hint mismatch: `llm_council/engine/parsers.py:parse_react_output()` returns `None`s but is typed as non-optional.
- Storage robustness: `list_conversations()` assumes all JSON files are valid; writes are not atomic.

### Dependency drift watchlist
- `pydantic` is a runtime dependency but currently unused; either remove until v1.14 (validation) lands or start using it deliberately.
