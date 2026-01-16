# Development Log

This document tracks the development progress of the LLM Council CLI project.

---

## 2025-01-16: Project Setup & Planning

### Session Goals
- Fork Karpathy's LLM Council and set up for CLI development
- Create implementation plan
- Establish development workflow

### What Was Done

**1. Environment Setup**
- Installed `uv` package manager (Python)
- Installed frontend dependencies (`npm install`)
- Created `.env` with OpenRouter API key
- Verified web version runs correctly (backend :8001, frontend :5173)

**2. Repository Setup**
- Cloned from `karpathy/llm-council`
- Forked to `zhihaolin/llm-council-cli`
- Configured git remotes:
  - `origin` → zhihaolin/llm-council-cli (our fork)
  - `upstream` → karpathy/llm-council (original)

**3. Documentation**
- Created `docs/PLAN.md` - Full implementation roadmap
- Updated `README.md` - Added credits to Karpathy, documented CLI features
- Created `docs/DEVLOG.md` - This file

### Decisions Made

| Decision | Reasoning |
|----------|-----------|
| Fork instead of new repo | Maintains attribution, can sync upstream changes |
| Use Textual for TUI | Modern, async-native, good for complex terminal UIs |
| Use typer for CLI | Clean API, built on click, good help generation |
| Layered config (CLI > file > default) | Flexibility without complexity |
| Docs in `docs/` folder | Keep documentation organized |

### Files Changed
- `README.md` - Updated with credits and CLI preview
- `docs/PLAN.md` - Implementation roadmap (moved from root)
- `docs/DEVLOG.md` - This development log

### Next Steps
- [ ] Phase 1: Basic CLI with typer/rich
  - Create `cli/` package structure
  - Add dependencies to `pyproject.toml`
  - Implement basic `query` command
  - Test with real API call

### Notes
- Web version confirmed working at http://localhost:5173
- Backend and frontend servers running in background

---

## 2025-01-16: Phase 1 - Basic CLI Implementation

### Session Goals
- Implement basic CLI with typer and rich
- Test with real API calls
- Establish test → commit → push workflow

### What Was Done

**1. Created CLI Package Structure**
```
cli/
├── __init__.py      # Package init with version
├── __main__.py      # Enables `python -m cli`
└── main.py          # Typer CLI with commands
```

**2. Updated pyproject.toml**
- Added dependencies: `typer>=0.9.0`, `rich>=13.0.0`
- Added entry point: `llm-council = "cli.main:app"`
- Added `[tool.uv]` and `[tool.setuptools]` config for packaging

**3. Implemented CLI Commands**
- `query <question>` - Query the council with progress indicators
- `models` - Show current council configuration
- Flags: `--simple` (plain output), `--final-only` (skip stages 1 & 2)

**4. Rich Terminal Output**
- Progress spinners during API calls
- Panels for each model's response
- Tables for aggregate rankings
- Markdown rendering for responses

### Testing

| Test | Command | Result |
|------|---------|--------|
| Help | `uv run python -m cli --help` | ✓ Works |
| Models | `uv run python -m cli models` | ✓ Shows config table |
| Query | `uv run python -m cli query "What is 2+2?"` | ✓ Full 3-stage output |

### Issues Encountered

| Issue | Resolution |
|-------|------------|
| `uv sync` failed with multiple top-level packages | Added `[tool.setuptools.packages.find]` to include only `cli*` and `backend*` |
| Entry point script `llm-council` not finding module | Use `uv run python -m cli` instead; added `__main__.py` |

### Decisions Made

| Decision | Reasoning |
|----------|-----------|
| Use `python -m cli` over entry point | More reliable with uv's editable installs |
| Show all stages by default | Transparency - users can see full deliberation |
| Condensed Stage 2 output | Full evaluations too verbose; show rankings + parsed order |

### Files Changed
- `cli/__init__.py` - Package init
- `cli/__main__.py` - Module runner
- `cli/main.py` - Main CLI implementation
- `pyproject.toml` - Dependencies and packaging config

### Next Steps
- [x] Phase 2: Textual TUI with interactive interface
- [ ] Add `--models` and `--chairman` flags for model selection
- [ ] Add config file support (`~/.config/llm-council/config.yaml`)

