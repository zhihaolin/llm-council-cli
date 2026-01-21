# LLM Council - Roadmap

## Current Status

| Version | Feature | Status |
|---------|---------|--------|
| v1.0 | CLI + TUI + Web UI | ✅ Complete |
| v1.1 | Web Search (Tool Calling) | ✅ Complete |
| v1.2 | Multi-Turn Debate Mode | ✅ Complete |
| v1.3 | Interactive Chat with History | ✅ Complete |
| v1.4 | Token Streaming | ✅ Complete |
| v1.5 | Parallel Execution with Progress | Planned |
| v1.6 | Retry & Fallback Logic | Planned |
| v1.7 | File/Document Upload | Planned |
| v1.8 | Cost Tracking | Planned |
| v1.9 | Export Conversations | Planned |
| v1.10 | Configurable Council | Planned |

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

### v1.8: Cost Tracking

Show estimated API cost per query using OpenRouter pricing data.

```bash
llm-council query "Question"
# ... response ...
# 💰 Estimated cost: $0.0234 (3 models × 3 rounds)
```

**Features:**
- Per-model token counting
- Real-time pricing from OpenRouter API
- Session cost accumulator
- `/cost` command in chat REPL

### v1.9: Export Conversations

Save conversations to various formats.

```bash
/export conversation.md    # Markdown
/export conversation.json  # Raw JSON
/export conversation.pdf   # PDF (requires weasyprint)
```

### v1.10: Configurable Council

Select models per query instead of hardcoded config.

```bash
llm-council query --models gpt-4o,claude-3,gemini "Question"
llm-council query --preset fast      # gpt-4o-mini × 3
llm-council query --preset thorough  # gpt-4o, claude-3-opus, gemini-pro
```

### v1.11+: Future

| Version | Feature |
|---------|---------|
| v1.11 | Image input (multimodal) |
| v1.12 | Web UI streaming |
| v1.13 | Code execution tool |
| v1.14 | Local models (Ollama) |
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
