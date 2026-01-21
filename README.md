# LLM Council

[![MIT License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Tests](https://github.com/zhihaolin/llm-council-cli/actions/workflows/test.yml/badge.svg)](https://github.com/zhihaolin/llm-council-cli/actions/workflows/test.yml)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Coverage](https://img.shields.io/badge/coverage-66%25-brightgreen)](pyproject.toml)

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

**Search-enabled rounds in debate mode:**
- Round 1 (Initial): Models search to gather facts for their position
- Round 3 (Defense): Models search to find evidence supporting their defense

![Models autonomously searching for current information](images/search.png)

### ReAct Chairman

The chairman uses ReAct (Reasoning + Acting) to verify facts before synthesizing. If model responses disagree on factual claims, the chairman can search to verify before producing the final answer.

```
━━━ CHAIRMAN'S REASONING ━━━

Thought: The responses disagree on the current Bitcoin price. I should verify.

Action: search_web("bitcoin price today")

Observation: Bitcoin is currently trading at $67,234...

Thought: Now I can synthesize with verified data.

Action: synthesize()

━━━ CHAIRMAN'S SYNTHESIS ━━━
```

ReAct is enabled by default. Disable with `--no-react` or `/react off` in chat mode.

### Interactive Chat Mode

Multi-turn conversations with persistent history. The chat REPL remembers context and lets you switch between ranking and debate modes on the fly.

```bash
uv run llm-council chat
```

```
┌─────────────── Council Chat ───────────────┐
│ Resumed conversation                       │
│ Previous Topic Title                       │
│ ID: abc12345                               │
│ Mode: Debate (2 rounds) [parallel] [react] │
└────────────────────────────────────────────┘
Commands: /help, /history, /use <id>, /new, /debate, /parallel, /stream, /react, /rounds, /mode, /exit

debate(2)> What is the capital of France?
```

Slash commands:
- `/history` — List saved conversations
- `/use <id>` — Switch to a conversation by ID prefix
- `/new` — Start a new conversation
- `/debate on|off` — Toggle debate mode
- `/parallel on|off` — Toggle parallel mode (default: on)
- `/stream on|off` — Toggle streaming mode
- `/react on|off` — Toggle ReAct reasoning (default: on)
- `/rounds N` — Set debate rounds
- `/mode` — Show current mode
- `/exit` — Exit chat

### Rich Terminal Interface

- **CLI mode** — Full 3-stage output with progress indicators
- **Simple mode** — Just the final answer, pipe-friendly
- **Chat mode** — Interactive REPL with conversation history
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
│  │ Model A │ │ Model B │ │ Model C │ │ Model D │ │ Model E │   │
│  │  (GPT)  │ │(Gemini) │ │(Claude) │ │ (Grok)  │ │(DeepSeek)   │
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
uv run llm-council query "What is the best programming language for beginners?"

# Debate mode (models critique each other)
uv run llm-council query --debate "Should AI be regulated?"

# Simple output (just the final answer)
uv run llm-council query --simple "What is 2+2?"
```

---

## CLI Usage

### Commands

```bash
# Query with full deliberation output
uv run llm-council query "Your question"

# Query with debate mode
uv run llm-council query --debate "Complex question"
uv run llm-council query --debate --rounds 3 "Very complex question"

# Simple output (final answer only, no stages)
uv run llm-council query --simple "Quick question"

# Final answer with formatting (skip stages 1 & 2)
uv run llm-council query --final-only "Question"

# Show current council configuration
uv run llm-council models

# Interactive chat with history
uv run llm-council chat
uv run llm-council chat --new  # Start fresh conversation

# Interactive TUI
uv run llm-council interactive
```

### Flags

| Flag | Short | Description |
|------|-------|-------------|
| `--simple` | `-s` | Output only the final answer (no formatting) |
| `--final-only` | `-f` | Show only chairman's synthesis (with formatting) |
| `--debate` | `-d` | Enable debate mode |
| `--rounds N` | `-r N` | Number of debate rounds (default: 2) |
| `--stream` | | Stream token-by-token (sequential, debate mode) |
| `--parallel` | `-p` | Run models in parallel with progress spinners (debate mode) |
| `--no-react` | | Disable ReAct reasoning for chairman |
| `--new` | | Start a new conversation (chat mode) |
| `--max-turns N` | `-t N` | Context turns to include (chat mode, default: 6) |

---

## Configuration

### Models

Edit `backend/config.py` to customize the council:

```python
# Example configuration (use any OpenRouter-supported models)
COUNCIL_MODELS = [
    "openai/gpt-4o-mini",      # Fast, cost-effective
    "x-ai/grok-3",             # X.AI's latest
    "deepseek/deepseek-chat",  # Strong reasoning
]

CHAIRMAN_MODEL = "openai/gpt-4o-mini"
```

All models are accessed through [OpenRouter](https://openrouter.ai/), which provides a unified API for 200+ models from OpenAI, Anthropic, Google, Meta, and more. Choose models based on your budget and quality requirements.

---

## Tech Stack

| Component | Technology |
|-----------|------------|
| Backend | Python 3.10+, async httpx |
| CLI | Typer, Rich, Textual |
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
| **Test Suite** | ✅ | pytest + pytest-asyncio, 84 tests, 66% coverage |
| **Linting** | ✅ | Ruff (check + format) in CI |
| **Type Checking** | ✅ | Pyright in basic mode |
| **Type Hints** | ✅ | Throughout codebase |
| **CI/CD** | ✅ | GitHub Actions (lint → test pipeline) |
| **SOLID (SRP/ISP)** | ✅ | Focused modules, clean API exports |
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
├── conftest.py                  # Fixtures and mock API responses
├── test_chat_commands.py        # Chat REPL command parsing (10 tests)
├── test_conversation_context.py # Context extraction (5 tests)
├── test_debate.py               # Debate mode (15 tests)
├── test_ranking_parser.py       # Ranking extraction (14 tests)
├── test_react.py                # ReAct chairman (11 tests)
├── test_search.py               # Web search & tool calling (17 tests)
├── test_streaming.py            # Streaming & parallel (10 tests)
└── integration/                 # CLI integration tests (planned)
```

---

## Roadmap

| Version | Feature | Status |
|---------|---------|--------|
| v1.0 | CLI + TUI | ✅ Complete |
| v1.1 | Autonomous Web Search | ✅ Complete |
| v1.2 | Multi-Turn Debate Mode | ✅ Complete |
| v1.3 | Interactive Chat with History | ✅ Complete |
| v1.4 | Token Streaming | ✅ Complete |
| v1.5 | Parallel Execution with Progress | ✅ Complete |
| v1.6 | ReAct Chairman | ✅ Complete |
| v1.6.1 | SOLID Refactoring | ✅ Complete |
| v1.7 | Self-Reflection Round | Planned |
| v1.8 | Workflow State Machine | Planned |
| v1.9 | File/Document Upload | Planned |
| v1.10 | Observability (OpenTelemetry) | Planned |
| v1.11 | Tool Registry (MCP) | Planned |
| v1.12 | Retry & Fallback Logic | Planned |
| v1.13 | Security Foundations | Planned |

See [docs/PLAN.md](docs/PLAN.md) for the full roadmap and [docs/DEVLOG.md](docs/DEVLOG.md) for development history.

---

## Credits

This project builds upon the original [LLM Council](https://github.com/karpathy/llm-council) concept by **[Andrej Karpathy](https://github.com/karpathy)**. The core idea of using multiple LLMs with peer review comes from his work.

This fork extends the original with:
- Full CLI/TUI interface
- Interactive chat with conversation history
- Autonomous web search via tool calling
- Multi-turn debate mode
- Rich terminal output with progress indicators

---

## License

MIT
