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

- **CLI interface** - Query the council from your terminal: `llm-council "your question"`
- **Rich TUI** - Interactive terminal UI with Textual (tabs, panels, progress indicators)
- **Simple mode** - Pipe-friendly output for scripting
- **Model configuration** - Select council members via CLI flags or config file

See [PLAN.md](PLAN.md) for the full implementation roadmap.

---

## Setup

### 1. Install Dependencies

The project uses [uv](https://docs.astral.sh/uv/) for project management.

**Backend:**
```bash
uv sync
```

**Frontend (for web UI):**
```bash
cd frontend
npm install
cd ..
```

### 2. Configure API Key

Create a `.env` file in the project root:

```bash
OPENROUTER_API_KEY=sk-or-v1-...
```

Get your API key at [openrouter.ai](https://openrouter.ai/).

### 3. Configure Models (Optional)

Edit `backend/config.py` to customize the council:

```python
COUNCIL_MODELS = [
    "openai/gpt-5.1",
    "google/gemini-3-pro-preview",
    "anthropic/claude-sonnet-4.5",
    "x-ai/grok-4",
]

CHAIRMAN_MODEL = "google/gemini-3-pro-preview"
```

## Running the Application

### Web UI (Original)

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
npm run dev
```

Then open http://localhost:5173 in your browser.

### CLI (Coming Soon)

```bash
# Basic query
llm-council "What is the best programming language for beginners?"

# Simple output (just final answer)
llm-council -s "Quick question"

# Interactive TUI mode
llm-council -i

# Custom models
llm-council --models "gpt-5,claude-4" --chairman "gemini-3" "Your question"
```

## Tech Stack

- **Backend:** FastAPI (Python 3.10+), async httpx, OpenRouter API
- **Frontend:** React + Vite, react-markdown for rendering
- **CLI:** Typer, Textual, Rich (coming soon)
- **Storage:** JSON files in `data/conversations/`
- **Package Management:** uv for Python, npm for JavaScript

## License

This project inherits from the original [LLM Council](https://github.com/karpathy/llm-council) by Andrej Karpathy.
