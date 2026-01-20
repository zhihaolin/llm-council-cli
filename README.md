# LLM Council

**Multi-model deliberation for better answers.**

A system where AI models debate, critique, and synthesize answers together.

Instead of asking one LLM and hoping for the best, LLM Council orchestrates multiple frontier models through structured deliberation—producing more accurate, nuanced, and well-reasoned answers.

![Chairman synthesis after multi-round debate](images/hero.png)

## Why This Exists

Single-model responses have blind spots. LLM Council fixes this by:

1. **Consulting multiple models** — GPT, Claude, Gemini, Grok, and DeepSeek all weigh in
2. **Anonymous peer review** — Models rank each other's responses without knowing who wrote what (prevents favoritism)
3. **Structured debate** — Models critique and defend positions across multiple rounds
4. **Chairman synthesis** — A designated model synthesizes the collective wisdom into one answer

The result? Answers that capture the best insights from each model while filtering out individual weaknesses.

---

## Features

### Multi-Model Deliberation

Query 5 frontier models in parallel. Each provides an independent response, then anonymously evaluates the others. A chairman model synthesizes the final answer based on the full deliberation.

```
Stage 1: Independent Responses    →  5 models answer your question
Stage 2: Anonymous Peer Review    →  Each model ranks the others (blind)
Stage 3: Chairman Synthesis       →  Best insights combined into final answer
```

### Debate Mode

For complex or controversial questions, enable multi-round debate where models critique each other's reasoning and defend their positions.

```bash
llm-council --debate "Is capitalism or socialism better for reducing poverty?"
llm-council --debate --rounds 3 "Should AI development be paused?"
```

```
Round 1: Initial Responses    →  Each model presents their position
Round 2: Critiques            →  Models challenge each other's arguments
Round 3: Defense & Revision   →  Models defend valid points, concede weaknesses
Final:   Chairman Synthesis   →  Synthesizes the evolved positions
```

![Models critiquing each other in debate mode](images/debate.png)

### Autonomous Web Search

Models decide when they need current information. No manual flags—they call the search tool when the question requires it.

```bash
llm-council "What is the current price of Bitcoin?"
# Models automatically search for real-time data
```

The CLI shows which models used search with a subtle `• searched` indicator.

![Models autonomously searching for current information](images/search.png)

### Rich Terminal Interface

