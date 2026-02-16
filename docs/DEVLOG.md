# Development Log

Technical decisions and implementation notes for LLM Council.

---

## Post-v1.9: Compact chat banner
*February 2026*

### Overview
Replaced the Panel-based chat banner with compact text lines framed by horizontal rules. Improved mode line format and indicator visibility.

### Changes
- **Chat banner**: Replaced Rich Panel with compact text: title line (`Council Chat · {id} · {status}`), mode line, commands line, framed by horizontal rules.
- **Mode line format**: Changed from `Debate (N rounds) [streaming] [react]` to dot-delimited `Debate · N rounds · React on · Stream off`. Correct grammar for "1 round" vs "N rounds". Always shows all settings explicitly (on/off).
- **Mode updated feedback**: `_print_mode()` now prints `Mode updated: Debate · 1 round · ...` instead of re-printing the full Rich-markup mode line.
- **Model panel indicators**: `[reasoned]` and `[searched]` no longer use dim styling — visible at normal intensity.
- **`format_chat_mode_line()`**: Returns a plain string (no Rich markup), styling applied by callers.

### Results
- 111 tests across 10 test files, ruff clean

---

## Post-v1.9: Chat UI improvements
*February 2026*

### Overview
Cleaned up the chat REPL interface: simplified prompt, organized commands, added visibility into ReAct reasoning and Reflection synthesis.

### Changes
- **Chat prompt**: Always shows `council>` instead of `debate(N)>` / `rank>`. Mode details available via `/mode`. Removed `format_prompt_mode()`.
- **Commands**: Grouped by function with `·` separators in banner (`/new /history /use <id> · /debate /rounds /stream /react · /mode /help /exit`). `/help` output organized into Session / Config / Info sections.
- **Model panels**: Show `[reasoned]` and `[searched]` indicators in title (e.g., `gpt-4.1 [reasoned] [searched]`). Engine sets `"reasoned": True` in result dicts when ReAct was used.
- **Chairman headers**: Changed from "CHAIRMAN'S ANALYSIS"/"CHAIRMAN'S SYNTHESIS" to "CHAIRMAN'S REFLECTION". Analysis panel title changed to "Reflection".

### Results
- 108 tests across 10 test files, ruff clean

---

## Post-v1.9: Chairman Reflection + Council Member ReAct
*February 2026*

### Overview
Swapped synthesis and reasoning roles: chairman now uses **Reflection** (deep analysis, no tools — always on), council members now use **ReAct** (visible Thought→Action→Observation reasoning + web search — controlled by `--no-react`/`/react on|off`).

Previously the chairman used ReAct, which steered it toward web searching rather than analyzing debate content. Council members used opaque native function calling.

### Architecture

| | Chairman | Council |
|---|---|---|
| **react ON** (default) | Reflection | ReAct loop (Thought → search_web → respond) |
| **react OFF** (`--no-react`) | Reflection | Native function calling |

### Key changes
- **New**: `synthesize_with_reflection()` (engine/reflection.py), `council_react_loop()` (engine/react.py), `parse_reflection_output()`, `build_reflection_prompt()`, `wrap_prompt_with_react()`
- **Removed**: `synthesize_with_react()`, `build_react_prompt()`, `run_react_synthesis()`, `synthesize_debate()`, `stage3_synthesize_final()`
- **Modified**: `RoundConfig` gains `uses_react` field; `build_round_config()` gains `react_enabled` param; both execution strategies dispatch to `council_react_loop()` when `uses_react=True`; `stage1_collect_responses()` gains `react_enabled` param
- **CLI**: `run_reflection_synthesis()` replaces both `run_react_synthesis()` and inline synthesis; `skip_synthesis` param removed from all runners
- **Streaming**: New event types `thought`, `action`, `observation` for council ReAct traces displayed in debate streaming mode

### Results
- 107 tests across 10 test files, ruff clean
- Both ranking and debate modes use Reflection for chairman, ReAct for council

---

## Post-v1.9: Command pattern for chat REPL
*February 2026*

### Overview
Replaced ~155-line if/elif chain in `run_chat_session()` with a `ChatState` dataclass, 10 `cmd_*` handler functions, and a `COMMAND_HANDLERS` dispatch dict.

