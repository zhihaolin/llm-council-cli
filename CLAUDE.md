# CLAUDE.md - Technical Notes for LLM Council

This file contains technical details, architectural decisions, and important implementation notes for future development sessions.

## Core Engineering Principles (SACROSANCT)

These principles are non-negotiable for this project:

### 1. SOLID
- **S**ingle Responsibility: Each module/class has one reason to change
- **O**pen/Closed: Extend behavior without modifying existing code
- **L**iskov Substitution: Subtypes must be substitutable for base types
- **I**nterface Segregation: Small, focused interfaces over large ones
- **D**ependency Inversion: Depend on abstractions, not concretions

### 2. TDD (Test-Driven Development)
- Write tests BEFORE implementation
- Red → Green → Refactor cycle
- Tests document expected behavior
- No production code without a failing test first

### 3. TBD (Trunk-Based Development)
- Small, frequent commits to master/trunk
- Each commit must pass all tests
- Each commit should be independently deployable
- No long-lived feature branches
- For refactors: use Branch by Abstraction
  1. Add new structure alongside old
  2. Migrate incrementally (each commit passes tests)
  3. Remove old code only after full migration

### 4. Green CI, Always
- CI must be passing at all times
- Never merge/push code that breaks CI
- If CI breaks, fixing it is the top priority

### 5. Trunk is Always Deployable
- Master/trunk must be in a deployable state at any point in time
- No "work in progress" commits that break functionality
- Feature flags over feature branches for incomplete work

### 6. YAGNI (You Ain't Gonna Need It)
- Only build what's needed now
- Remove unused code and dependencies
- Avoid speculative features

### 7. Configuration over Code
- User-editable settings in config files (YAML), not hardcoded
- Secrets in environment variables, never in config files or code

### 8. Small Atomic Commits
- Each commit is focused on one change
- Each commit passes all tests
- Easy to review, revert, and bisect

### 9. Docs Stay Current (AI-Assisted Coding)
- Update documentation with every code change
- AI assistants lose context between sessions
- Stale docs cause repeated mistakes

### 10. DRY is Not Absolute
- Don't abstract until you've repeated something 3+ times (Rule of Three)
- Premature DRY creates tight coupling between unrelated code
- Sometimes 3 similar lines is better than 1 clever abstraction
- Duplication is cheaper than the wrong abstraction

**When refactoring**: Never make large, sweeping changes in a single commit. Break into small, safe steps.

---

## Project Overview

LLM Council orchestrates multiple LLMs to collaboratively answer questions through structured deliberation.

**Two modes:**
- **Ranking mode** (default): 3-stage flow - responses → anonymous peer ranking → chairman synthesis
- **Debate mode** (`--debate`): Multi-round deliberation - initial → critique → defense → synthesis

Both modes use a chairman model (configurable) to synthesize the final answer.

## Architecture

### Backend Structure (`llm_council/`)

**`settings.py`**
- Loads settings from `config.yaml` in project root (falls back to defaults if missing)
- Exports: `COUNCIL_MODELS`, `CHAIRMAN_MODEL`, `OPENROUTER_API_URL`, `DATA_DIR`
- API key loaded from environment variable `OPENROUTER_API_KEY` (never in YAML)

**`config.yaml`** (project root)
- User-editable configuration file
- Settings: `council_models`, `chairman_model`, `openrouter_api_url`, `data_dir`
- Optional - defaults are built into `settings.py`

**`adapters/openrouter_client.py`**
- `query_model()`: Single async model query
- `query_models_parallel()`: Parallel queries using `asyncio.gather()`
- `query_model_with_tools()`: Query with tool/function calling support
  - Handles tool call loop: model requests tool → execute → return results → get final response
  - `max_tool_calls` parameter prevents infinite loops (default: 3; streaming variant defaults to 10)
  - Returns `tool_calls_made` list showing which tools were used
- Returns dict with 'content' and optional 'reasoning_details'
- Graceful degradation: returns None on failure, continues with successful responses

**`adapters/tavily_search.py`** - Web Search Integration
- `SEARCH_TOOL`: OpenAI-format tool definition for function calling
- `search_web(query)`: Async function to query Tavily API
- `format_search_results()`: Converts search results to LLM-readable text
- Requires `TAVILY_API_KEY` in `.env` (optional - gracefully degrades if missing)

