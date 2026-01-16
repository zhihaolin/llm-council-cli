# LLM Council CLI - Implementation Plan

## Overview

Extend Karpathy's LLM Council with a terminal-based interface using Python's Textual library for a rich TUI experience. The CLI will provide the same 3-stage council deliberation workflow without requiring a web browser.

## Goals

1. **Standalone CLI tool** - Single command to query the council
2. **Rich TUI** - Interactive terminal UI with panels, tabs, and progress indicators
3. **Simple mode** - Pipe-friendly output for scripting
4. **Reuse existing logic** - Leverage `backend/council.py` and `backend/openrouter.py`
5. **Configurable models** - Select council members and chairman via CLI or config

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                      cli.py                             │
│  (typer CLI entry point - handles args, launches TUI)   │
└─────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────┐
│                      tui.py                             │
│  (Textual App - interactive terminal interface)         │
│                                                         │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐     │
│  │  Stage 1    │  │  Stage 2    │  │  Stage 3    │     │
│  │  Responses  │  │  Rankings   │  │  Synthesis  │     │
│  │  (Tabs)     │  │  (Table)    │  │  (Panel)    │     │
│  └─────────────┘  └─────────────┘  └─────────────┘     │
└─────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────┐
│              backend/council.py (existing)              │
│  stage1_collect_responses()                             │
│  stage2_collect_rankings()                              │
│  stage3_synthesize_final()                              │
└─────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────┐
│             backend/openrouter.py (existing)            │
│  query_model() / query_models_parallel()                │
└─────────────────────────────────────────────────────────┘
```

## Features

### Core Features

| Feature | Description |
|---------|-------------|
| Query command | `llm-council "question"` - run full council |
| Interactive mode | `llm-council -i` - TUI with input prompt |
| Simple mode | `llm-council -s "question"` - just final answer |
| Show models | `llm-council models` - display current config |
| Model selection | `llm-council --models gpt-5,claude-4 "question"` |
| Chairman selection | `llm-council --chairman gemini-3 "question"` |

### Model Configuration

Models can be configured in three ways (in order of precedence):

1. **CLI flags** (highest priority)
   ```bash
   llm-council --models "openai/gpt-5.1,anthropic/claude-sonnet-4.5" \
               --chairman "google/gemini-3-pro-preview" \
               "Your question"
   ```

2. **Config file** (`~/.config/llm-council/config.yaml`)
   ```yaml
   council_models:
     - openai/gpt-5.1
     - google/gemini-3-pro-preview
     - anthropic/claude-sonnet-4.5
     - x-ai/grok-4
   chairman_model: google/gemini-3-pro-preview
   ```

3. **Default** (falls back to `backend/config.py`)

### TUI Features

| Feature | Description |
|---------|-------------|
| Stage tabs | Switch between Stage 1, 2, 3 views |
| Model tabs | Within Stage 1, tab through each model's response |
| Progress spinner | Show which stage/model is currently processing |
| Rankings table | Aggregate rankings with avg position |
| Markdown rendering | Proper formatting of model responses |
| Keyboard navigation | `1/2/3` for stages, `Tab` for models, `q` to quit |

## File Structure

```
llm-council-cli/
├── backend/           # Existing - no changes needed
│   ├── council.py
│   ├── openrouter.py
│   └── config.py
├── cli/               # New CLI package
│   ├── __init__.py
│   ├── main.py        # Typer CLI entry point
│   ├── tui.py         # Textual TUI application
│   ├── widgets.py     # Custom Textual widgets
│   ├── config.py      # Config loading (CLI > file > default)
│   └── styles.tcss    # Textual CSS styling
├── pyproject.toml     # Add typer, textual, rich deps
└── PLAN.md            # This file
```

## Dependencies to Add

```toml
[project.dependencies]
# ... existing deps ...
typer = ">=0.9.0"
textual = ">=0.50.0"
rich = ">=13.0.0"
pyyaml = ">=6.0"  # For config file

[project.scripts]
llm-council = "cli.main:app"
```

## Implementation Steps

### Phase 1: Basic CLI (no TUI)

1. Create `cli/` package structure
2. Add dependencies to `pyproject.toml`
3. Implement `cli/config.py` - layered config loading
4. Implement `cli/main.py` with typer:
   - `query` command with progress spinner (rich)
   - `models` command to show config
   - `-s/--simple` flag for minimal output
   - `--models` and `--chairman` flags
5. Test: `uv run llm-council "test question"`

### Phase 2: Textual TUI

1. Create `cli/tui.py` with Textual App
2. Layout: Header, TabPane for stages, Footer with keybindings
3. Stage 1 view: TabbedContent for each model's response
4. Stage 2 view: DataTable for rankings + expandable evaluations
5. Stage 3 view: Markdown panel with chairman's synthesis
6. Input widget for new queries within TUI

### Phase 3: Polish

1. Add keyboard shortcuts (1/2/3 for stages, q to quit)
2. Style with `styles.tcss` (colors, borders, spacing)
3. Add loading states and progress indicators
4. Error handling and graceful degradation
5. Update README with CLI usage

## UI Mockup

```
┌─ LLM Council ─────────────────────────────────────────────────────┐
│ Query: What is the best programming language for beginners?       │
├───────────────────────────────────────────────────────────────────┤
│ [Stage 1: Responses] [Stage 2: Rankings] [Stage 3: Final]        │
├───────────────────────────────────────────────────────────────────┤
│ ┌─ gpt-5.1 ─┬─ gemini-3 ─┬─ claude-4.5 ─┬─ grok-4 ─┐             │
│ │                                                    │             │
│ │ Python is widely recommended for beginners due to │             │
│ │ its clean syntax and readability. Here's why:     │             │
│ │                                                    │             │
│ │ 1. **Simple syntax** - reads like English         │             │
│ │ 2. **Rich ecosystem** - libraries for everything  │             │
│ │ 3. **Strong community** - help is always available│             │
│ │ ...                                                │             │
│ └────────────────────────────────────────────────────┘             │
├───────────────────────────────────────────────────────────────────┤
│ [1] Stage 1  [2] Stage 2  [3] Stage 3  [q] Quit  [?] Help        │
└───────────────────────────────────────────────────────────────────┘
```

## Testing Strategy

1. **Unit tests**: Mock OpenRouter API responses
2. **Integration test**: Run with real API (manual)
3. **TUI test**: Textual's built-in snapshot testing

---

## Future Roadmap

### v1.1: Web Search Integration

Enable council members to search the web when they need current information. Models decide when to search using tool calling.

**Decision: Tavily API + Tool Calling**

- **Tavily**: Free tier 1,000 searches/month, built for LLM use
- **Tool Calling**: Models decide when to search (not user-driven `--web-search` flag)

**Architecture:**

```
User Query
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│  Stage 1: Query models WITH search tool available       │
│                                                         │
│  Model sees: "What's the latest on X?"                  │
│  Model decides: "I need current info" → calls search    │
│  Your code: Executes Tavily search, returns results     │
│  Model: Uses results to form response                   │
└─────────────────────────────────────────────────────────┘
    │
    ▼
  Stage 2 & 3 (normal flow)
