# LLM Council - Roadmap

## Current Status

| Version | Feature | Status |
|---------|---------|--------|
| v1.0 | CLI + TUI + Web UI | ✅ Complete |
| v1.1 | Web Search (Tool Calling) | ✅ Complete |
| v1.2 | Multi-Turn Debate Mode | ✅ Complete |
| v1.3 | Interactive Chat with History | ✅ Complete |
| v1.4 | Token Streaming | ✅ Complete |
| v1.5 | Parallel Execution with Progress | ✅ Complete |
| v1.6 | Retry & Fallback Logic | Planned |
| v1.7 | File/Document Upload | Planned |
| v1.8 | Security Foundations | Planned |
| v1.9 | Observability | Planned |
| v1.10 | ReAct Chairman | Planned |
| v1.11 | Self-Reflection Round | Planned |
| v1.12 | Workflow State Machine | Planned |
| v1.13 | Tool Registry | Planned |

---

## Completed Features

### v1.0: Core Platform
- CLI with Typer + Rich (progress indicators, formatted output)
- Interactive TUI with Textual
- React web interface
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

---

## Next Up

### v1.5: Parallel Execution with Progress

Run all models in parallel within each round, showing live progress indicators.

```
━━━ ROUND 1: Initial Responses ━━━

gpt-4o-mini: ⠋ querying...
grok-3:      ⠋ querying...
deepseek:    ⠋ querying...

[grok-3 finishes first → panel appears]
[deepseek finishes → panel appears]
[gpt-4o-mini finishes → panel appears]
```

**Key changes:**
- `asyncio.as_completed()` for parallel execution
- Rich progress bars/spinners for each model
- Panels appear in completion order (fastest first)
- Applies to Round 1, 2, 3 (not chairman synthesis - single model)
- Per-model timeout with `asyncio.wait_for()` to prevent one model hanging forever
- Shared `httpx.AsyncClient` for connection reuse across all requests
- Optional `asyncio.Semaphore` if user configures many models (rate limit protection)

**Performance:** Total time = max(model times) instead of sum(model times)

### v1.6: Retry & Fallback Logic

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

### v1.8: Security Foundations

Minimum security layer to claim "end-to-end secure."

**Features:**
- API key authentication for web endpoints
- Input validation (query length limits, content filtering)
- Audit logging (who queried what, when, which models responded)
- Environment-based secrets (no hardcoded keys)

**Implementation:**
- FastAPI middleware for auth (`X-API-Key` header)
- Pydantic models for input validation
- Append-only audit log (JSON lines file)
- `AuditEntry`: timestamp, user_id, query_hash, models_used, latency_ms

### v1.9: Observability

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

### v1.10: ReAct Chairman

Chairman uses ReAct pattern: Reason → Act → Observe → Repeat.

**Features:**
- Chairman can call tools (search, re-query specific models)
- Reasoning loop: "Do I have enough info? No → search → synthesize"
- Max iterations limit (default: 3)
- Thought/Action/Observation trace visible in output

**Example output:**
```
Thought: The responses disagree on the 2024 election date. I should verify.
Action: search_web("2024 US presidential election date")
Observation: November 5, 2024
Thought: Now I can synthesize with the correct date.
Action: synthesize
```

**Implementation:**
- `synthesize_with_react()` replaces `stage3_synthesize_final()` when enabled
- Chairman prompt includes ReAct format instructions
- `--react` flag to enable (off by default for cost)

### v1.11: Self-Reflection Round

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
- `debate_round_reflection()` function
- Prompt: "Review your response. Identify weaknesses. Provide an improved version."
- `--reflect` flag to enable
- Reflection visible in output as separate round

### v1.12: Workflow State Machine

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

---

### v1.14+: Future

| Version | Feature |
|---------|---------|
| v1.14 | Cost tracking & token counting |
| v1.15 | Export conversations (MD/JSON/PDF) |
| v1.16 | Configurable council (`--models`, `--preset`) |
| v1.17 | Image input (multimodal) |
| v1.18 | Web UI streaming |
| v1.19 | Local models (Ollama) |
| v2.0 | Docker packaging |

---

## Engineering Practices

### Implemented ✅

| Practice | Details |
|----------|---------|
| Async/Parallel | `asyncio.gather()` for concurrent API calls |
| Graceful Degradation | Continues if individual models fail |
| Test Suite | pytest + pytest-asyncio, 70 tests |
| Type Hints | Function signatures throughout |
| CI/CD | GitHub Actions (tests on every push) |

### Planned

| Practice | Details |
|----------|---------|
| Pydantic Models | `CouncilConfig`, `ModelResponse`, `DebateRound` |
| Config Extraction | YAML config with validation |
| Structured Logging | JSON logs with correlation IDs |
| Contract Tests | Scheduled daily API schema validation |
| Pre-commit Hooks | Ruff lint/format |
| Type Checking | Pyright (basic) |
| Live API E2E Tests | Scheduled OpenRouter/Tavily tests; CI stays mocked |
| Custom Exceptions | `CouncilError`, `ModelTimeoutError` |
| Retry with Backoff | Exponential backoff for API failures |
| SOLID Refactor | Extract classes, dependency injection |

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
uv run pytest tests/ -v                    # Run all tests
uv run pytest tests/ --cov=backend         # With coverage
```

```
tests/
├── conftest.py                  # Fixtures, mocks
├── test_chat_commands.py        # 10 tests
├── test_cli_imports.py          # 1 test
├── test_conversation_context.py # 5 tests
├── test_debate.py               # 15 tests
├── test_ranking_parser.py       # 14 tests
├── test_search.py               # 17 tests
├── test_streaming.py            # 8 tests
└── integration/                 # CLI tests (planned)
```

---

*Last updated: 2026-01-21*

For implementation details and session notes, see [DEVLOG.md](DEVLOG.md).
