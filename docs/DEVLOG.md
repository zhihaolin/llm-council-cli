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
