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
| v1.6 | ReAct Chairman | ✅ Complete |
| v1.6.1 | SOLID Refactoring | ✅ Complete |
| v1.6.2 | CI Quality Gates | ✅ Complete |
| v1.6.3 | Docker Support | ✅ Complete |
| v1.7 | File/Document Upload | Planned |
| v1.8 | Strategy Pattern (OCP/DIP) | Planned |
| v1.9 | Self-Reflection Round | Planned |
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
- `--parallel` / `-p` flag for debate mode
- `/parallel on|off` command in chat REPL (default: on)
- `asyncio.as_completed()` for parallel execution within rounds
- Rich Spinner widgets for animated progress indicators
- Per-model timeout with `asyncio.wait_for()` (default: 120s)
- Shared `httpx.AsyncClient` for connection reuse
- Performance: total time = max(model times) instead of sum

### v1.6: ReAct Chairman
- Chairman uses ReAct pattern: Reason → Act → Observe → Repeat
- `search_web` tool to verify facts during synthesis
- Max 3 iterations to prevent infinite loops
- Enabled by default for both ranking and debate modes
- `/react on|off` command in chat REPL
- `--no-react` flag to disable in CLI
- Works with parallel and streaming modes
- Color-coded trace display (Thought=cyan, Action=yellow, Observation=dim)

---

## Next Up

### v1.7: File/Document Upload

Attach files for the council to review.

```bash
llm-council query --file ./code.py "Review this code"
llm-council query --file ./report.pdf "Summarize the key findings"
llm-council query --file ./data.csv --file ./schema.json "Validate this data"
```

**Supported formats:**
- Text: `.txt`, `.md`, `.py`, `.js`, `.json`, `.yaml`, `.csv`
- Documents: `.pdf` (via `pypdf`), `.docx` (via `python-docx`)

**Implementation:**
- File content prepended to user query
- Large files truncated with warning
- Multiple `--file` flags supported

### v1.8: Strategy Pattern (OCP/DIP)

Apply Open/Closed and Dependency Inversion principles for extensibility.

**Features:**
- Strategy pattern for round types (initial, critique, defense, reflection)
- Dependency injection for model querier (testable, swappable)
- Registry pattern for adding new round types without modifying existing code

**Implementation:**
- `RoundStrategy` abstract base class with `execute()` and `build_prompt()` methods
- `InitialRound`, `CritiqueRound`, `DefenseRound` strategy classes
- `ROUND_STRATEGIES` registry dict for round type lookup
- `ModelQuerier` protocol for dependency injection
- Functions accept `models` and `querier` as parameters with defaults

**Benefits:**
- Add new round types by creating new classes (no modification to existing code)
- Easy to test with mock queriers
- Swap OpenRouter for Ollama by injecting different querier

### v1.9: Self-Reflection Round

Models evaluate and improve their own outputs before peer review.

**Features:**
- New round type: `reflection`
- Each model critiques its OWN previous response
- Outputs: identified weaknesses + improved response
- Inserted after Round 1 (initial) when enabled

**Flow with reflection:**
```
Round 1: Initial → Round 1.5: Self-Reflection → Round 2: Critique → Round 3: Defense
```

**Implementation:**
- `ReflectionRound` strategy class (builds on v1.8 strategy pattern)
- Prompt: "Review your response. Identify weaknesses. Provide an improved version."
- `--reflect` flag to enable
- Reflection visible in output as separate round

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

User control during autonomous execution via optional async callbacks. All three features use callbacks passed from CLI → runners → backend, defaulting to `None` (auto-pilot, fully backward compatible). Absorbs planned v1.17 "Configurable council" (`--models` part).

**Prerequisites:** v1.7-v1.10 completed (v1.8 Strategy Pattern in particular introduces `models` parameter and DI patterns that make threading callbacks cleaner).

**New type definitions** in `backend/council/types.py`:
```python
ToolApprovalCallback = Callable[[str, dict[str, Any]], Awaitable[bool]]
RoundInterventionCallback = Callable[[int, str, list[dict[str, Any]]], Awaitable[str | None]]
```

#### Feature 1: Tool Call Approval

Before executing `search_web`, prompt user to approve/reject.

- **Gate location:** `openrouter.py:query_model_with_tools()` and `query_model_streaming_with_tools()` — before `result = await tool_executor(...)`
- **Behavior:** `tool_approval: ToolApprovalCallback | None = None` param. When present, await before execution. If rejected, insert `"Tool call rejected by user."` as tool result.
- **CLI:** `--approve` flag on `query`; `/approve on|off` in chat REPL

