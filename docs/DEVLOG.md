# Development Log

Technical decisions and implementation notes for LLM Council.

---

## v1.2: Multi-Turn Debate Mode
*January 2026*

### Overview
Implemented debate mode where models critique each other's positions and revise their answers before chairman synthesis.

### Implementation

**Backend (`backend/council.py`)** - Added 6 functions:

| Function | Purpose |
|----------|---------|
| `debate_round_critique()` | Each model critiques all others |
| `extract_critiques_for_model()` | Parse critiques for a specific model |
| `debate_round_defense()` | Models defend and revise positions |
| `parse_revised_answer()` | Extract "Revised Response" section |
| `synthesize_debate()` | Chairman synthesizes full debate |
| `run_debate_council()` | Orchestrate complete flow |

**CLI (`cli/main.py`)** - Added flags and display:
- `--debate` / `-d` flag
- `--rounds N` / `-r N` flag (default: 2)
- Color-coded round display (cyan/yellow/magenta)
- `• searched` indicator for web search

**Storage (`backend/storage.py`)** - New debate format:
```python
{"mode": "debate", "rounds": [...], "synthesis": {...}}
```

### Architecture
```
Round 1 (Initial)     Round 2 (Critique)     Round 3 (Defense)
┌─────────────────┐   ┌─────────────────┐   ┌─────────────────┐
│ Model A answers │   │ A critiques B,C │   │ A defends/revises│
│ Model B answers │ → │ B critiques A,C │ → │ B defends/revises│
│ Model C answers │   │ C critiques A,B │   │ C defends/revises│
└─────────────────┘   └─────────────────┘   └─────────────────┘
                                                    │
                                                    ▼
                                          ┌─────────────────┐
                                          │    Chairman     │
                                          │   Synthesizes   │
                                          └─────────────────┘
```

### Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Attribution | Named (not anonymous) | Track positions across rounds |
| Critique scope | All-to-all | Each model critiques all others |
| Defense format | Structured sections | Easy to parse revised answers |
| Default rounds | 2 | Sufficient for most questions |

### API Costs

| Mode | API Calls (5 models) |
|------|---------------------|
| Standard | 11 calls |
| Debate (2 rounds) | 16 calls |
| Debate (3 rounds) | 21 calls |

---

## Test Infrastructure
*January 2026*

### Overview
Set up pytest with async support and wrote tests for critical parsing logic.

### Implementation

```
tests/
├── conftest.py              # Fixtures, mock API responses
├── test_ranking_parser.py   # 14 tests
├── test_debate.py           # 15 tests
├── test_search.py           # 17 tests
└── integration/             # CLI tests (planned)
```

**Dependencies added:**
- `pytest>=8.0.0`
- `pytest-asyncio>=0.23.0`
- `pytest-cov>=4.1.0`

### Test Categories

| Category | Tests | Coverage |
|----------|-------|----------|
| Ranking parser | 14 | `parse_ranking_from_text`, `calculate_aggregate_rankings` |
| Debate mode | 15 | Critique extraction, defense parsing, async rounds |
| Web search | 17 | Tool calling, search_web, format_search_results |

**Results:** 46 passed (focused on critical parsing and tool calling logic)

---

## v1.1: Web Search Integration
*January 2026*

### Overview
Integrated Tavily API with OpenAI-style tool calling. Models autonomously decide when to search.

### Implementation

**New file `backend/search.py`:**
- `SEARCH_TOOL` - Function calling definition
- `search_web()` - Async Tavily API wrapper
- `format_search_results()` - Format for LLM context

**Modified `backend/openrouter.py`:**
- `query_model_with_tools()` - Handle tool call loop
- `max_tool_calls` parameter to prevent infinite loops

**Modified `backend/council.py`:**
- `execute_tool()` - Dispatch tool calls
- Stage 1 now passes `tools=[SEARCH_TOOL]` to models

### Architecture
```
User Query
    ↓
Stage 1: Query with tools=[SEARCH_TOOL]
    ├── Model needs current info → calls search_web → Tavily API
    └── Model knows answer → direct response
    ↓
Stage 2 & 3 (unchanged)
```

### Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Search API | Tavily | Built for LLM use, free tier available |
| Trigger | Model decides | More natural than `--web-search` flag |
| Max tool calls | 10 | Prevents infinite loops |

---

## v1.0: Core Platform
*January 2025*

### Overview
Built CLI and TUI interfaces on top of Karpathy's LLM Council concept.

### Implementation

**CLI (`cli/main.py`):**
- `query` command with Rich progress indicators
- `models` command to show configuration
- `--simple` and `--final-only` output modes
- Markdown rendering for responses

**TUI (`cli/tui.py`):**
- Textual app with tabbed interface
- Stage 1/2/3 views with keyboard navigation
- Keybindings: `1/2/3` for stages, `Q` to quit

**Backend:**
- 3-stage deliberation: responses → anonymous ranking → synthesis
- Async parallel queries with `asyncio.gather()`
- Graceful degradation if models fail

### Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| CLI framework | Typer + Rich | Clean API, good help generation |
| TUI framework | Textual | Modern, async-native |
| Anonymous ranking | Labels (A, B, C) | Prevents model favoritism |
| Default output | Show all stages | Transparency in deliberation |

### Council Configuration
- 5 models: GPT-5.2, Gemini 3 Pro, Claude Sonnet 4.5, Grok 4.1, DeepSeek R1
- Chairman: Gemini 3 Pro
- All via OpenRouter API

---

*For roadmap and planned features, see [PLAN.md](PLAN.md).*