### Changes
- `llm_council/cli/chat_session.py`: Added `ChatState` dataclass (replaces 7 loose locals), `_print_mode()` / `_print_banner()` helpers (eliminate repeated argument passing), 10 `cmd_*` handler functions (each returns `bool` — True=continue, False=exit), `COMMAND_HANDLERS` dispatch dict. Main loop reduced to 3-line dispatch.

### Results
- 92 tests pass, ruff clean
- No behavior changes — pure refactor

---

## Post-v1.9: Extract `RoundConfig` dataclass
*February 2026*

### Overview
Both execution strategies (`debate_round_parallel`, `debate_round_streaming`) duplicated if/elif dispatch on `round_type` to determine prompt construction, tool availability, and response parsing. Extracted into a `RoundConfig` frozen dataclass + `build_round_config()` factory.

### Changes
- `llm_council/engine/debate.py`: Added `RoundConfig(uses_tools, build_prompt, has_revised_answer)` dataclass and `build_round_config()` factory. Both strategies now call `build_round_config()` once and use the config throughout. Removed `query_initial()`, `query_critique()`, `query_defense()` — their logic is inlined into `build_round_config()` and the execution strategies.
- `llm_council/engine/__init__.py`: Replaced `query_initial/query_critique/query_defense` exports with `RoundConfig/build_round_config`.
- `tests/test_debate.py`: Replaced 8 `TestQuery*` tests with 7 `TestBuildRoundConfig` tests (synchronous, no mocking needed).

### Results
- 92 tests pass, ruff clean
- Net reduction: ~158 lines (150 insertions, 308 deletions)

---

## Post-v1.9: Remove batch mode, make parallel default
*February 2026*

### Overview
Removed `run_debate_with_progress()` (batch mode) — it was strictly dominated by `run_debate_parallel()` which shows live per-model spinners. With batch gone, parallel becomes the default non-streaming debate mode, eliminating the `--parallel` flag and `/parallel` chat command.

### Changes
- `llm_council/cli/runners.py`: Deleted `run_debate_with_progress()` (~75 lines)
- `llm_council/cli/main.py`: Removed `--parallel` CLI option, simplified debate dispatch to `if stream: streaming else: parallel`
- `llm_council/cli/chat_session.py`: Removed `parallel_enabled` variable, `/parallel` command handler, and mutual exclusion logic
- `llm_council/cli/chat_commands.py`: Removed `"parallel"` from `CHAT_COMMANDS`, removed `parallel_enabled` param from `format_chat_mode_line`, `format_prompt_mode`, `build_chat_prompt`
- `llm_council/cli/presenters.py`: Removed `parallel_enabled` param from `print_chat_banner`, `/parallel` from help text, `parallel` param from `print_query_header`

### Results
- 92 tests pass, ruff clean
- Net reduction: ~153 lines (21 insertions, 174 deletions)

---

## Post-v1.9: Add `ExecuteRound` Protocol
*February 2026*

### Overview
Added an explicit `typing.Protocol` for the `execute_round` parameter of `run_debate()`. The strategy pattern previously used a bare `Callable` type — the contract between the orchestrator and its two strategies (`debate_round_parallel`, `debate_round_streaming`) was purely duck-typed. The protocol makes the expected signature visible to readers, IDEs, and type checkers (pyright).

### Changes
- `llm_council/engine/debate.py`: Added `ExecuteRound` protocol class with keyword-only `__call__` signature. Changed `run_debate(execute_round: Callable)` to `run_debate(execute_round: ExecuteRound)`.
- `llm_council/engine/__init__.py`: Exported `ExecuteRound` in imports, `__all__`, and module docstring.
- `CLAUDE.md`: Documented `ExecuteRound` protocol in debate functions section and common gotchas.

### Results
- 0 pyright errors (both built-in strategies conform to the protocol)
- All tests pass, ruff clean

---

## Post-v1.9: Fix `max_rounds` semantics and streaming error/complete conflict
*February 2026*

### Overview
Fixed two bugs in `debate.py`:

1. **`max_rounds` off-by-one could produce dangling critiques.** The old `while round_num <= max_rounds + 1` loop added rounds one-at-a-time, so odd values > 2 would end on a critique with no defense. Renamed `max_rounds` → `cycles` where `--rounds N` = N complete critique-defense cycles after the initial round. Always ends on defense.

