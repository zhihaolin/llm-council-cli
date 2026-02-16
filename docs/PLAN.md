# LLM Council - Roadmap

## Current Status

| Version | Feature | Status |
|---------|---------|--------|
| v1.0 | CLI + TUI | ✅ Complete |
| v1.1 | Web Search (Tool Calling) | ✅ Complete |
| v1.2 | Multi-Turn Debate Mode | ✅ Complete |
| v1.3 | Interactive Chat with History | ✅ Complete |
| v1.4 | Token Streaming | ✅ Complete |
| v1.5 | Parallel Execution with Progress | ✅ Complete |
| v1.6 | Tool Calling for Council | ✅ Complete |
| v1.6.1 | SOLID Refactoring | ✅ Complete |
| v1.6.2 | CI Quality Gates | ✅ Complete |
| v1.6.3 | Docker Support | ✅ Complete |
| v1.7 | Unify Debate Logic | ✅ Complete |
| v1.8 | Rename Debate Functions | ✅ Complete |
| v1.9 | Strategy Pattern (OCP/DIP) | ✅ Complete |
| — | Chairman Reflection | ✅ Complete |
| — | Council ReAct | ✅ Complete |
| — | Chat UI Improvements | ✅ Complete |
| — | Compact Chat Banner | ✅ Complete |
| v1.10 | Workflow State Machine | Planned |
| v1.11 | Human-in-the-Loop (HITL) | Planned |
| v1.12 | Observability | Planned |
| v1.13 | Tool Registry | Planned |
| v1.14 | Retry & Fallback Logic | Planned |
| v1.15 | Security Foundations | Planned |

---

## Completed Features

### v1.0: Core Platform
- CLI with Typer + Rich (progress indicators, formatted output)
- Interactive TUI with Textual
- 3-stage deliberation: responses → anonymous ranking → synthesis

### v1.1: Web Search
- Tavily API integration via OpenAI-style tool calling
- Models autonomously decide when to search
- `• searched` indicator in CLI output

### v1.2: Debate Mode
- `--debate` flag for multi-round deliberation
- Round 1: Initial responses → Round 2: Critiques → Round 3: Defense/Revision
- `--rounds N` for extended debates
- Chairman synthesizes full debate transcript

### v1.3: Interactive Chat with History
- `llm-council chat` interactive REPL with auto-resume
- Slash commands: `/history`, `/use <id>`, `/new`, `/debate on|off`, `/rounds N`, `/mode`, `/exit`
- Context includes Stage 3 only (first message + last N exchanges)
- Shared storage with web UI (`data/conversations/`)
- `--new` flag to start fresh, `--max-turns` to control context window

### v1.4: Token Streaming
- Token-by-token streaming in debate mode
- `/stream on|off` command in chat REPL
- Streaming enabled by default with debate mode
- Dimmed text while streaming, replaced with rendered markdown panel on completion
- Terminal line-wrap tracking for clean output clearing
- Streaming with tool calling support (`query_model_streaming_with_tools`)
- Web search enabled in defense round (Round 3) for evidence gathering

### v1.5: Parallel Execution with Progress
- Parallel is now the default debate execution mode (no flag needed)
- `asyncio.as_completed()` for parallel execution within rounds
- Rich Spinner widgets for animated progress indicators
- Per-model timeout with `asyncio.wait_for()` (default: 120s)
- Performance: total time = max(model times) instead of sum

### v1.6: Tool Calling for Council
- *(Originally included ReAct chairman — superseded by Reflection, see Post-v1.9)*
- Tavily web search via OpenAI-style tool calling for council members
- `/react on|off` command in chat REPL
- `--no-react` flag to disable in CLI
- Works with parallel and streaming modes

### v1.7: Unify Debate Logic
- Extracted shared per-round query functions
- Fixed Round 3 (defense) tool asymmetry: all modes now use `query_model_with_tools()`
- Consistent web search availability in Rounds 1 and 3 across all modes

### v1.8: Rename Debate Functions for Clarity
- Consolidated into single `debate.py` (removed `debate_async.py`)
- `debate_round_parallel()` (runs models in parallel with events)
- `debate_round_streaming()` (sequential with per-token events)
- `run_debate_parallel()` / `run_debate_streaming()` in CLI runners

### v1.9: Consolidate Round-Sequencing with Strategy Pattern
- Single `run_debate()` orchestrator defines round sequence once (initial → critique → defense → extra rounds)
- Strategy pattern: `execute_round` callback plugs in execution strategy
- Two executors: `debate_round_parallel()` (parallel with per-model events) and `debate_round_streaming()` (sequential with per-token events)
- `run_debate_parallel()` and `run_debate_streaming()` simplified to delegate to `run_debate()`
- `run_debate_with_progress()` rewritten to consume `run_debate` events
- Removed `run_debate_council()` (dead code, unused by CLI)
- Removed nested generators `stream_initial_round_with_tools()` and `stream_round()`
- Net reduction: ~400 lines of duplicated round-sequencing logic