- **CLI mode** — Full 3-stage output with progress indicators
- **Simple mode** — Just the final answer, pipe-friendly
- **Interactive TUI** — Terminal UI with keyboard navigation

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         User Query                               │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│              Stage 1: Parallel Model Queries                     │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐   │
│  │ GPT-5.2 │ │ Gemini  │ │ Claude  │ │  Grok   │ │DeepSeek │   │
│  │         │ │  3 Pro  │ │Sonnet4.5│ │4.1 Fast │ │   R1    │   │
│  └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘   │
│       │           │           │           │           │         │
│       └───────────┴─────┬─────┴───────────┴───────────┘         │
│                         │                                        │
│              ┌──────────▼──────────┐                            │
│              │   Web Search Tool   │  (Tavily API)              │
│              │  Models call when   │                            │
│              │  they need current  │                            │
│              │    information      │                            │
│              └─────────────────────┘                            │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│              Stage 2: Anonymous Peer Review                      │
│                                                                  │
│   Responses anonymized as "Response A, B, C, D, E"              │
│   Each model ranks all responses (can't identify authors)        │
│   Aggregate rankings computed from all evaluations               │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│              Stage 3: Chairman Synthesis                         │
│                                                                  │
│   Chairman model receives:                                       │
│   - All original responses                                       │
│   - All peer evaluations                                         │
│   - Aggregate rankings                                           │
│                                                                  │
│   Produces: Single comprehensive answer                          │
└─────────────────────────────────────────────────────────────────┘
```

### Debate Mode Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│  Round 1: Initial        Round 2: Critique       Round 3: Defend │
│  ┌─────┐ ┌─────┐        ┌─────┐ ┌─────┐        ┌─────┐ ┌─────┐  │
│  │Model│ │Model│   →    │  A  │→│  B  │   →    │Revise│ │Revise│ │
│  │  A  │ │  B  │        │critiques B,C,D│        │  A   │ │  B   │ │
│  └─────┘ └─────┘        └─────┘ └─────┘        └─────┘ └─────┘  │
│  ┌─────┐ ┌─────┐        ┌─────┐ ┌─────┐        ┌─────┐ ┌─────┐  │
│  │Model│ │Model│   →    │  C  │→│  D  │   →    │Revise│ │Revise│ │
│  │  C  │ │  D  │        │critiques A,B,D│        │  C   │ │  D   │ │
│  └─────┘ └─────┘        └─────┘ └─────┘        └─────┘ └─────┘  │
└──────────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │    Chairman     │
                    │   Synthesizes   │
                    │  Full Debate    │
                    └─────────────────┘
```

---

## Quick Start

### 1. Clone and Install

```bash
git clone https://github.com/zhihaolin/llm-council-cli.git
cd llm-council-cli

# Install uv if you don't have it
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dependencies
uv sync
```

### 2. Configure API Keys

```bash
# Required: OpenRouter API key (access to all models via one API)
echo "OPENROUTER_API_KEY=sk-or-v1-your-key-here" > .env

# Optional: Tavily API key for web search
echo "TAVILY_API_KEY=tvly-your-key-here" >> .env
```

Get your API keys:
- [openrouter.ai](https://openrouter.ai/) — Required, provides access to GPT, Claude, Gemini, etc.
- [tavily.com](https://tavily.com/) — Optional, enables web search (free tier: 1000 searches/month)

### 3. Query the Council

```bash
# Standard deliberation (all 3 stages)
uv run python -m cli query "What is the best programming language for beginners?"

# Debate mode (models critique each other)
uv run python -m cli query --debate "Should AI be regulated?"

# Simple output (just the final answer)
uv run python -m cli query --simple "What is 2+2?"
```

---

## CLI Usage

### Commands

```bash
# Query with full deliberation output
uv run python -m cli query "Your question"

# Query with debate mode
uv run python -m cli query --debate "Complex question"
uv run python -m cli query --debate --rounds 3 "Very complex question"

# Simple output (final answer only, no stages)
uv run python -m cli query --simple "Quick question"

# Final answer with formatting (skip stages 1 & 2)
uv run python -m cli query --final-only "Question"

# Show current council configuration
uv run python -m cli models

# Interactive TUI
uv run python -m cli interactive
```

### Flags

| Flag | Short | Description |
|------|-------|-------------|
| `--simple` | `-s` | Output only the final answer (no formatting) |
| `--final-only` | `-f` | Show only chairman's synthesis (with formatting) |
| `--debate` | `-d` | Enable debate mode |
| `--rounds N` | `-r N` | Number of debate rounds (default: 2) |

---

## Web UI

A React-based web interface is also available:

```bash
# Start both backend and frontend
./start.sh

# Or manually:
# Terminal 1: uv run python -m backend.main
# Terminal 2: cd frontend && npm run dev
```

Then open http://localhost:5173

---

## Configuration

### Models

Edit `backend/config.py` to customize the council:

```python
COUNCIL_MODELS = [
    "openai/gpt-5.2",
    "google/gemini-3-pro-preview",
    "anthropic/claude-sonnet-4.5",
    "x-ai/grok-4.1-fast",
    "deepseek/deepseek-r1-0528",
]

CHAIRMAN_MODEL = "google/gemini-3-pro-preview"
```

All models are accessed through [OpenRouter](https://openrouter.ai/), which provides a unified API for multiple providers.

---

## Tech Stack

| Component | Technology |
|-----------|------------|
| Backend | Python 3.10+, FastAPI, async httpx |
| CLI | Typer, Rich, Textual |
| Frontend | React, Vite, react-markdown |
| LLM Access | OpenRouter API (unified access to GPT, Claude, Gemini, etc.) |
| Web Search | Tavily API (LLM-optimized search) |
| Testing | pytest, pytest-asyncio, pytest-cov |
| Storage | JSON files |

---

## Engineering Practices

| Practice | Status | Details |
|----------|--------|---------|
| **Async/Parallel** | ✅ | Concurrent API calls with `asyncio.gather()` |
| **Graceful Degradation** | ✅ | Continues if individual models fail |
| **Test Suite** | ✅ | pytest + pytest-asyncio, 29 tests |
| **Type Hints** | ✅ | Throughout codebase |
| **CI/CD** | 🔜 | GitHub Actions (planned) |
| **Pydantic Models** | 🔜 | Data validation (planned) |
| **Structured Logging** | 🔜 | JSON logs with correlation IDs (planned) |
| **Config Management** | 🔜 | YAML config with validation (planned) |

See [docs/PLAN.md](docs/PLAN.md) for the full engineering roadmap.

---

## Development

### Running Tests

```bash
# Install dev dependencies
uv sync --extra dev

# Run all tests
uv run pytest tests/ -v

# Run with coverage report
uv run pytest tests/ --cov=backend --cov-report=term-missing
```

### Test Structure

```
tests/
├── conftest.py              # Fixtures and mock API responses
├── test_ranking_parser.py   # Ranking extraction tests
├── test_debate.py           # Debate mode tests
└── integration/             # CLI integration tests
```

---

## Roadmap

| Version | Feature | Status |
|---------|---------|--------|
| v1.0 | CLI + TUI + Web UI | ✅ Complete |
| v1.1 | Autonomous Web Search | ✅ Complete |
| v1.2 | Multi-Turn Debate Mode | ✅ Complete |
| v1.3 | Conversation History | Planned |
| v1.4 | File/Document Upload | Planned |
| v1.5 | Image Input (Multimodal) | Planned |

See [docs/PLAN.md](docs/PLAN.md) for the full roadmap and [docs/DEVLOG.md](docs/DEVLOG.md) for development history.

---

## Credits

This project builds upon the original [LLM Council](https://github.com/karpathy/llm-council) concept by **[Andrej Karpathy](https://github.com/karpathy)**. The core idea of using multiple LLMs with peer review comes from his work.

This fork extends the original with:
- Full CLI/TUI interface
- Autonomous web search via tool calling
- Multi-turn debate mode
- Rich terminal output with progress indicators

---

## License

MIT