2. **Streaming could emit `model_error` then `model_complete` for the same model.** In `debate_round_streaming`, if tokens streamed and then an error arrived, the `break` exited the inner loop but `full_content` was non-empty, causing `model_complete` to fire after `model_error`. Added `had_error` flag to guard against this.

### Changes
- `llm_council/engine/debate.py`: Renamed `max_rounds` → `cycles`, replaced round-building with explicit cycle loop. Added `had_error` flag in streaming.
- `llm_council/cli/runners.py`: Renamed `max_rounds` → `cycles` in 3 runner signatures and `_run_debate()` calls.
- `llm_council/cli/main.py`: `--rounds` default `2` → `1`, updated help text.
- `llm_council/cli/constants.py`: `DEFAULT_DEBATE_ROUNDS` `2` → `1`.
- `tests/test_streaming.py`: Renamed `max_rounds` → `cycles` at 4 call sites. Added `test_multiple_cycles_produces_correct_rounds` and `test_streaming_error_prevents_model_complete`.
- `CLAUDE.md`: Updated `max_rounds` references to `cycles`.

### Semantics Change
| `--rounds` | Old behavior | New behavior |
|---|---|---|
| 1 | 2 interaction rounds (initial + critique) — dangling critique! | 3 interaction rounds (initial + critique + defense) |
| 2 (old default) | 3 interaction rounds (initial + critique + defense) | 5 interaction rounds (initial + 2×critique-defense) |
| New default | `--rounds 2` | `--rounds 1` — same output as old default |

### Results
- 93 tests pass, ruff clean
- No dangling critiques possible regardless of `--rounds` value
- No spurious `model_complete` events after streaming errors

---

## Post-v1.9: Remove Textual TUI
*February 2026*

### Overview
Removed the Textual-based TUI (`tui.py`) and the `interactive` CLI command. The chat REPL (`llm-council chat`) fully supersedes it — it supports debate mode, streaming, parallel execution, ReAct, and conversation history, none of which the TUI had.

### Changes
- Deleted `llm_council/cli/tui.py` (~410 lines)
- Removed `interactive` command from `main.py`
- Removed `textual>=0.50.0` from `pyproject.toml` dependencies
- Updated README.md and CLAUDE.md to remove TUI references

---

## Post-v1.9: Remove engine wrappers, inline synthesis in CLI runners
*February 2026*

### Overview
Removed `run_debate_parallel()` and `run_debate_streaming()` from `debate.py`. These violated SRP: each wired `run_debate()` to an executor AND performed chairman synthesis. The `skip_synthesis` parameter was the tell — it disabled half the function. CLI runners now call `run_debate()` directly and handle synthesis inline based on their presentation needs.

### Changes
- Deleted `run_debate_parallel()` and `run_debate_streaming()` from `debate.py` (~120 lines)
- Removed from `__init__.py` imports and `__all__`
- `runners.py`: Updated imports, rewrote `run_debate_streaming()` and `run_debate_parallel()` to two-phase (debate + inline synthesis)
- `test_streaming.py`: Rewrote 2 tests to use `run_debate` + `debate_round_parallel` directly

### Results
- Net reduction: ~125 lines
- 91 tests pass, ruff clean
- All three CLI runners now follow the same pattern: call `run_debate()` directly, then handle synthesis at the CLI layer

---

## Post-v1.9: Merge debate.py and debate_async.py
*February 2026*

### Overview
Merged `debate.py` (per-model query functions) and `debate_async.py` (orchestrator and execution strategies) into a single `debate.py`. The split was historical — after v1.9's strategy pattern refactoring, `debate_async.py` just called through to functions in `debate.py`, and both files shared a duplicate `execute_tool()`. No clean architectural boundary remained.

### Changes
- Absorbed `query_initial`, `query_critique`, `query_defense`, `synthesize_debate` into `debate_async.py`
- Removed duplicate `execute_tool()` (kept the one in debate_async.py, identical)
- Deleted old `debate.py`, renamed `debate_async.py` → `debate.py` via `git mv`
- Dropped `debate_round_initial`, `debate_round_critique`, `debate_round_defense` (batch wrappers unused in production)
- Updated `__init__.py`, `runners.py`, `test_debate.py`, `test_streaming.py`
- Collapsed duplicate mock target patches in tests (previously needed separate targets for each module)

