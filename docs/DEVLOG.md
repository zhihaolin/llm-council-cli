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