### Post-v1.9: Chairman Reflection
- Chairman uses Reflection for synthesis (always on, replaces ReAct for chairman)
- Single streaming call with deep analysis before `## Synthesis` header
- `synthesize_with_reflection()` in `engine/reflection.py`

### Post-v1.9: Council ReAct
- Council members use text-based ReAct (Thought → Action → Observation) for visible reasoning
- `council_react_loop()` in `engine/react.py`
- Controlled by `--no-react` / `/react on|off` (enabled by default)
- Applied to tool-enabled rounds only (initial, defense)

### Post-v1.9: Chat UI Improvements
- Simplified prompt: always `council>` instead of mode-specific prompts
- Commands grouped by function in banner
- Model panels show `[reasoned]` and `[searched]` indicators
- Chairman headers changed to "CHAIRMAN'S REFLECTION"

### Post-v1.9: Compact Chat Banner
- Replaced Panel-based banner with compact text framed by horizontal rules
- Dot-delimited mode line: `Debate · 1 round · React on · Stream off`
- Improved indicator visibility (no longer dim)

---

## Next Up

### v1.10: Workflow State Machine

Formal state management with checkpoints for reliability.

**Features:**
- Defined states: `pending → querying → ranking → synthesizing → complete → failed`
- Checkpoint after each stage (can resume on failure)
- Workflow runs stored in SQLite (not just JSON files)
- `--resume <run-id>` to continue interrupted runs

**State transitions:**
```
pending ──→ querying ──→ ranking ──→ synthesizing ──→ complete
    │           │           │             │
    └───────────┴───────────┴─────────────┴──→ failed
```

**Implementation:**
- `WorkflowState` enum + `WorkflowRun` Pydantic model
- SQLite table: `workflow_runs(id, state, query, checkpoint_data, created_at, updated_at)`
- `checkpoint_data` stores serialized round results
- On resume: load checkpoint, skip completed stages

### v1.11: Human-in-the-Loop (HITL)

User control during autonomous execution via optional async callbacks. All three features use callbacks passed from CLI → runners → engine → adapters, defaulting to `None` (auto-pilot, fully backward compatible). Includes configurable council (`--models`).

**Prerequisites:** v1.7-v1.10 completed (v1.9 Strategy Pattern in particular introduces `models` parameter and DI patterns that make threading callbacks cleaner).

**New type definitions** in `llm_council/engine/types.py`:
```python
ToolApprovalCallback = Callable[[str, dict[str, Any]], Awaitable[bool]]
RoundInterventionCallback = Callable[[int, str, list[dict[str, Any]]], Awaitable[str | None]]
```

#### Feature 1: Tool Call Approval

Before executing `search_web`, prompt user to approve/reject.

- **Gate location:** `llm_council/adapters/openrouter_client.py:query_model_with_tools()` and `llm_council/adapters/openrouter_client.py:query_model_streaming_with_tools()` — before `result = await tool_executor(...)`
- **Behavior:** `tool_approval: ToolApprovalCallback | None = None` param. When present, await before execution. If rejected, insert `"Tool call rejected by user."` as tool result.
- **CLI:** `--approve` flag on `query`; `/approve on|off` in chat REPL

#### Feature 2: Debate Intervention

Between rounds, let user inject their perspective into the next round's prompt.

- **Pause location:** `llm_council/engine/debate.py` — after `round_complete` yield in `run_debate()`, before next round.
- **Behavior:** `round_intervention: RoundInterventionCallback | None = None` param. After each round, await callback. If returns a string, prepend to next round's prompt via `inject_human_perspective()` in `llm_council/engine/prompts.py`. If returns `None`, continue normally.
- **CLI:** `--intervene` flag on `query`; `/intervene on|off` in chat REPL

#### Feature 3: Model Selection

Let user choose which models participate.

- **Current state:** `COUNCIL_MODELS` (defined in `llm_council/settings.py`) is used directly in `llm_council/engine/ranking.py`, `llm_council/engine/debate.py`, `llm_council/cli/main.py`, and `llm_council/cli/runners.py`.
- **Change:** Add `models: list[str] | None = None` parameter to all debate/streaming functions. Default to `COUNCIL_MODELS` when `None`.
- **CLI:** `--select-models` (interactive picker); `--models "model-a,model-b"` (explicit); `/select` in chat REPL (minimum 2 models enforced)

#### Commit Sequence