### Results
- Net reduction: ~100 lines (removed duplicates and batch wrappers)
- 91 tests pass (7 tests removed for dropped batch wrappers)
- Single module for all debate logic — easier to navigate

---

## v1.9: Consolidate Round-Sequencing with Strategy Pattern
*February 2026*

### Overview
Eliminated 4x duplication of the debate round sequence (initial → critique → defense → extra rounds) by introducing a single `run_debate()` orchestrator with pluggable execution strategies.

### Problem
The round sequence was duplicated in `run_debate_council()`, `run_debate_parallel()`, `run_debate_streaming()`, and `run_debate_with_progress()`. Any change to the debate structure required updating all four.

### Solution: Strategy Pattern
- **`run_debate(user_query, execute_round, max_rounds)`** — single orchestrator defining the sequence once
- **`debate_round_parallel()`** — executor strategy: parallel with per-model events (existing, already matched protocol)
- **`debate_round_streaming()`** — executor strategy: sequential with per-token events (new, consolidates `stream_initial_round_with_tools()` + `stream_round()`)

### Changes
- `debate_async.py`: Added `run_debate()` and `debate_round_streaming()`; simplified `run_debate_parallel()` and `run_debate_streaming()` to delegate to `run_debate()`
- `debate.py`: Removed `run_debate_council()` (dead code)
- `runners.py`: Rewrote `run_debate_with_progress()` to consume `run_debate` events
- `__init__.py`: Updated exports

### Results
- Net reduction: ~400 lines of duplicated round-sequencing logic
- 95 tests pass (3 new tests for orchestrator + streaming executor)
- Round sequence changes now require editing only `run_debate()`

---

## Post-v1.6.3: Package Reorganization
*February 2026*

### Changes
- Reorganized two top-level packages (`backend/` + `cli/`) into single `llm_council/` package
- Renamed subpackage `council/` → `engine/` to avoid `llm_council.council` redundancy
- Module renames for clarity:
  - `config.py` → `settings.py` (avoids confusion with `config.yaml`)
  - `orchestrator.py` → `ranking.py` (parallel with `debate.py`)
  - `streaming.py` → `debate_streaming.py` → `debate_async.py` (clarifies scope)
  - `chat.py` → `chat_commands.py` (more descriptive)
  - `utils.py` → `constants.py` (matches contents)
- Introduced `adapters/` subpackage for external service clients (`openrouter_client.py`, `tavily_search.py`, `json_storage.py`)
- Fixed duplicated constants in `chat_session.py` (now imports from `constants.py`)
- Cleaned stale build artifacts (`llm_council.egg-info/`), added `.ruff_cache/` to `.gitignore`

### Final Structure
```
llm_council/
├── settings.py
├── adapters/
│   ├── openrouter_client.py
│   ├── tavily_search.py
│   └── json_storage.py
├── engine/
│   ├── ranking.py
│   ├── debate.py
│   ├── debate_async.py
│   ├── react.py
│   ├── prompts.py
│   ├── parsers.py
│   └── aggregation.py
└── cli/
    ├── main.py
    ├── runners.py
    ├── presenters.py
    ├── chat_session.py
    ├── chat_commands.py
    ├── tui.py
    └── constants.py
```

### Note on Historical Entries
Entries below this point reference the pre-reorganization paths (`backend/`, `cli/`, `backend/council/`). These are historically accurate for when those changes were made.

---

## Post-v1.6.3: Docker CI Smoke Test & Import Cleanup
*January 2026*

### Changes
- Added `docker` job to CI pipeline (`.github/workflows/test.yml`)
  - Builds Docker image after tests pass
  - Runs `docker run --rm llm-council --help` as smoke test (verifies entrypoint + imports)
  - Pipeline is now: `lint` → `test` → `docker`
- Removed `sys.path.insert` hack from `cli/main.py` and `cli/tui.py`
  - The project is properly packaged (`[tool.uv] package = true` + hatch build config)
  - Both `cli` and `backend` are on the Python path automatically when run via `uv run`
  - Also removed the now-unused `import sys` from both files

---

## Post-v1.6.3: Config Extraction
*January 2026*

Moved configuration from hardcoded Python to YAML file.