**`engine/`** - The Core Logic (v1.6.1 modular structure)

```
llm_council/engine/
├── __init__.py             # Public API exports (backward compatible)
├── ranking.py              # Stage 1-2-3 flow
├── debate.py               # Debate orchestration + async execution strategies
├── react.py                # ReAct chairman logic
├── prompts.py              # All prompt templates
├── parsers.py              # Regex/text parsing utilities
└── aggregation.py          # Ranking calculations
```

Key functions (all exported from `llm_council.engine`):
- `stage1_collect_responses()`: Parallel queries to all council models with tool support
- `stage2_collect_rankings()`: Anonymizes responses and collects peer rankings
- `stage3_synthesize_final()`: Chairman synthesizes from all responses + rankings
- `run_full_council()`: Orchestrates the complete 3-stage flow
- `run_debate()`: Single orchestrator defining debate round sequence, delegates to executor callback
- `debate_round_parallel()`: Execute-round strategy — parallel with per-model events
- `debate_round_streaming()`: Execute-round strategy — sequential with per-token events
- `run_debate_parallel()`: Full debate flow using parallel executor + synthesis
- `run_debate_streaming()`: Full debate flow using streaming executor + synthesis
- `synthesize_with_react()`: ReAct reasoning loop for chairman
- `parse_ranking_from_text()`: Extracts "FINAL RANKING:" section
- `calculate_aggregate_rankings()`: Computes average rank position

**`adapters/json_storage.py`**
- JSON-based conversation storage in `data/conversations/`
- Each conversation: `{id, created_at, messages[]}`
- Assistant messages contain: `{role, stage1, stage2, stage3}`
- Note: metadata (label_to_model, aggregate_rankings) is NOT persisted to storage

## Key Design Decisions

### Stage 2 Prompt Format
The Stage 2 prompt is very specific to ensure parseable output:
```
1. Evaluate each response individually first
2. Provide "FINAL RANKING:" header
3. Numbered list format: "1. Response C", "2. Response A", etc.
4. No additional text after ranking section
```

This strict format allows reliable parsing while still getting thoughtful evaluations.

### De-anonymization Strategy
- Models receive: "Response A", "Response B", etc.
- Backend creates mapping: `{"Response A": "openai/gpt-5.1", ...}`
- CLI displays de-anonymized model names for readability
- This prevents bias during evaluation while maintaining transparency in output

### Error Handling Philosophy
- Continue with successful responses if some models fail (graceful degradation)
- Never fail the entire request due to single model failure
- Log errors but don't expose to user unless all models fail

### CLI/UX Transparency
- Parsed rankings shown below raw text for validation
- Users can verify system's interpretation of model outputs
- This builds trust and allows debugging of edge cases

## Important Implementation Details

### Relative Imports
All backend modules use relative imports (e.g., `from .config import ...`) not absolute imports. This is critical for Python's module system to work correctly.

### Model Configuration
Models are configured in `config.yaml` (project root). Chairman can be same or different from council members.

## Web Search / Tool Calling

### How It Works
Models receive a `search_web` tool definition and autonomously decide when to use it:
- Questions about current events, prices, weather → model calls search
- General knowledge questions → model answers directly

**Rounds with search enabled** (consistent across batch, parallel, and token-streaming modes):
- **Round 1 (Initial):** Models can search to gather facts for their initial response
- **Round 3 (Defense):** Models can search to find evidence supporting their defense

Round 2 (Critique) does not have search — models critique existing responses without introducing new facts.

### Tool Calling Flow
```
1. Send request to OpenRouter with tools=[SEARCH_TOOL], stream=True
2. Stream response tokens, accumulating any tool_calls chunks
3. If tool_calls detected:
   a. Parse arguments (using index as key - id only in first chunk)
   b. Execute search_web(query) → Tavily API
   c. Send tool result back to model
   d. Continue streaming final response
4. Yield done event with full content and tool_calls_made
```

