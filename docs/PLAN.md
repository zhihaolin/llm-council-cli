# LLM Council - Roadmap

## Current Status

| Version | Feature | Status |
|---------|---------|--------|
| v1.0 | CLI + TUI + Web UI | ✅ Complete |
| v1.1 | Web Search (Tool Calling) | ✅ Complete |
| v1.2 | Multi-Turn Debate Mode | ✅ Complete |
| v1.3 | Conversation History | 🔜 Next |
| v1.4 | File/Document Upload | Planned |
| v1.5 | Image Input (Multimodal) | Planned |

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

---

## Next Up

### v1.3: Conversation History

Multi-turn conversations in CLI.

```bash
llm-council query "Question"                    # New conversation
llm-council query "Follow-up" --continue        # Continue last
llm-council query "Question" --id <id>          # Resume specific
llm-council history                             # List conversations
```

**Key decisions:**
- Context includes Stage 3 only (not all stages)
- Shared storage with web UI (`data/conversations/`)
- Truncation: first message + last N exchanges

### v1.4: File/Document Upload

```bash
llm-council query --file ./code.py "Review this"
llm-council query --file ./report.pdf "Summarize"
```

**Supported:** `.txt`, `.md`, `.py`, `.json`, `.pdf`, `.docx`

### v1.5+: Future

| Version | Feature |
|---------|---------|
| v1.5 | Image input (multimodal) |
| v1.6 | Presets & profiles |
| v1.7 | Streaming responses |
| v1.8 | Code execution tool |
| v1.9 | Local models (Ollama) |

---

## Engineering Practices

### Implemented ✅

| Practice | Details |
|----------|---------|
| Async/Parallel | `asyncio.gather()` for concurrent API calls |
| Graceful Degradation | Continues if individual models fail |
| Test Suite | pytest + pytest-asyncio, 29 tests |
| Type Hints | Function signatures throughout |

### Planned for v1.3

| Practice | Details |
|----------|---------|
| TDD | Tests first for new features |
| Pydantic Models | `CouncilConfig`, `ModelResponse`, `DebateRound` |
| Config Extraction | YAML config with validation |
| Structured Logging | JSON logs with correlation IDs |

### Planned for v1.4+

| Practice | Details |
|----------|---------|
| CI/CD | GitHub Actions for tests + lint |
| Pre-commit Hooks | ruff/black formatting |
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
├── conftest.py              # Fixtures, mocks
├── test_ranking_parser.py   # 14 tests
├── test_debate.py           # 15 tests
└── integration/             # CLI tests (planned)
```

---

*Last updated: 2026-01-20*

For implementation details and session notes, see [DEVLOG.md](DEVLOG.md).
