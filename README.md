# LLM Council CLI

> **Fork of [Andrej Karpathy's LLM Council](https://github.com/karpathy/llm-council)** - Extended with a terminal-based interface.

![llmcouncil](header.jpg)

## Credits

This project is based on the original [LLM Council](https://github.com/karpathy/llm-council) created by **[Andrej Karpathy](https://github.com/karpathy)**. All credit for the core concept and implementation goes to him. This fork adds a CLI/TUI interface for terminal users.

---

## What is LLM Council?

Instead of asking a question to a single LLM, you can group multiple LLMs into a "Council". This project sends your query to multiple LLMs, has them review and rank each other's work anonymously, and then a Chairman LLM produces the final response.

**The 3-Stage Process:**

1. **Stage 1: First opinions** - The query is sent to all LLMs individually, responses collected
2. **Stage 2: Review** - Each LLM ranks the anonymized responses of others
3. **Stage 3: Final response** - The Chairman synthesizes everything into a final answer

## What This Fork Adds

- **CLI interface** - Query the council from your terminal
- **Rich output** - Progress indicators, formatted tables, markdown rendering
- **Web search** - Models can autonomously search the web for current information
- **Interactive TUI** - Terminal UI with Textual (optional)
- **Simple mode** - Pipe-friendly output for scripting

See [docs/PLAN.md](docs/PLAN.md) for the full implementation roadmap and [docs/DEVLOG.md](docs/DEVLOG.md) for development progress.

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

Create a `.env` file in the project root:

```bash
# Required: OpenRouter API key for LLM access
echo "OPENROUTER_API_KEY=sk-or-v1-your-key-here" > .env

# Optional: Tavily API key for web search (models decide when to search)
echo "TAVILY_API_KEY=tvly-your-key-here" >> .env
```

Get your API keys at:
- [openrouter.ai](https://openrouter.ai/) - Required for LLM queries
- [tavily.com](https://tavily.com/) - Optional, enables web search (free tier: 1000 searches/month)

### 3. Run the CLI

```bash
# Query the council
uv run python -m cli query "What is the best programming language for beginners?"

# Show current council configuration
uv run python -m cli models
```

---

## CLI Usage

### Basic Query

```bash
uv run python -m cli query "Your question here"
```

This shows all 3 stages: individual responses, rankings, and final synthesis.

### Output Options

```bash
# Simple output - just the final answer (no formatting)
uv run python -m cli query -s "Quick question"

# Final only - skip stages 1 & 2, show only chairman's synthesis
uv run python -m cli query -f "Just give me the answer"
```

### Show Models

```bash
uv run python -m cli models
```

### Interactive TUI (Experimental)

```bash
uv run python -m cli interactive
```

---

## Running in a New Terminal Session

If you open a new terminal, navigate to the project and run:

```bash
cd /path/to/llm-council-cli
uv run python -m cli query "Your question"
```

The `uv run` command automatically uses the project's virtual environment.

---

## Configure Models

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

---

## Web UI (Original)

The original web interface is still available:

**Option 1: Use the start script**
```bash
./start.sh
```

**Option 2: Run manually**

Terminal 1 (Backend):
```bash
uv run python -m backend.main
```

Terminal 2 (Frontend):
```bash
cd frontend
npm install  # first time only
npm run dev
```

Then open http://localhost:5173 in your browser.

---

## Tech Stack

- **Backend:** FastAPI (Python 3.10+), async httpx, OpenRouter API
- **Frontend:** React + Vite, react-markdown for rendering
- **CLI:** Typer, Textual, Rich
- **Web Search:** Tavily API (optional, for real-time information)
- **Storage:** JSON files in `data/conversations/`
- **Package Management:** uv for Python, npm for JavaScript

## License

This project inherits from the original [LLM Council](https://github.com/karpathy/llm-council) by Andrej Karpathy.