### Changes
- Added `config.yaml` in project root for user-editable settings
- Updated `backend/config.py` to load from YAML (falls back to defaults)
- Added `pyyaml>=6.0` dependency
- Removed unused `fastapi` and `uvicorn` dependencies (web UI was removed in v1.6.1)

### Config Structure
```yaml
council_models:
  - openai/gpt-4o-mini
  - x-ai/grok-3
  - deepseek/deepseek-chat
chairman_model: openai/gpt-4o-mini
openrouter_api_url: https://openrouter.ai/api/v1/chat/completions
data_dir: data/conversations
```

API keys remain in `.env` (security best practice).

---

## Post-v1.6.3: CLI Module Rename
*January 2026*

Renamed `cli/orchestrators.py` → `cli/runners.py` to avoid confusion with `backend/council/orchestrator.py`. Both files existed after v1.6.1 refactoring and had similar names but different purposes:
- `backend/council/orchestrator.py` - Stage 1-2-3 flow coordination (backend logic)
- `cli/runners.py` - CLI presentation wrappers with progress indicators

---

## v1.6.3: Docker Support
*January 2026*

### Overview
Added Docker support for one-command setup. No local Python or dependencies required.

### Usage
```bash
# Build
docker build -t llm-council https://github.com/zhihaolin/llm-council-cli.git

# Run
docker run -e OPENROUTER_API_KEY=your-key llm-council query "Your question"
```

### Files Added
- `Dockerfile` - Multi-stage build with uv for fast installs
- `.dockerignore` - Excludes tests, docs, .git from image

---

## v1.6.2: CI Quality Gates
*January 2026*

### Overview
Added linting and type checking to CI pipeline.

### Changes

**New dev dependencies:**
- `ruff>=0.4.0` - Linting and formatting
- `pyright>=1.1.350` - Static type checking

**CI pipeline** (`.github/workflows/test.yml`):
```
lint job (runs first):
  → ruff check
  → ruff format --check
  → pyright

test job (runs after lint):
  → pytest
```

**Code fixes:**
- 208 auto-fixed issues (import sorting, modern type hints)
- Removed unused imports and variables

### Configuration

| Tool | Config |
|------|--------|
| Ruff | line-length=100, select E/W/F/I/UP |
| Pyright | basic mode, warnings for optional types |

### Results
- All checks pass in CI
- 0 pyright errors (31 warnings)

### Note on Coverage
Line coverage was initially added but later removed. TDD discipline matters more than coverage metrics—line coverage only measures "was code executed" not "does code work correctly."

---

## v1.6.1: SOLID Refactoring
*January 2026*

### Overview
Major refactoring to apply SOLID principles and remove the unused Web UI. Split monolithic files into focused modules.

### What Was Removed
- `frontend/` - Entire React app (unused, CLI-only project)
- `backend/main.py` - FastAPI server (not needed for CLI)
- `start.sh` - Launch script for frontend+backend

### Backend Refactoring

Split `backend/council.py` (1,722 lines) into focused modules:

```
backend/council/
├── __init__.py       # Public API exports (backward compatible)
├── aggregation.py    # Ranking calculations (~55 lines)
├── debate.py         # Debate orchestration (~210 lines)
├── orchestrator.py   # Stage 1-2-3 flow (~175 lines)
├── parsers.py        # Regex/text parsing (~155 lines)
├── prompts.py        # All prompt templates (~290 lines)
├── react.py          # ReAct chairman logic (~105 lines)
└── streaming.py      # Event generators (~530 lines)
```

### CLI Refactoring

Split `cli/main.py` (1,407 lines) into focused modules:

```
cli/
├── main.py           # Command routing only (~270 lines)
├── presenters.py     # All print_* functions (~250 lines)
├── runners.py        # run_* execution functions (~450 lines) [renamed from orchestrators.py]
├── chat_session.py   # Chat REPL logic (~280 lines)
├── chat.py           # Command parsing (unchanged)
└── utils.py          # Constants (~10 lines)
```

### SOLID Principles Applied

| Principle | Change |
|-----------|--------|
| **Single Responsibility** | Each module has one reason to change |
| **Interface Segregation** | `__init__.py` exports only public API |

### Documentation
- Added `docs/REFACTORING.md` - Educational guide with bad→good examples for each SOLID principle

