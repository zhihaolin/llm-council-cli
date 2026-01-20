# CLAUDE.md - Technical Notes for LLM Council

This file contains technical details, architectural decisions, and important implementation notes for future development sessions.

## Project Overview

LLM Council is a 3-stage deliberation system where multiple LLMs collaboratively answer user questions. The key innovation is anonymized peer review in Stage 2, preventing models from playing favorites.

## Architecture

### Backend Structure (`backend/`)

**`config.py`**
- Contains `COUNCIL_MODELS` (list of OpenRouter model identifiers)
- Contains `CHAIRMAN_MODEL` (model that synthesizes final answer)
- Uses environment variable `OPENROUTER_API_KEY` from `.env`
- Backend runs on **port 8001** (NOT 8000 - user had another app on 8000)

**`openrouter.py`**
- `query_model()`: Single async model query
- `query_models_parallel()`: Parallel queries using `asyncio.gather()`
- `query_model_with_tools()`: Query with tool/function calling support
  - Handles tool call loop: model requests tool → execute → return results → get final response
  - `max_tool_calls` parameter prevents infinite loops (default: 3)
  - Returns `tool_calls_made` list showing which tools were used
- Returns dict with 'content' and optional 'reasoning_details'
- Graceful degradation: returns None on failure, continues with successful responses

**`search.py`** - Web Search Integration
- `SEARCH_TOOL`: OpenAI-format tool definition for function calling
- `search_web(query)`: Async function to query Tavily API
- `format_search_results()`: Converts search results to LLM-readable text
- Requires `TAVILY_API_KEY` in `.env` (optional - gracefully degrades if missing)

**`council.py`** - The Core Logic
- `execute_tool()`: Dispatches tool calls to appropriate handlers (currently only `search_web`)
- `stage1_collect_responses()`: Parallel queries to all council models with tool support
  - Models receive `SEARCH_TOOL` and can autonomously decide when to search
  - Returns `tool_calls_made` for each model if any searches were performed
- `stage2_collect_rankings()`:
  - Anonymizes responses as "Response A, B, C, etc."
  - Creates `label_to_model` mapping for de-anonymization
  - Prompts models to evaluate and rank (with strict format requirements)
  - Returns tuple: (rankings_list, label_to_model_dict)
  - Each ranking includes both raw text and `parsed_ranking` list
- `stage3_synthesize_final()`: Chairman synthesizes from all responses + rankings
- `parse_ranking_from_text()`: Extracts "FINAL RANKING:" section, handles both numbered lists and plain format
- `calculate_aggregate_rankings()`: Computes average rank position across all peer evaluations

**`storage.py`**
- JSON-based conversation storage in `data/conversations/`
- Each conversation: `{id, created_at, messages[]}`
- Assistant messages contain: `{role, stage1, stage2, stage3}`
- Note: metadata (label_to_model, aggregate_rankings) is NOT persisted to storage, only returned via API

**`main.py`**
- FastAPI app with CORS enabled for localhost:5173 and localhost:3000
- POST `/api/conversations/{id}/message` returns metadata in addition to stages
- Metadata includes: label_to_model mapping and aggregate_rankings

### Frontend Structure (`frontend/src/`)

**`App.jsx`**
- Main orchestration: manages conversations list and current conversation
- Handles message sending and metadata storage
- Important: metadata is stored in the UI state for display but not persisted to backend JSON

**`components/ChatInterface.jsx`**
- Multiline textarea (3 rows, resizable)
- Enter to send, Shift+Enter for new line
- User messages wrapped in markdown-content class for padding

**`components/Stage1.jsx`**
- Tab view of individual model responses
- ReactMarkdown rendering with markdown-content wrapper

**`components/Stage2.jsx`**
- **Critical Feature**: Tab view showing RAW evaluation text from each model
- De-anonymization happens CLIENT-SIDE for display (models receive anonymous labels)
- Shows "Extracted Ranking" below each evaluation so users can validate parsing
- Aggregate rankings shown with average position and vote count
- Explanatory text clarifies that boldface model names are for readability only

