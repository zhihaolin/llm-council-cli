# LLM Council - Roadmap

## Current Status

| Version | Feature | Status |
|---------|---------|--------|
| v1.0 | CLI + TUI + Web UI | ✅ Complete |
| v1.1 | Web Search (Tool Calling) | ✅ Complete |
| v1.2 | Multi-Turn Debate Mode | ✅ Complete |
| v1.3 | Interactive Chat with History | ✅ Complete |
| v1.4 | Token Streaming | ✅ Complete |
| v1.5 | File/Document Upload | Planned |
| v1.6 | Image Input (Multimodal) | Planned |

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

---

## Next Up

### v1.5: File/Document Upload

```bash
llm-council query --file ./code.py "Review this"
llm-council query --file ./report.pdf "Summarize"
```

**Supported:** `.txt`, `.md`, `.py`, `.json`, `.pdf`, `.docx`

### v1.6+: Future

| Version | Feature |
|---------|---------|
| v1.6 | Image input (multimodal) |
| v1.7 | Presets & profiles |
| v1.8 | Code execution tool |
| v1.9 | Local models (Ollama) |
| v2.0 | Docker packaging (for web UI) |

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