### Results
- All 84 tests pass
- Net reduction: ~4,500 lines (deleted unused Web UI)
- CLI commands unchanged (backward compatible)

---

## v1.6: ReAct Chairman
*January 2026*

### Overview
The chairman now uses the ReAct (Reasoning + Acting) pattern to verify facts before synthesizing. If model responses disagree on factual claims, the chairman can search to verify.

### Implementation

**Backend (`backend/council.py`):**
- `parse_react_output()` - Extracts Thought/Action from model output using regex
- `build_chairman_context_ranking()` - Formats Stage 1/2 results for chairman
- `build_chairman_context_debate()` - Formats debate rounds for chairman
- `build_react_prompt()` - Constructs ReAct system prompt with tool descriptions
- `synthesize_with_react()` - Async generator implementing the ReAct loop
  - Yields: `token`, `thought`, `action`, `observation`, `synthesis` events
  - Max 3 iterations to prevent infinite loops

**CLI (`cli/main.py`):**
- `run_react_synthesis()` - Displays ReAct trace with color coding
  - Thought: cyan
  - Action: yellow
  - Observation: dim
- Works with parallel, streaming, and batch modes

**CLI (`cli/chat.py`):**
- `/react on|off` command
- ReAct enabled by default

### ReAct Pattern

```
Thought: The responses disagree on the current Bitcoin price. I should verify.
Action: search_web("bitcoin price today")
Observation: Bitcoin is currently trading at $67,234...
Thought: Now I can synthesize with verified data.
Action: synthesize()
[Final synthesis]
```

### Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Default state | Enabled | Most questions benefit from potential fact verification |
| Max iterations | 3 | Prevents infinite search loops |
| Streaming | Trace only | Token streaming for Thought/Action would be noisy |
| Empty synthesize() | Re-prompt | Model sometimes forgets to provide answer after action |

### Tests
- `test_react.py` - 11 tests for parsing, loop behavior, integration, and streaming

---

## v1.5: Parallel Execution with Progress
*January 2026*

### Overview
Run all models in parallel within each round with live progress spinners. Total round time = max(model times) instead of sum(model times).

### Implementation

**Backend (`backend/openrouter.py`):**
- `get_shared_client()` - Returns shared `httpx.AsyncClient` for connection reuse
- `close_shared_client()` - Clean shutdown of shared client
- `shared_client_context()` - Context manager for automatic cleanup
- Connection limits: `max_connections=20`, `max_keepalive_connections=10`

**Backend (`backend/council.py`):**
- `debate_round_streaming()` enhanced with:
  - `model_timeout` parameter (default: 120s)
  - `asyncio.wait_for()` for per-model timeout
  - `model_start` events emitted before parallel execution
  - `asyncio.as_completed()` for yielding results as they finish
- Error handling: `model_error` event with "Timeout" message on timeout

**CLI (`cli/main.py`):**
- `run_debate_parallel()` - Rich Live display with status table
- `build_model_panel()` - Moved to module level for shared use
- `build_status_table()` - Shows spinner status for each model
- Status states: "⠋ querying...", "✓ done", "✗ error"
- `--parallel` / `-p` flag for debate mode

### Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Timeout | Per-model 120s | Prevents single slow model from blocking |
| Connection reuse | Shared httpx.AsyncClient | Reduces connection overhead |
| Progress display | Rich Live + status table | Shows all models simultaneously |
| Event order | model_start first, then completions | CLI can show spinners before any completes |

### Tests
- `test_streaming_emits_model_start_events()` - Verifies model_start before completions
- `test_streaming_handles_model_timeout()` - Verifies timeout handling with model_error event

---

## v1.4: Token Streaming
*January 2026*

### Overview
Added token-by-token streaming for debate mode. Responses stream as they generate, then are replaced with rendered markdown panels. Also added streaming with tool calling support for web search during initial and defense rounds.

### Implementation

**Backend (`backend/openrouter.py`):**
- `query_model_streaming()` - Async generator yielding SSE tokens
- `query_model_streaming_with_tools()` - Streaming + tool calling combined
  - Uses `index` as primary key for tool call chunks (id only in first chunk)
  - Yields `tool_call` and `tool_result` events during search
- Parses `data: ` lines from OpenRouter streaming response
- Yields `{'type': 'token'}`, `{'type': 'done'}`, `{'type': 'error'}` events