#### Feature 2: Debate Intervention

Between rounds, let user inject their perspective into the next round's prompt.

- **Pause location:** `streaming.py` — after `round_complete` yield, before next round. `debate.py` — after each round completes.
- **Behavior:** `round_intervention: RoundInterventionCallback | None = None` param. After each round, await callback. If returns a string, prepend to next round's prompt via `inject_human_perspective()` in `prompts.py`. If returns `None`, continue normally.
- **CLI:** `--intervene` flag on `query`; `/intervene on|off` in chat REPL

#### Feature 3: Model Selection

Let user choose which models participate (absorbs v1.17 "Configurable council").

- **Current state:** `COUNCIL_MODELS` is a module-level constant used directly in `streaming.py` (7 refs) and `debate.py` (1 ref).
- **Change:** Add `models: list[str] | None = None` parameter to all debate/streaming functions. Default to `COUNCIL_MODELS` when `None`.
- **CLI:** `--select-models` (interactive picker); `--models "model-a,model-b"` (explicit); `/select` in chat REPL (minimum 2 models enforced)

#### Commit Sequence

| # | Scope | Files |
|---|-------|-------|
| 1 | HITL callback type definitions | `backend/council/types.py`, `__init__.py`, `tests/test_hitl_types.py` |
| 2-3 | `tool_approval` in openrouter | `backend/openrouter.py`, `tests/test_tool_approval.py` |
| 4 | Thread `tool_approval` through streaming/debate | `backend/council/streaming.py`, `backend/council/debate.py` |
| 5 | `inject_human_perspective` prompt | `backend/council/prompts.py`, `tests/test_hitl_intervention.py` |
| 6-7 | Thread `round_intervention` into streaming/debate | `backend/council/streaming.py`, `backend/council/debate.py` |
| 8-9 | `models` parameter in debate/streaming | `backend/council/debate.py`, `backend/council/streaming.py`, `tests/test_model_selection.py` |
| 10-11 | CLI prompt functions + callback wiring | `cli/runners.py` |
| 12 | Chat commands (`/approve`, `/intervene`, `/select`) | `cli/chat.py`, `cli/chat_session.py`, `cli/presenters.py` |
| 13 | CLI flags (`--approve`, `--intervene`, `--select-models`, `--models`) | `cli/main.py` |

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
| Off-by-one in tool call loops | `openrouter.py:198` vs `:372` | Medium | Align both to `range(max_tool_calls)` — the `+1` appears to be a bug |
| `datetime.utcnow()` deprecated | `storage.py:36` | Low | Replace with `datetime.now(datetime.UTC)` |
| Hardcoded title gen model | `orchestrator.py:206` | Medium | Add `title_model` to config.yaml; default to cheap/fast model |
| Redundant import | `openrouter.py:455` | Trivial | Delete the inner `import asyncio` |
| Shared HTTP client unused | `openrouter.py:21-52` | Low | Either use it in all query functions or delete it (YAGNI) |

**Note:** Several other issues (duplicated `execute_tool`, feature asymmetry, storage inefficiency, logging) are addressed by planned versions:
- v1.8 Strategy Pattern fixes round duplication and feature asymmetry
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
| Test Suite | pytest + pytest-asyncio, 84 tests |
| Linting | Ruff check + format in CI |
| Type Checking | Pyright in basic mode |
| Type Hints | Function signatures throughout |
| CI/CD | GitHub Actions (lint → test → docker pipeline) |
| SOLID (SRP/ISP) | Focused modules, clean API exports (v1.6.1) |
| Config Extraction | YAML config file (`config.yaml`) |

### Planned

| Practice | Details | Roadmap |
|----------|---------|---------|
| SOLID (OCP/DIP) | Strategy pattern, dependency injection | v1.8 |
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
├── test_chat_commands.py        # 10 tests
├── test_cli_imports.py          # 1 test
├── test_conversation_context.py # 5 tests
├── test_debate.py               # 15 tests
├── test_ranking_parser.py       # 14 tests
├── test_react.py                # 11 tests
├── test_search.py               # 17 tests
├── test_streaming.py            # 10 tests
└── integration/                 # CLI tests (planned)
```

---

*Last updated: 2026-02-10*

For implementation details and session notes, see [DEVLOG.md](DEVLOG.md).