| # | Scope | Files |
|---|-------|-------|
| 1 | HITL callback type definitions | `llm_council/engine/types.py`, `llm_council/engine/__init__.py`, `tests/test_hitl_types.py` |
| 2-3 | `tool_approval` in openrouter | `llm_council/adapters/openrouter_client.py`, `tests/test_tool_approval.py` |
| 4 | Thread `tool_approval` through debate | `llm_council/engine/debate.py` |
| 5 | `inject_human_perspective` prompt | `llm_council/engine/prompts.py`, `tests/test_hitl_intervention.py` |
| 6-7 | Thread `round_intervention` into debate | `llm_council/engine/debate.py` |
| 8-9 | `models` parameter in debate | `llm_council/engine/debate.py`, `tests/test_model_selection.py` |
| 10-11 | CLI prompt functions + callback wiring | `llm_council/cli/runners.py` |
| 12 | Chat commands (`/approve`, `/intervene`, `/select`) | `llm_council/cli/chat_commands.py`, `llm_council/cli/chat_session.py`, `llm_council/cli/presenters.py` |
| 13 | CLI flags (`--approve`, `--intervene`, `--select-models`, `--models`) | `llm_council/cli/main.py` |

#### Risks

| Risk | Mitigation |
|------|------------|
| `console.input()` blocks event loop | Prompts fire between async operations, not during token streaming |
| Chat `/select` vs existing `models` command | `/select` in chat, `models` stays as top-level Typer command |
| Rejected tool calls confuse LLM | Return "rejected by user" as tool result — LLM answers from knowledge |
| < 2 models selected | Enforce minimum 2 in selection prompt |

### v1.12: Observability

Structured logging and tracing for production visibility.

**Features:**
- Structured JSON logging with correlation IDs
- OpenTelemetry tracing (spans per round, per model)
- Basic metrics: request count, latency p50/p95, error rate
- `/metrics` endpoint (Prometheus format)

**Implementation:**
- `structlog` for JSON logging
- `opentelemetry-sdk` + `opentelemetry-exporter-otlp` for tracing
- Correlation ID generated per request, flows through all logs
- Spans: `council.query` → `council.round.{n}` → `council.model.{name}`

### v1.13: Tool Registry

Pluggable tools with registration protocol for extensibility.

**Features:**
- Tool registry: `register_tool(name, schema, handler)`
- Built-in tools: `search_web`, `read_file`, `execute_code`
- Tools described to models dynamically based on registry
- MCP-compatible tool definitions (Model Context Protocol)

**Example:**
```python
@tool_registry.register(
    name="read_file",
    description="Read contents of a file",
    parameters={"path": {"type": "string", "description": "File path"}}
)
async def read_file(path: str) -> str:
    return Path(path).read_text()
```

**Implementation:**
- `ToolRegistry` class with `register()`, `list_tools()`, `execute()`
- Tools auto-converted to OpenAI function-calling format
- `ENABLED_TOOLS` config to control which tools models can use
- Sandboxed execution for `execute_code` (subprocess with timeout)

### v1.14: Retry & Fallback Logic

Graceful handling of API failures with automatic recovery.

**Failure modes addressed:**

| Category | Failure | Solution |
|----------|---------|----------|
| Network | OpenRouter down | Retry with exponential backoff (1s → 2s → 4s) |
| Network | Rate limit (429) | Detect status code, backoff, retry |
| Network | Timeout | Per-model timeout, retry once |
| Network | Partial stream | Detect incomplete response, retry |
| Model | Unavailable | Fallback to alternate model |
| Model | Empty response | Retry once, then skip |
| Model | Context overflow | Truncate input, warn user |
| Tool | Tavily down | Graceful "search unavailable" message |
| Quorum | 2 of 3 fail | Continue with 1 + warning |
| Quorum | All fail | Clear error message, no empty response |

**Implementation:**
- Shared `httpx.AsyncClient` with configured limits
- `max_retries=3` with exponential backoff
- Model fallback map: `{"gpt-4o-mini": "gpt-4o", "grok-3": "grok-2"}`
- Minimum quorum setting (default: 1 model required)

**Custom exceptions:**
- `ModelTimeoutError` - Model exceeded time limit
- `ModelRateLimitError` - Hit rate limits, backoff required
- `CouncilQuorumError` - Too few models responded

### v1.15: Security Foundations

Minimum security layer for CLI usage.

**Features:**
- Input validation (query length limits, content filtering)
- Audit logging (queries, models used, timestamps)
- Environment-based secrets (no hardcoded keys) ✅ already done
- File upload sandboxing (for v1.7)

**Implementation:**
- Pydantic models for input validation
- Append-only audit log (JSON lines file)
- `AuditEntry`: timestamp, query_hash, models_used, latency_ms
- File path validation (no traversal attacks)

---

### v1.16+: Future

| Version | Feature |
|---------|---------|
| v1.16 | Cost tracking & token counting |
| v1.17 | Export conversations (MD/JSON/PDF) |
| v1.18 | Image input (multimodal) |
| v1.19 | Local models (Ollama) |