**Backend (`backend/council.py`):**
- `debate_round_streaming()` - Model-completion streaming (parallel)
- `run_debate_council_streaming()` - Full debate with completion events
- `run_debate_token_streaming()` - Sequential token-by-token streaming
- `stream_round(with_tools=True)` - Generic round streaming with optional tool support
- Web search enabled in Round 1 (initial) and Round 3 (defense)

**CLI (`cli/main.py`):**
- `run_debate_streaming()` - Rich-based streaming display
- `track_output()` - Tracks terminal line wrapping for accurate clearing
- ANSI escape codes for cursor movement (`\033[{n}A\033[J`)
- Handles `tool_call` events to show "searching..." indicator
- Handles `tool_result` events to resume streaming display

**CLI (`cli/chat.py`):**
- `/stream on|off` command
- Streaming enabled by default with debate mode
- Updated prompt to show streaming state

### Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Streaming type | Token-by-token | More engaging than model-completion |
| Model order | Sequential | Parallel token streams would be chaotic |
| Display | Stream dimmed → replace with panel | Readable while streaming, clean final output |
| Line tracking | Count wraps | Terminal wrapping breaks naive newline counting |
| Tool call parsing | Use index as key | id only appears in first chunk of streamed tool calls |
| Defense search | Enabled | Models can find evidence to support their defense |

### Tests
- `test_streaming.py` - 10 tests for streaming event order, model identity, error handling, timeout

---

## v1.3: Interactive Chat with History
*January 2026*

### Overview
Added a chat-oriented CLI workflow with conversation history and slash commands.

### Implementation

**New file `cli/chat.py`:**
- `CHAT_COMMANDS` dictionary with `/help`, `/history`, `/use`, `/new`, `/debate`, `/rounds`, `/mode`, `/exit`
- `parse_chat_command()` - Parse slash commands with alias support (`/q` → `/exit`)
- `extract_conversation_pairs()` - Extract (user, assistant) pairs from stored messages
- `select_context_pairs()` - Select first + last N exchanges for context window
- `build_context_prompt()` - Format context for LLM queries

**Modified `cli/main.py`:**
- `chat` command with `--new` and `--max-turns` flags
- `run_chat_session()` - Interactive REPL loop
- Rich-themed output with custom color scheme
- Auto-resume most recent conversation on startup

### Tests

```
tests/
├── test_chat_commands.py         # 10 tests - command parsing, formatting
└── test_conversation_context.py  # 5 tests - context extraction, formatting
```

| Test File | Tests | Coverage |
|-----------|-------|----------|
| `test_chat_commands.py` | 10 | Command parsing, aliases, mode formatting |
| `test_conversation_context.py` | 5 | Pair extraction, context selection, prompt building |

### Features
- Auto-resume latest conversation or start fresh with `--new`
- Switch between ranking and debate modes mid-conversation
- Context window: first exchange + last N exchanges (default: 6)
- Shared storage with web UI (`data/conversations/`)

### Configuration
- Council model list trimmed to OpenAI, Grok, and DeepSeek
- Chairman set to OpenAI (`openai/gpt-5.2`)

---

## CI/CD Setup
*January 2026*

### Overview
Added GitHub Actions for automated testing on every push.

### Implementation
- `.github/workflows/test.yml` runs pytest on push/PR to master
- Dynamic badge in README shows real-time CI status
- Uses `astral-sh/setup-uv` for fast dependency installation

### Future
- Contract tests (daily scheduled runs to detect API drift)
- Pre-commit hooks for linting

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
├── conftest.py                  # Fixtures, mock API responses
├── test_chat_commands.py        # 10 tests
├── test_cli_imports.py          # 1 test
├── test_conversation_context.py # 5 tests
├── test_debate.py               # 15 tests
├── test_ranking_parser.py       # 14 tests
├── test_search.py               # 17 tests
├── test_streaming.py            # 10 tests
└── integration/                 # CLI tests (planned)
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
| Chat commands | 10 | Command parsing, aliases, mode formatting |
| Conversation context | 5 | Pair extraction, context selection |
| Streaming | 10 | Event order, model identity, error handling, timeout |
| CLI imports | 1 | Module import verification |

**Results:** 72 passed (parsing, tool calling, streaming, parallel, and chat logic)

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