```

**Files to create/modify:**

1. **`backend/search.py`** (new)
   - `SEARCH_TOOL` - Tool definition for function calling
   - `search_web(query)` - Async function to call Tavily API
   - `format_search_results()` - Format results for LLM context

2. **`backend/openrouter.py`** (modify)
   - Update `query_model()` to accept `tools` parameter
   - Handle tool call responses (when model wants to use a tool)
   - Execute tool, send results back, get final response

3. **`backend/council.py`** (modify)
   - Pass `SEARCH_TOOL` to models in Stage 1
   - Handle the tool calling loop

4. **`.env`** (update)
   - Add `TAVILY_API_KEY=tvly-xxx`

**Tool Definition:**

```python
SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "search_web",
        "description": "Search the web for current information. Use this when you need up-to-date information, recent events, current statistics, or facts you're unsure about.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query"
                }
            },
            "required": ["query"]
        }
    }
}
```

**Tool Calling Flow:**

```
1. Send request to OpenRouter with tools=[SEARCH_TOOL]
2. Model response may include:
   - Normal content (no tool needed)
   - tool_calls: [{"function": {"name": "search_web", "arguments": {"query": "..."}}}]
3. If tool_calls:
   a. Parse the arguments
   b. Execute search_web(query) → Tavily API
   c. Send tool result back to model
   d. Get final response with search context
4. Return final response
```

**CLI Usage:**

```bash
# Web search is automatic - models decide when to use it
uv run python -m cli query "What's the latest news on AI regulation?"

# Model will automatically search if it needs current info
# No --web-search flag needed
```

**Environment Setup:**

```bash
# Add to .env
TAVILY_API_KEY=tvly-your-key-here
```

### v1.2: Multi-Turn Debate Mode

Enable models to challenge and respond to each other for deeper analysis.

**Current flow (ranking only):**
```
Stage 1: Independent answers → Stage 2: Rank → Stage 3: Synthesize
```

**Debate flow:**
```
Round 1: Independent answers
Round 2: Each model critiques others' answers
Round 3: Models defend/revise their positions
Round N: Continue until consensus or max rounds
Final: Chairman synthesizes with full debate context
```

**Implementation:**
- Add `--debate` flag to enable debate mode
- Add `--rounds N` to set max debate rounds (default: 2)
- Track position changes across rounds
- Chairman considers debate quality, not just final positions

**Usage:**
```bash
llm-council --debate "Is capitalism or socialism better for reducing poverty?"
llm-council --debate --rounds 3 "Complex ethical question"
```

### v1.3: Presets & Profiles

Save and load council configurations:

```bash
# Save current config as a preset
llm-council preset save "coding-council"

# Use a preset
llm-council --preset coding-council "How do I optimize this SQL?"

# List presets
llm-council preset list
```

### v1.4: Conversation History

- Persist conversations locally (SQLite or JSON)
- Continue previous conversations: `llm-council --continue`
- Browse history in TUI

### v1.5: Streaming Responses

- Show tokens as they arrive (requires SSE support from OpenRouter)
- Progressive rendering in TUI
- Better perceived latency

### v1.6: Extended Tooling

- **Code execution**: Let models run code to verify solutions
- **File context**: `llm-council --file ./code.py "Review this"`
- **Image input**: For vision-capable models

### v1.7: Local Models

- Support Ollama as a backend
- Mix cloud + local models in same council
- Fallback to local when API unavailable

### Future Ideas (Unscheduled)

- [ ] Web UI that calls the same CLI backend (hybrid mode)
- [ ] Export to markdown/PDF
- [ ] Model performance analytics (track which models rank highest over time)
- [ ] Custom ranking criteria (security, performance, readability, etc.)
- [ ] Voice input/output

---

## Open Questions

1. Should we support conversation history in CLI mode? → **Roadmap v1.3**
2. Stream responses or wait for complete response? → **Roadmap v1.4**
3. Config file for models or just use existing `backend/config.py`? → **Yes, layered config**

---

*Plan created: 2025-01-16*
*Status: Ready for review*