**`components/Stage3.jsx`**
- Final synthesized answer from chairman
- Green-tinted background (#f0fff0) to highlight conclusion

**Styling (`*.css`)**
- Light mode theme (not dark mode)
- Primary color: #4a90e2 (blue)
- Global markdown styling in `index.css` with `.markdown-content` class
- 12px padding on all markdown content to prevent cluttered appearance

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
- Frontend displays model names in **bold** for readability
- Users see explanation that original evaluation used anonymous labels
- This prevents bias while maintaining transparency

### Error Handling Philosophy
- Continue with successful responses if some models fail (graceful degradation)
- Never fail the entire request due to single model failure
- Log errors but don't expose to user unless all models fail

### UI/UX Transparency
- All raw outputs are inspectable via tabs
- Parsed rankings shown below raw text for validation
- Users can verify system's interpretation of model outputs
- This builds trust and allows debugging of edge cases

## Important Implementation Details

### Relative Imports
All backend modules use relative imports (e.g., `from .config import ...`) not absolute imports. This is critical for Python's module system to work correctly when running as `python -m backend.main`.

### Port Configuration
- Backend: 8001 (changed from 8000 to avoid conflict)
- Frontend: 5173 (Vite default)
- Update both `backend/main.py` and `frontend/src/api.js` if changing

### Markdown Rendering
All ReactMarkdown components must be wrapped in `<div className="markdown-content">` for proper spacing. This class is defined globally in `index.css`.

### Model Configuration
Models are hardcoded in `backend/config.py`. Chairman can be same or different from council members. The current default is Gemini as chairman per user preference.

## Web Search / Tool Calling

### How It Works
Models in Stage 1 receive a `search_web` tool definition. They autonomously decide when to use it based on the query:
- Questions about current events, prices, weather → model calls search
- General knowledge questions → model answers directly

### Tool Calling Flow
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

### Debate Functions in `council.py`

**`debate_round_critique(query, initial_responses)`**
- Each model receives all responses and critiques the others
- Models are told their own model name so they skip self-critique
- Prompt requests structured format: `## Critique of [Model Name]`

**`extract_critiques_for_model(target_model, critique_responses)`**
- Parses all critique responses to find sections about a specific model
- Uses regex to match `## Critique of [model_name]` headers
- Returns concatenated critiques with attribution

**`debate_round_defense(query, initial_responses, critique_responses)`**
- Each model receives their original response + all critiques of them
- Prompt requests: "Addressing Critiques" + "Revised Response" sections
- Returns both full response and parsed `revised_answer`

**`parse_revised_answer(defense_response)`**
- Extracts content after `## Revised Response` header
- Falls back to full response if section not found

**`synthesize_debate(query, rounds, num_rounds)`**
- Chairman receives full debate transcript
- Considers evolution of arguments, valid critiques, consensus points
- Produces final synthesized answer

**`run_debate_council(query, max_rounds)`**
- Orchestrates complete debate flow
- `max_rounds=2` produces 3 interaction rounds (initial, critique, defense)
- Additional rounds alternate between critique and defense

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

# Storage format (backend/storage.py)
{
    "role": "assistant",
    "mode": "debate",
    "rounds": [...],
    "synthesis": {"model": "...", "response": "..."}
}
```

### CLI Display Functions in `main.py`

**`print_debate_round(round_data, round_num)`**
- Color-coded by round type (cyan=initial, yellow=critique, magenta=defense)
- Shows each model's response in a Rich panel
- Includes `• searched` indicator if model used web search

**`print_debate_synthesis(synthesis)`**
- Green-styled panel for final answer
- Same format as Stage 3 synthesis

**`run_debate_with_progress(query, max_rounds)`**
- Progress spinners for each round
- Reports completion status after each round

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

## Common Gotchas

1. **Module Import Errors**: Always run backend as `python -m backend.main` from project root, not from backend directory
2. **CORS Issues**: Frontend must match allowed origins in `main.py` CORS middleware
3. **Ranking Parse Failures**: If models don't follow format, fallback regex extracts any "Response X" patterns in order
4. **Missing Metadata**: Metadata is ephemeral (not persisted), only available in API responses
5. **Web Search Not Working**: Check that `TAVILY_API_KEY` is set in `.env`. Models will say "search not available" if missing
6. **Max Tool Calls**: If a model keeps calling tools without responding, it hits `max_tool_calls` limit (default 10)

## Future Enhancement Ideas

- Configurable council/chairman via UI instead of config file
- Streaming responses instead of batch loading
- Export conversations to markdown/PDF
- Model performance analytics over time
- Custom ranking criteria (not just accuracy/insight)
- Support for reasoning models (o1, etc.) with special handling

## Testing Notes

Use `test_openrouter.py` to verify API connectivity and test different model identifiers before adding to council. The script tests both streaming and non-streaming modes.

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
Frontend/CLI: Display with tabs + validation UI
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