---

## 2025-01-16: Phase 2 - Textual TUI Implementation

### Session Goals
- Implement interactive TUI with Textual
- Add tabbed interface for stages
- Enable keyboard navigation

### What Was Done

**1. Added Textual Dependency**
- Added `textual>=0.50.0` to pyproject.toml

**2. Created TUI Application (`cli/tui.py`)**
- Full Textual app with header, footer, keybindings
- Query input area with text field and submit button
- Tabbed content for Stage 1, Stage 2, Stage 3

**3. Stage Views**
- **Stage 1:** Sub-tabs for each model's response with markdown rendering
- **Stage 2:** DataTable for aggregate rankings + individual evaluations
- **Stage 3:** Markdown panel with chairman's synthesis

**4. Added `interactive` Command**
- `uv run python -m cli interactive` - Launch TUI
- `uv run python -m cli interactive "question"` - Launch with initial query

### TUI Features

| Feature | Keybinding |
|---------|------------|
| Switch to Stage 1 | `1` |
| Switch to Stage 2 | `2` |
| Switch to Stage 3 | `3` |
| New query | `Ctrl+N` |
| Quit | `Q` |

### Files Changed
- `pyproject.toml` - Added textual dependency
- `cli/tui.py` - New TUI implementation (~250 lines)
- `cli/main.py` - Added `interactive` command

### Testing
- [ ] TUI launches: `uv run python -m cli interactive`
- [ ] Query submission works
- [ ] Stage tabs switch correctly
- [ ] Keyboard shortcuts work

### Next Steps
- [ ] Add `--models` and `--chairman` CLI flags
- [ ] Add config file support
- [ ] Polish TUI styling

---

## 2025-01-16: TUI Fixes, Model Updates & Roadmap

### Session Goals
- Fix TUI bugs and test
- Update council models
- Review and update roadmap
- Improve documentation

### What Was Done

**1. Fixed TUI Bugs**
- Fixed `BadIdentifier` error - dots in widget IDs not allowed (e.g., `gpt-5.1`)
- Changed to simple numeric IDs (`response-0`, `response-1`, etc.)
- Updated Textual API usage for v7.x compatibility (context manager syntax)
- Changed Stage views to `ScrollableContainer` for proper scrolling

**2. Updated Color Scheme**
- New dark navy/blue theme for TUI
- Colors: `#1a1a2e` (background), `#16213e` (surface), `#0f3460` (primary), `#e94560` (accent)

**3. Model Configuration**
- Removed Grok from council (cost efficiency)
- Updated GPT-5.1 → GPT-5.2

**4. Roadmap Updates**
- Added **v1.2: Multi-Turn Debate Mode** - Models will critique and respond to each other
- Renumbered subsequent versions (v1.3-v1.7)

**5. Documentation**
- Rewrote README with Quick Start section
- Added CLI usage instructions
- Added "Running in New Terminal" section
- Updated model examples to current config

### Decisions Made

| Decision | Reasoning |
|----------|-----------|
| Prefer simple CLI over TUI | User preference; TUI needs more polish |
| Add Debate Mode to roadmap | More valuable than simple ranking; produces better answers |
| Defer TUI styling | Functionality first, polish later |
| Defer config file system | Already in plan, not blocking |

### Issues Encountered

| Issue | Resolution |
|-------|------------|
| TUI crash: BadIdentifier with dots | Use numeric IDs instead of model names |
| TUI crash: TabbedContent API change | Use context manager syntax for Textual 7.x |
| TUI color scheme "horrible" | Applied dark navy theme (still needs work) |

### Files Changed
- `cli/tui.py` - Fixed bugs, updated colors
- `backend/config.py` - GPT-5.2, removed Grok
- `docs/PLAN.md` - Added Debate Mode (v1.2)
- `README.md` - Complete rewrite with Quick Start

### Commits
- `646fc23` - Implement Phase 2: Textual TUI
- `d258d0f` - Fix TUI bugs and update to GPT-5.2
- `5e13a43` - Update README and add Debate Mode to roadmap

### Current Roadmap

