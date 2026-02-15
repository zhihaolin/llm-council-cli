# SOLID Refactoring Guide

This document captures educational examples of SOLID principle violations found in this codebase and how to fix them. Use it as a reference for understanding SOLID in practice.

---

## Table of Contents

1. [Single Responsibility Principle (SRP)](#single-responsibility-principle-srp)
2. [Open/Closed Principle (OCP)](#openclosed-principle-ocp)
3. [Liskov Substitution Principle (LSP)](#liskov-substitution-principle-lsp)
4. [Interface Segregation Principle (ISP)](#interface-segregation-principle-isp)
5. [Dependency Inversion Principle (DIP)](#dependency-inversion-principle-dip)

---

## Quick Reference

| Principle | Plain English Summary |
|-----------|----------------------|
| **S**ingle Responsibility | Each module should do ONE thing. If you use "and" to describe it, it's doing too much. |
| **O**pen/Closed | Add new features by writing NEW code, not changing OLD code. |
| **L**iskov Substitution | Similar functions should work the same way—like how all USB devices use the same port. |
| **I**nterface Segregation | Don't force users to take a buffet when they only want a salad. |
| **D**ependency Inversion | Don't hardcode dependencies—pass them in. Makes code testable and swappable. |

---

## Single Responsibility Principle (SRP)

> A class/module should have only one reason to change.

**In plain English:** Each module should do ONE thing. If you have to use the word "and" to describe what a module does ("it handles parsing AND streaming AND orchestration"), it's doing too much. A module that does one thing is easier to understand, test, and change without breaking other things.

### Bad Example: `backend/council.py` (1,722 lines, pre-refactor)

This single file handles **8+ distinct responsibilities**:

```python
# backend/council.py - TOO MANY RESPONSIBILITIES

# 1. Date formatting
def get_date_context() -> str: ...

# 2. Tool execution
async def execute_tool(tool_name, tool_args) -> str: ...

# 3. Stage orchestration
async def stage1_collect_responses(user_query) -> List: ...
async def stage2_collect_rankings(user_query, stage1_results) -> Tuple: ...
async def stage3_synthesize_final(user_query, stage1, stage2) -> Dict: ...

# 4. Text parsing
def parse_ranking_from_text(ranking_text) -> List[str]: ...
def parse_revised_answer(defense_response) -> str: ...
def extract_critiques_for_model(target_model, critiques) -> str: ...

# 5. Aggregation/statistics
def calculate_aggregate_rankings(stage2_results, label_to_model) -> List: ...

# 6. Debate mode orchestration
async def debate_round_critique(query, responses) -> List: ...
async def debate_round_defense(query, initial, critiques) -> List: ...
async def run_debate_council(query, max_rounds) -> Tuple: ...

# 7. Streaming generators
async def debate_round_streaming(round_type, query, context) -> AsyncGenerator: ...
async def run_debate_token_streaming(query, max_rounds) -> AsyncGenerator: ...

# 8. ReAct chairman logic
def parse_react_output(text) -> Tuple: ...
def build_react_prompt(context) -> str: ...
async def synthesize_with_react(query, context) -> AsyncGenerator: ...
```

**Why it's bad:**
- Changing the ranking algorithm requires modifying the same file as streaming logic
- Testing parsers requires importing the entire council module
- New team members struggle to find where specific logic lives
- High risk of merge conflicts when multiple features are developed

### Good Example: Split into focused modules

```
llm_council/engine/
├── __init__.py             # Public API exports
├── ranking.py              # Stage 1-2-3 coordination
├── debate.py               # Debate round logic
├── react.py                # ReAct chairman
├── prompts.py              # Prompt templates
├── parsers.py              # Text parsing utilities
├── debate_streaming.py     # Async generators
└── aggregation.py          # Ranking calculations
```

Each module has **one reason to change**:
- `parsers.py` changes when parsing logic changes
- `prompts.py` changes when prompt templates change
- `debate_streaming.py` changes when streaming behavior changes

---

### Bad Example: `cli/main.py` (1,407 lines, pre-refactor)

Mixed presentation, orchestration, and state management:

```python
# cli/main.py - MIXED CONCERNS

# Presentation (should be separate)
def print_stage1(results): ...
def print_stage2(results, label_to_model, aggregate): ...
def print_debate_round(round_data, round_num): ...

# Orchestration with progress (should be separate)
async def run_council_with_progress(query): ...
async def run_debate_with_progress(query, max_rounds): ...
async def run_debate_streaming(query, max_rounds): ...

# Chat session state (should be separate)
async def run_chat_session(max_turns, start_new): ...

# Command routing (this is the actual CLI concern)
@app.command()
def query(...): ...

@app.command()
def chat(...): ...
```

### Good Example: Split by responsibility

```python
# llm_council/cli/presenters.py - ONLY presentation
def print_stage1(results): ...
def print_stage2(results, label_to_model, aggregate): ...
def print_debate_round(round_data, round_num): ...

# llm_council/cli/runners.py - ONLY execution flow (renamed from orchestrators.py)
async def run_council_with_progress(query): ...
async def run_debate_with_progress(query, max_rounds): ...

# llm_council/cli/chat_session.py - ONLY chat state management
async def run_chat_session(max_turns, start_new): ...

# llm_council/cli/main.py - ONLY command routing (~150 lines)
@app.command()
def query(...):
    print_query_header(...)
    results = asyncio.run(run_council_with_progress(question))
    print_stage1(results)
```

---

## Open/Closed Principle (OCP)

> Software should be open for extension but closed for modification.

**In plain English:** You should be able to add new features without editing existing code. If adding a new "reflection" round type means you have to modify the function that handles "critique" rounds, you risk breaking critique. Good design lets you add new things by writing NEW code, not changing OLD code.

### Bad Example: Adding a new round type requires modifying existing code

```python
# llm_council/engine.py - VIOLATION: must modify to extend

async def debate_round_streaming(round_type, query, context):
    if round_type == "initial":
        # 50 lines of initial logic
        ...
    elif round_type == "critique":
        # 50 lines of critique logic
        ...
    elif round_type == "defense":
        # 50 lines of defense logic
        ...
    # To add "reflection" round, must modify this function!
    else:
        raise ValueError(f"Unknown round type: {round_type}")
```

**Why it's bad:**
- Adding a new round type (e.g., "reflection", "summary") requires editing this function
- Risk of breaking existing round types when adding new ones
- The function grows unbounded as features are added

### Good Example: Strategy pattern for round types

```python
# llm_council/engine/rounds.py - OPEN FOR EXTENSION

from abc import ABC, abstractmethod

class RoundStrategy(ABC):
    """Base class for debate round strategies."""

    @abstractmethod
    async def execute(self, query: str, context: dict) -> List[Dict]:
        """Execute this round type."""
        pass

    @abstractmethod
    def build_prompt(self, model: str, context: dict) -> str:
        """Build the prompt for this round."""
        pass


class InitialRound(RoundStrategy):
    """Initial response round with optional web search."""

    async def execute(self, query: str, context: dict) -> List[Dict]:
        # Initial round logic here
        ...


class CritiqueRound(RoundStrategy):
    """Critique round where models evaluate each other."""

    async def execute(self, query: str, context: dict) -> List[Dict]:
        # Critique logic here
        ...


class DefenseRound(RoundStrategy):
    """Defense round where models respond to critiques."""

    async def execute(self, query: str, context: dict) -> List[Dict]:
        # Defense logic here
        ...


# Adding a new round type - NO MODIFICATION to existing code!
class ReflectionRound(RoundStrategy):
    """Self-reflection round where models critique themselves."""

    async def execute(self, query: str, context: dict) -> List[Dict]:
        # New reflection logic
        ...


# Registry pattern for round types
ROUND_STRATEGIES = {
    "initial": InitialRound(),
    "critique": CritiqueRound(),
    "defense": DefenseRound(),
    "reflection": ReflectionRound(),  # Just add to registry!
}


async def debate_round_streaming(round_type: str, query: str, context: dict):
    """Execute a debate round using the appropriate strategy."""
    strategy = ROUND_STRATEGIES.get(round_type)
    if not strategy:
        raise ValueError(f"Unknown round type: {round_type}")
    return await strategy.execute(query, context)
```

**Benefits:**
- Add new round types by creating new classes, not modifying existing ones
- Each round type is self-contained and testable
- Existing code is "closed" to modification

---

## Liskov Substitution Principle (LSP)

> Subtypes must be substitutable for their base types.

**In plain English:** If you have functions that do similar things (like stage1, stage2, stage3), they should work the same way. If stage1 returns a list, stage2 returns a tuple, and stage3 returns a dict, the caller has to write special handling for each one. Consistent interfaces let you treat similar things uniformly—like how all USB devices plug into the same port.

### Bad Example: Inconsistent return types

```python
# llm_council/engine.py - VIOLATION: inconsistent returns

async def stage1_collect_responses(query) -> List[Dict]:
    """Returns list of response dicts."""
    return [{"model": "...", "response": "..."}]

async def stage2_collect_rankings(query, stage1) -> Tuple[List, Dict]:
    """Returns tuple of (rankings, label_to_model)."""
    return rankings, label_to_model  # Different structure!

async def stage3_synthesize_final(query, stage1, stage2) -> Dict:
    """Returns single dict."""
    return {"model": "...", "response": "..."}

# Caller must know the specific return type of each stage
# Can't treat stages uniformly
```

### Good Example: Consistent interface with result objects

```python
# llm_council/engine/types.py - CONSISTENT INTERFACE

from dataclasses import dataclass
from typing import List, Dict, Any, Optional

@dataclass
class StageResult:
    """Consistent result type for all stages."""
    stage_name: str
    responses: List[Dict[str, Any]]
    metadata: Optional[Dict[str, Any]] = None

    def get_primary_response(self) -> str:
        """Get the main response content."""
        if self.responses:
            return self.responses[0].get("response", "")
        return ""


# Now all stages return the same type
async def stage1_collect_responses(query) -> StageResult:
    responses = [...]
    return StageResult(
        stage_name="stage1",
        responses=responses,
        metadata={"tool_calls": [...]}
    )

async def stage2_collect_rankings(query, stage1) -> StageResult:
    rankings = [...]
    return StageResult(
        stage_name="stage2",
        responses=rankings,
        metadata={"label_to_model": {...}, "aggregate": [...]}
    )

async def stage3_synthesize_final(query, stage1, stage2) -> StageResult:
    synthesis = {...}
    return StageResult(
        stage_name="stage3",
        responses=[synthesis]
    )


# Now stages can be treated uniformly
async def run_pipeline(query: str, stages: List[Callable]) -> List[StageResult]:
    """Run any combination of stages."""
    results = []
    for stage in stages:
        result = await stage(query, results)
        results.append(result)
    return results
```

---

## Interface Segregation Principle (ISP)

> Clients should not be forced to depend on interfaces they don't use.

**In plain English:** Don't force users to take a whole buffet when they only want a salad. If someone just needs `run_debate_council()`, they shouldn't have to import 15 other functions they'll never use. Smaller, focused interfaces mean less coupling—when you change `parse_ranking_from_text()`, code that only uses `run_debate_council()` won't break.

### Bad Example: Importing entire module for one function

```python
# llm_council/cli/main.py - VIOLATION: imports everything

from llm_council.engine import (
    stage1_collect_responses,
    stage2_collect_rankings,
    stage3_synthesize_final,
    calculate_aggregate_rankings,
    run_debate_council,
    run_debate_council_streaming,
    run_debate_token_streaming,
    generate_conversation_title,
    parse_ranking_from_text,        # Not used in this file!
    parse_revised_answer,           # Not used in this file!
    extract_critiques_for_model,    # Not used in this file!
    debate_round_critique,          # Not used in this file!
    debate_round_defense,           # Not used in this file!
)
```

**Why it's bad:**
- Importing unused functions creates unnecessary coupling
- Changes to unused functions can still cause import errors
- Harder to understand what a module actually depends on

### Good Example: Focused module APIs

```python
# llm_council/engine/__init__.py - FOCUSED EXPORTS

# Only export what external users need
from .ranking import (
    run_full_council,
    stage1_collect_responses,
    stage2_collect_rankings,
    stage3_synthesize_final,
)

from .debate import (
    run_debate_council,
)

from .debate_streaming import (
    run_debate_council_streaming,
    run_debate_token_streaming,
)

from .react import (
    synthesize_with_react,
    build_react_context_debate,
    build_react_context_ranking,
)

# Internal functions (parsers, prompts) are NOT exported
# They're implementation details
```

```python
# llm_council/cli/main.py - CLEAN IMPORTS

# Import only what's needed
from llm_council.engine import (
    run_full_council,
    run_debate_council,
)

# If you need streaming, import from specific submodule
from llm_council.engine.debate_streaming import run_debate_token_streaming
```

---

## Dependency Inversion Principle (DIP)

> High-level modules should not depend on low-level modules. Both should depend on abstractions.

**In plain English:** Don't hardcode your dependencies—pass them in. If `stage1_collect_responses()` directly imports `COUNCIL_MODELS` from config, you can't test it with mock models or run it with different models without changing the code. Instead, accept models as a parameter with a sensible default. This makes code testable, flexible, and swappable (want to use Ollama instead of OpenRouter? Just pass a different querier).

### Bad Example: Hardcoded dependencies

```python
# llm_council/engine.py - VIOLATION: hardcoded config

from .settings import COUNCIL_MODELS, CHAIRMAN_MODEL  # Concrete dependency

async def stage1_collect_responses(query: str):
    """Uses hardcoded COUNCIL_MODELS - can't test or customize."""
    for model in COUNCIL_MODELS:  # Hardcoded!
        response = await query_model(model, messages)
        ...

async def stage3_synthesize_final(query, stage1, stage2):
    """Uses hardcoded CHAIRMAN_MODEL - can't substitute."""
    response = await query_model(CHAIRMAN_MODEL, messages)  # Hardcoded!
    ...
```

**Why it's bad:**
- Can't test with mock models without monkey-patching
- Can't run council with different model configurations
- Config change requires code change

### Good Example: Dependency injection

```python
# llm_council/engine/ranking.py - DEPENDENCY INJECTION

from typing import List, Optional, Protocol

class ModelQuerier(Protocol):
    """Abstract interface for querying models."""
    async def query(self, model: str, messages: list) -> dict: ...


async def stage1_collect_responses(
    query: str,
    models: List[str],  # Injected, not hardcoded
    querier: ModelQuerier,  # Injected, not imported
) -> List[Dict]:
    """Models and querier are injected - easy to test and customize."""
    results = []
    for model in models:
        response = await querier.query(model, [{"role": "user", "content": query}])
        results.append({"model": model, "response": response})
    return results


async def stage3_synthesize_final(
    query: str,
    stage1: List[Dict],
    stage2: List[Dict],
    chairman_model: str,  # Injected
    querier: ModelQuerier,  # Injected
) -> Dict:
    """Chairman model is injected - can use any model."""
    response = await querier.query(chairman_model, messages)
    return {"model": chairman_model, "response": response}


# High-level orchestration uses defaults but allows injection
async def run_full_council(
    query: str,
    models: Optional[List[str]] = None,
    chairman: Optional[str] = None,
    querier: Optional[ModelQuerier] = None,
):
    """Dependency injection with sensible defaults."""
    from .settings import COUNCIL_MODELS, CHAIRMAN_MODEL
    from .adapters.openrouter_client import OpenRouterQuerier

    models = models or COUNCIL_MODELS
    chairman = chairman or CHAIRMAN_MODEL
    querier = querier or OpenRouterQuerier()

    stage1 = await stage1_collect_responses(query, models, querier)
    stage2 = await stage2_collect_rankings(query, stage1, models, querier)
    stage3 = await stage3_synthesize_final(query, stage1, stage2, chairman, querier)

    return stage1, stage2, stage3
```

**Benefits:**
- Easy to test with mock querier
- Can run council with any model configuration
- Swap OpenRouter for Ollama by injecting different querier

```python
# Testing is now easy
async def test_stage1():
    class MockQuerier:
        async def query(self, model, messages):
            return {"content": f"Mock response from {model}"}

    results = await stage1_collect_responses(
        "test query",
        models=["model-a", "model-b"],
        querier=MockQuerier()
    )

    assert len(results) == 2
    assert "Mock response" in results[0]["response"]
```

---

## Summary: Before and After

| Principle | Before (Violation) | After (Fixed) |
|-----------|-------------------|---------------|
| **Single Responsibility** | 1,722-line council.py with 8 responsibilities | 7 focused modules (~200 lines each) |
| **Open/Closed** | if/elif chain for round types | Strategy pattern with registry |
| **Liskov Substitution** | Inconsistent return types per stage | Uniform StageResult dataclass |
| **Interface Segregation** | Import 15 functions, use 5 | Focused module exports |
| **Dependency Inversion** | Hardcoded COUNCIL_MODELS | Dependency injection with defaults |

---

## Refactoring Progress

### Phase 1: Remove Web UI ✅
Deleted frontend/, start.sh, backend/main.py

### Phase 2: Extract CLI Modules ✅
Created presenters.py, runners.py (originally orchestrators.py), chat_session.py, utils.py (applies SRP)

### Phase 3: Split Council Module ✅
Split 1,722-line council.py into focused modules:
```
llm_council/engine/
├── __init__.py             # Public API exports
├── aggregation.py          # Ranking calculations
├── debate.py               # Debate orchestration
├── ranking.py              # Stage 1-2-3 flow
├── parsers.py              # Regex/text parsing
├── prompts.py              # Prompt templates
├── react.py                # ReAct chairman logic
└── debate_streaming.py     # Event generators
```

### Phase 4: Apply OCP/DIP (Future)
Add strategy pattern and dependency injection

---

*This document serves as both a refactoring plan and an educational reference for SOLID principles.*