---

## Technical Debt

Issues not tied to a specific version. Fix opportunistically or when touching related code.

| Issue | Location | Severity | Fix Strategy |
|-------|----------|----------|--------------|
| Off-by-one in tool call loops | `llm_council/adapters/openrouter_client.py` | Medium | Align both to `range(max_tool_calls)` — the `+1` appears to be a bug |
| `datetime.utcnow()` deprecated | `llm_council/adapters/json_storage.py` | Low | Replace with `datetime.now(datetime.UTC)` |
| Hardcoded title gen model | `llm_council/engine/ranking.py` | Medium | Add `title_model` to config.yaml; default to cheap/fast model |
| Redundant import | `llm_council/adapters/openrouter_client.py` | Trivial | Delete the inner `import asyncio` |
| Shared HTTP client unused | `llm_council/adapters/openrouter_client.py` | Low | Either use it in all query functions or delete it (YAGNI) |

**Note:** Several other issues (duplicated `execute_tool`, storage inefficiency, logging) are addressed by planned versions:
- v1.10 Workflow State Machine replaces JSON storage with SQLite
- v1.12 Observability adds structured logging
- v1.13 Tool Registry centralizes `execute_tool`
- v1.14 Retry & Fallback will use the shared client

---

## Engineering Practices

### Implemented ✅

| Practice | Details |
|----------|---------|
| Async/Parallel | `asyncio.gather()` for concurrent API calls |
| Graceful Degradation | Continues if individual models fail |
| Test Suite | pytest + pytest-asyncio, 111 tests |
| Linting | Ruff check + format in CI |
| Type Checking | Pyright in basic mode |
| Type Hints | Function signatures throughout |
| CI/CD | GitHub Actions (lint → test → docker pipeline) |
| SOLID (SRP/ISP) | Focused modules, clean API exports (v1.6.1) |
| SOLID (OCP) | Strategy pattern for debate execution (v1.9) |
| Config Extraction | YAML config file (`config.yaml`) |
| Chairman Reflection | Deep analysis before synthesis (always on) |
| Council ReAct | Visible Thought→Action→Observation reasoning for council members |
| Compact Chat UI | Text-based banner with horizontal rules, dot-delimited mode line |

### Planned

| Practice | Details | Roadmap |
|----------|---------|---------|
| Pydantic Models | `CouncilConfig`, `ModelResponse`, `WorkflowRun` | v1.10, v1.14 |
| Structured Logging | JSON logs with correlation IDs | v1.12 |
| Custom Exceptions | `CouncilError`, `ModelTimeoutError`, `CouncilQuorumError` | v1.14 |
| Retry with Backoff | Exponential backoff for API failures | v1.14 |
| Contract Tests | Scheduled daily API schema validation | — |
| Pre-commit Hooks | Ruff as pre-commit hook | — |
| Live API E2E Tests | Scheduled OpenRouter/Tavily tests; CI stays mocked | — |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        User Query                            │
└─────────────────────────────────────────────────────────────┘
                             │
              ┌──────────────┴──────────────┐
              ▼                             ▼
┌──────────────────────┐      ┌──────────────────────┐
│    Standard Mode     │      │     Debate Mode      │
│                      │      │                      │
│  Stage 1: Responses  │      │  Round 1: Initial    │
│  Stage 2: Rankings   │      │  Round 2: Critique   │
│  Stage 3: Synthesis  │      │  Round 3: Defense    │
│                      │      │  Synthesis           │
└──────────────────────┘      └──────────────────────┘
              │                             │
              └──────────────┬──────────────┘
                             ▼
┌─────────────────────────────────────────────────────────────┐
│                   OpenRouter API                             │
│         (GPT, Claude, Gemini, Grok, DeepSeek)               │
│                                                              │
│    ┌─────────────────────────────────────────────────┐      │
│    │  Tool Calling: search_web() → Tavily API        │      │
│    └─────────────────────────────────────────────────┘      │
└─────────────────────────────────────────────────────────────┘
```

---

## Testing

```bash
uv run pytest tests/ -v
```

```
tests/
├── conftest.py                  # Fixtures, mocks
├── test_chat_commands.py        # 14 tests
├── test_cli_imports.py          # 1 test
├── test_conversation_context.py # 5 tests
├── test_debate.py               # 24 tests
├── test_ranking_parser.py       # 14 tests
├── test_react.py                # 12 tests
├── test_reflection.py           # 6 tests
├── test_search.py               # 18 tests
├── test_streaming.py            # 17 tests
└── integration/                 # CLI tests (planned)
```

---

*Last updated: 2026-02-16*

For implementation details and session notes, see [DEVLOG.md](DEVLOG.md).