| Version | Feature | Status |
|---------|---------|--------|
| v1.0 | Basic CLI + TUI | ✓ Done |
| v1.1 | Web Search Integration | ✓ Done |
| v1.2 | Multi-Turn Debate Mode | Planned |
| v1.3 | File/Document Upload | Planned |
| v1.4 | Image Input | Planned |
| v1.5 | Presets & Profiles | Planned |
| v1.6 | Conversation History | Planned |
| v1.7 | Streaming Responses | Planned |
| v1.8 | Extended Tooling | Planned |
| v1.9 | Local Models (Ollama) | Planned |

### Next Steps
- [ ] Implement config file support
- [ ] Add `--models` and `--chairman` CLI flags
- [x] v1.1: Web Search Integration

---

## 2026-01-17: v1.1 Web Search Integration

### Session Goals
- Implement web search capability for council models
- Use Tavily API with tool calling so models decide when to search

### What Was Done

**1. Created `backend/search.py`**
- Tavily API wrapper with `search_web()` async function
- `SEARCH_TOOL` definition for OpenAI-style function calling
- `format_search_results()` to convert search results to LLM-readable text

**2. Updated `backend/openrouter.py`**
- Added `query_model_with_tools()` function
- Handles tool calling loop: model requests tool → execute → return results → get final response
- Supports `max_tool_calls` parameter to prevent infinite loops
- Returns `tool_calls_made` list in response for transparency

**3. Updated `backend/council.py`**
- Added `execute_tool()` function to dispatch tool calls to appropriate handlers
- Modified `stage1_collect_responses()` to use `query_model_with_tools()`
- Models now have access to `search_web` tool during Stage 1
- Tool calls are tracked in stage1_results for each model

**4. Updated `docs/PLAN.md`**
- Documented the full v1.1 implementation plan before coding
- Included tool definition format and calling flow

### Architecture

```
User Query
    │
    ▼
Stage 1: Query models WITH tools=[SEARCH_TOOL]
    │
    ├── Model decides: "I need current info"
    │       ↓
    │   Tool call: search_web(query)
    │       ↓
    │   Tavily API → Search results
    │       ↓
    │   Results sent back to model
    │       ↓
    │   Model generates final response
    │
    └── Model decides: "I know this" → Direct response
    │
    ▼
Stage 2 & 3 (unchanged)
```

### Testing

| Test | Command | Result |
|------|---------|--------|
| Weather query | `uv run python -m cli query "What is the current weather?"` | ✓ Models attempt to use search tool |
| AI regulation | `uv run python -m cli query "AI regulation in 2026"` | ✓ Full 3-stage response |

**Note:** Tool calling works correctly - models receive the tool definition and attempt to use it. To enable actual web searches, add `TAVILY_API_KEY=tvly-xxx` to `.env`.

### Files Changed
- `backend/search.py` - New file: Tavily wrapper and tool definition
- `backend/openrouter.py` - Added `query_model_with_tools()`
- `backend/council.py` - Integrated search tool into Stage 1
- `docs/PLAN.md` - Documented v1.1 implementation plan

### Post-Implementation Tuning
- Increased `max_tool_calls` from 3 → 5 → 10 after testing showed models hitting the limit on complex queries

### Council Member Updates
- Added `x-ai/grok-4.1-fast` (free on OpenRouter)
- Added `deepseek/deepseek-r1-0528` (free, strong reasoning from China)
- Tested `qwen/qwen3-32b` but removed - not competitive enough
- Final 5-member council: GPT-5.2, Gemini 3 Pro, Claude Sonnet 4.5, Grok 4.1 Fast, DeepSeek R1

### Next Steps
- [ ] Consider showing tool calls in CLI output
- [ ] v1.2: Multi-Turn Debate Mode
- [ ] v1.3: File/Document Upload (txt, pdf, docx, epub)

---

*Template for future entries:*

```markdown
## YYYY-MM-DD: Session Title

### Session Goals
- Goal 1
- Goal 2

### What Was Done
1. ...
2. ...

### Decisions Made
| Decision | Reasoning |
|----------|-----------|

### Testing
- [ ] Test 1: Result
- [ ] Test 2: Result

### Issues Encountered
- Issue: ...
- Resolution: ...

### Files Changed
- `file1.py` - Description
- `file2.py` - Description

### Next Steps
- [ ] ...

### Commits
- `abc1234` - Commit message
```