### Configuration
- Requires `TAVILY_API_KEY` in `.env`
- Free tier: 1000 searches/month at [tavily.com](https://tavily.com)
- If key is missing, models gracefully acknowledge they can't search

## Debate Mode

### Overview
Debate mode replaces the standard ranking flow with multi-round deliberation where models critique and defend positions.

**Standard flow:** Stage 1 (answers) → Stage 2 (rank) → Stage 3 (synthesize)

**Debate flow:** Round 1 (answers) → Round 2 (critique all) → Round 3 (defend/revise) → Chairman synthesis

### CLI Usage
```bash
llm-council --debate "Question"                    # 2 rounds (default)
llm-council --debate --rounds 3 "Complex question" # 3 rounds
llm-council --debate --simple "Question"           # Just final answer
```

### Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Attribution | Named (not anonymous) | Need to track who said what across rounds |
| Critique scope | All-to-all | Each model critiques all others |
| Defense format | Structured sections | Easy to parse revised answers |
| Default rounds | 2 | Sufficient for most questions |

### Debate Functions (in `llm_council/engine/debate.py`)

**Per-model query functions** (used by both parallel and streaming executors):

**`query_initial(model, user_query)`** — Round 1 for a single model
- Uses `query_model_with_tools()` (web search enabled)
- Returns `{"model": ..., "response": ..., "tool_calls_made": ...}` or `None`

**`query_critique(model, user_query, initial_responses)`** — Round 2 for a single model
- Uses `query_model()` (no tools — critiques evaluate existing responses)
- Returns `{"model": ..., "response": ...}` or `None`

**`query_defense(model, user_query, initial_responses, critique_responses)`** — Round 3 for a single model
- Uses `query_model_with_tools()` (web search enabled for evidence gathering)
- Returns `{"model": ..., "response": ..., "revised_answer": ..., "tool_calls_made": ...}` or `None`

**Orchestrator and execution strategies** (also in `debate.py`):

**`run_debate(user_query, execute_round, max_rounds)`**
- Single orchestrator defining debate round sequence once
- Delegates execution to `execute_round` callback (strategy pattern)
- `max_rounds=2` produces 3 interaction rounds (initial, critique, defense)
- Yields: `round_start` → (pass-through events from executor) → `round_complete` → ... → `debate_complete`
- Does NOT handle synthesis (each mode does it differently)

### Parsing Functions (in `llm_council/engine/parsers.py`)

**`extract_critiques_for_model(target_model, critique_responses)`**
- Parses all critique responses to find sections about a specific model
- Uses regex to match `## Critique of [model_name]` headers

**`parse_revised_answer(defense_response)`**
- Extracts content after `## Revised Response` header
- Falls back to full response if section not found

**`parse_react_output(text)`**
- Extracts Thought/Action from ReAct model output

### Debate Data Structure

```python
# Round data format
{
    "round_number": 1,
    "round_type": "initial",  # or "critique" or "defense"
    "responses": [
        {
            "model": "openai/gpt-5.2",
            "response": "...",
            "revised_answer": "..."  # Only for defense rounds
        }
    ]
}

# Storage format (llm_council/adapters/json_storage.py)
{
    "role": "assistant",
    "mode": "debate",
    "rounds": [...],
    "synthesis": {"model": "...", "response": "..."}
}
```

### CLI Structure (v1.6.1 modular)

```
llm_council/cli/
├── main.py           # Command routing only
├── presenters.py     # All print_* display functions
├── runners.py        # run_* execution with progress
├── chat_session.py   # Chat REPL logic
├── chat_commands.py  # Command parsing utilities
├── tui.py            # Textual TUI app
└── constants.py      # Constants
```

**Display functions (in `llm_council/cli/presenters.py`):**
- `print_debate_round()` - Color-coded by round type
- `print_debate_synthesis()` - Green-styled panel for final answer
- `print_stage1/2/3()` - Standard mode output

**Runners (in `llm_council/cli/runners.py`):**
- `run_debate_with_progress()` - Consumes `run_debate` events with progress spinners
- `run_debate_parallel()` - Parallel execution with Rich Live display
- `run_debate_streaming()` - Token streaming with line wrap tracking
- `run_react_synthesis()` - ReAct trace display

### API Costs
| Mode | API Calls (5 models) |
|------|---------------------|
| Standard (ranking) | 11 calls |
| Debate (2 rounds) | 16 calls |
| Debate (3 rounds) | 21 calls |

### Error Handling
- Model fails during round: continue with remaining models
- Critique parsing fails: use full response text
- <2 models respond: abort debate, return error

## Streaming Mode

### Overview
Streaming mode shows model responses as they're generated, with token-by-token streaming. Each model processes sequentially (not in parallel) to provide a readable streaming experience.

**Default behavior:** Streaming is enabled by default in chat REPL with debate mode.

### How It Works
1. Models are processed one at a time (sequential, not parallel)
2. Tokens are displayed in dimmed grey as they arrive
3. When a model completes, the streaming text is cleared and replaced with a rendered markdown panel
4. The clearing accounts for terminal line wrapping to ensure clean replacement

### CLI Usage
```bash
llm-council query --stream "Question"          # Single query with streaming
llm-council chat                               # REPL (streaming+debate on by default)
```

### Chat REPL Commands
- `/stream on` - Enable streaming mode
- `/stream off` - Disable streaming mode
- `/mode` - Show current mode (streaming indicator shown if enabled)

### Streaming Functions

**`llm_council/adapters/openrouter_client.py`**
- `query_model_streaming()`: Async generator that yields SSE tokens
  - Yields `{'type': 'token', 'content': str}` for each token
  - Yields `{'type': 'done', 'content': str}` when complete
  - Yields `{'type': 'error', 'error': str}` on failure
- `query_model_streaming_with_tools()`: Streaming with tool calling support
  - Combines token streaming with function calling (used for initial round with web search)
  - Yields `{'type': 'tool_call', 'tool': str, 'args': dict}` when model calls a tool
  - Yields `{'type': 'tool_result', 'tool': str, 'result': str}` after tool execution
  - Uses `index` as primary key for tool call chunks (id only in first chunk)

**`llm_council/engine/debate.py`** (orchestration and execution strategies)
- `run_debate()`: Single orchestrator — defines round sequence once, delegates to executor callback
- `debate_round_parallel()`: Execute-round strategy — parallel with per-model events
- `debate_round_streaming()`: Execute-round strategy — sequential with per-token events
- `run_debate_parallel()`: Full debate using `run_debate(debate_round_parallel)` + synthesis
- `run_debate_streaming()`: Full debate using `run_debate(debate_round_streaming)` + synthesis

**`llm_council/cli/runners.py`**
- `run_debate_streaming()`: Renders streaming output with Rich
  - Tracks terminal line wrapping for accurate clearing
  - Uses ANSI escape codes for cursor movement
  - Shows dimmed text while streaming, then replaces with markdown panel

### Key Implementation Details

**Line Wrapping Tracking:**
```python
def track_output(text: str):
    """Track line count including terminal wrapping."""
    nonlocal line_count, current_col
    for char in text:
        if char == "\n":
            line_count += 1
            current_col = 0
        else:
            current_col += 1
            if current_col >= terminal_width:
                line_count += 1
                current_col = 0
```

**Clearing Streaming Output:**
```python
def clear_streaming_output():
    if line_count > 0:
        sys.stdout.write(f"\033[{line_count}A\033[J")
        sys.stdout.flush()
```

## Common Gotchas

1. **Module Import Errors**: Always run via `uv run llm-council` (not `python -m llm_council.cli`). The project is packaged (`[tool.uv] package = true`), so `llm_council` is on the Python path automatically. Backend modules use relative imports internally (e.g., `from ..settings import ...`)
2. **Ranking Parse Failures**: If models don't follow format, fallback regex extracts any "Response X" patterns in order
3. **Missing Metadata**: Metadata is ephemeral (not persisted), only returned in results
4. **Web Search Not Working**: Check that `TAVILY_API_KEY` is set in `.env`. Models will say "search not available" if missing
5. **Max Tool Calls**: If a model keeps calling tools without responding, it hits `max_tool_calls` limit (default 3 for non-streaming, 10 for streaming)
6. **Debate Round Sequence**: The round sequence (initial → critique → defense → extra rounds) is defined once in `run_debate()`. Execution is delegated to either `debate_round_parallel()` or `debate_round_streaming()`. All debate logic (per-model queries, orchestrator, execution strategies) lives in `debate.py`

## Known Technical Debt

Issues identified but not yet on the roadmap. Fix opportunistically or when touching related code.

| Issue | Location | Severity | Notes |
|-------|----------|----------|-------|
| Off-by-one in tool call loops | `adapters/openrouter_client.py` | Medium | Streaming uses `range(max_tool_calls + 1)`, non-streaming uses `range(max_tool_calls)` — inconsistent |
| `datetime.utcnow()` deprecated | `adapters/json_storage.py` | Low | Deprecated since Python 3.12; use `datetime.now(datetime.UTC)` |
| Hardcoded title generation model | `engine/ranking.py` | Medium | `"google/gemini-2.5-flash"` should be configurable; breaks if model retired |
| Redundant import | `adapters/openrouter_client.py` | Trivial | `import asyncio` inside function, already imported at top |
| Shared HTTP client unused | `adapters/openrouter_client.py` | Low | `get_shared_client()` defined but never called; each query creates new client |

## Future Enhancements

See [docs/PLAN.md](docs/PLAN.md) for the full roadmap (v1.9+).

## Testing

### Test Suite (91 tests)
```
tests/
├── conftest.py                  # Fixtures and mock API responses
├── test_chat_commands.py        # 10 tests - chat REPL command parsing
├── test_cli_imports.py          # 1 test - CLI module imports
├── test_conversation_context.py # 5 tests - conversation context handling
├── test_debate.py               # 16 tests - debate mode
├── test_ranking_parser.py       # 14 tests - ranking extraction
├── test_react.py                # 12 tests - ReAct chairman parsing & loop
├── test_search.py               # 17 tests - web search & tool calling
├── test_streaming.py            # 13 tests - streaming, parallel, orchestrator
└── integration/                 # CLI tests (planned)
```

### Running Tests
```bash
uv run pytest tests/ -v
```

### CI/CD
- GitHub Actions runs on every push to master
- Workflow: `.github/workflows/test.yml`
- Pipeline: `lint` → `test` → `docker` (build + smoke test)
- Docker job builds the image and runs `--help` to verify entrypoint and imports
- Badge in README shows real-time CI status

### Manual API Testing
Use `test_openrouter.py` to verify API connectivity and test different model identifiers before adding to council.

## Docker

### Build
```bash
docker build -t llm-council .
```

### Run
```bash
# Simple query
docker run -e OPENROUTER_API_KEY=your-key llm-council query "What is 2+2?"

# Interactive REPL (needs -it flags)
docker run -it -e OPENROUTER_API_KEY=your-key -e TAVILY_API_KEY=your-key llm-council chat

# Debate mode
docker run -e OPENROUTER_API_KEY=your-key llm-council query --debate "Should AI be regulated?"
```

### Notes
- Image is self-contained, can run from anywhere
- `-it` flags required for interactive mode (chat REPL)
- `TAVILY_API_KEY` optional, enables web search

## Data Flow Summary

### Standard Mode (Ranking)
```
User Query
    ↓
Stage 1: Parallel queries with tools=[SEARCH_TOOL]
    ├── Model decides: needs current info → calls search_web → Tavily API
    └── Model decides: knows answer → direct response
    ↓
[individual responses + tool_calls_made]
    ↓
Stage 2: Anonymize → Parallel ranking queries → [evaluations + parsed rankings]
    ↓
Aggregate Rankings Calculation → [sorted by avg position]
    ↓
Stage 3: Chairman synthesis with full context
    ↓
Return: {stage1, stage2, stage3, metadata}
    ↓
CLI: Display with formatted output
```

### Debate Mode
```
User Query (--debate flag)
    ↓
Round 1: Parallel queries with tools=[SEARCH_TOOL]
    ↓
[initial responses + tool_calls_made]
    ↓
Round 2: Each model critiques all others (parallel)
    ↓
[critique responses with ## Critique of [Model] sections]
    ↓
Round 3: Each model defends/revises (parallel)
    ├── Receives: own original response + critiques of self
    └── Outputs: ## Addressing Critiques + ## Revised Response
    ↓
[defense responses with revised_answer extracted]
    ↓
(Optional: additional critique/defense rounds if --rounds > 2)
    ↓
Chairman synthesis with full debate transcript
    ↓
Return: {rounds: [...], synthesis: {...}}
    ↓
CLI: Display rounds with color-coded headers + synthesis
```

The entire flow is async/parallel where possible to minimize latency.

## Parallel Execution Mode

### Overview
The `--parallel` flag runs all models concurrently within each round, showing live progress spinners. This dramatically reduces total time (max(model times) instead of sum).

### CLI Usage
```bash
llm-council query --debate --parallel "Question"   # Parallel with spinners
llm-council query --debate --stream "Question"     # Sequential with token streaming
```

### Implementation

**Shared HTTP Client (`llm_council/adapters/openrouter_client.py`):**
```python
_shared_client: Optional[httpx.AsyncClient] = None
_client_lock = asyncio.Lock()

async def get_shared_client() -> httpx.AsyncClient:
    """Get or create a shared httpx.AsyncClient for connection reuse."""
    global _shared_client
    async with _client_lock:
        if _shared_client is None or _shared_client.is_closed:
            _shared_client = httpx.AsyncClient(
                timeout=DEFAULT_TIMEOUT,
                limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
            )
        return _shared_client
```

**Per-model Timeout (`llm_council/engine/debate.py`):**
```python
async def query_with_model(model: str):
    try:
        result = await asyncio.wait_for(
            query_funcs[model](model),
            timeout=model_timeout  # Default: 120s
        )
        return model, result, None
    except asyncio.TimeoutError:
        return model, None, f"Timeout after {model_timeout}s"
```

**Event Flow:**
```
1. round_start event
2. model_start events for all models (CLI shows spinners)
3. model_complete/model_error events as each finishes
4. round_complete event with all responses
5. Repeat for each round
6. synthesis_start → synthesis_complete → complete
```

### CLI Display (`llm_council/cli/runners.py`)
- `run_debate_parallel()` uses Rich `Live` display with a status table
- Status states: "⠋ thinking..." → "✓ done" / "✗ error"
- Panels appear as models complete (fastest first)

## ReAct Chairman

### Overview
The chairman uses the ReAct (Reasoning + Acting) pattern to synthesize final answers. This allows fact verification before synthesis.

**Pattern:** Thought → Action → Observation → Repeat (max 3 iterations)

**Available tools:**
- `search_web(query)` - Verify facts or get current information
- `synthesize()` - Produce final answer (terminal action)

### CLI Usage
```bash
llm-council query --debate "Question"         # ReAct enabled by default
llm-council query --debate --no-react "Q"     # Disable ReAct
```

### Chat REPL Commands
- `/react on` - Enable ReAct reasoning
- `/react off` - Disable ReAct reasoning
- `/mode` - Show current mode (includes `[react]` indicator)

### Example Output
```
━━━ CHAIRMAN'S REASONING ━━━

Thought: The responses disagree on the current Bitcoin price. I should verify.

Action: search_web("bitcoin price today")

Observation: Bitcoin is currently trading at $67,234...

Thought: Now I can synthesize with verified data.

Action: synthesize()

━━━ CHAIRMAN'S SYNTHESIS ━━━

[Final answer panel]
```

### Implementation

**`llm_council/engine/react.py`:**
- `synthesize_with_react()` - Async generator implementing the ReAct loop
  - Yields: `token`, `thought`, `action`, `observation`, `synthesis` events
  - Max 3 iterations to prevent infinite loops
  - If model says `synthesize()` without content, asks for synthesis directly

**`llm_council/engine/prompts.py`:**
- `build_react_context_ranking()` - Formats Stage 1/2 results for chairman
- `build_react_context_debate()` - Formats debate rounds for chairman
- `build_react_prompt()` - Constructs ReAct system prompt with tool descriptions

**`llm_council/engine/parsers.py`:**
- `parse_react_output()` - Extracts Thought/Action from model output using regex

**`llm_council/cli/runners.py`:**
- `run_react_synthesis()` - Displays ReAct trace with color coding
  - Thought: cyan
  - Action: yellow
  - Observation: dim
- Works with parallel, streaming, and batch modes

### Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Default state | Enabled | Most questions benefit from potential fact verification |
| Max iterations | 3 | Prevents infinite search loops |
| Streaming | Trace only | Token streaming for Thought/Action would be noisy |
| Empty synthesize() | Re-prompt | Model sometimes forgets to provide answer after action |
