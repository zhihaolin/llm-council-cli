"""
Debate mode orchestration for council deliberation.

Contains RoundConfig, async execution strategies (parallel and streaming),
and the debate orchestrator.
"""

import asyncio
from collections.abc import AsyncGenerator, Callable
from dataclasses import dataclass
from typing import Any, Protocol

from ..adapters.openrouter_client import (
    query_model,
    query_model_streaming,
    query_model_streaming_with_tools,
    query_model_with_tools,
)
from ..adapters.tavily_search import SEARCH_TOOL, format_search_results, search_web
from ..settings import COUNCIL_MODELS
from .parsers import extract_critiques_for_model, parse_revised_answer
from .prompts import (
    build_critique_prompt,
    build_defense_prompt,
    format_responses_for_critique,
    get_date_context,
    wrap_prompt_with_react,
)
from .react import council_react_loop


class ExecuteRound(Protocol):
    """Protocol for debate round execution strategies.

    Implementations must be async generators that yield event dicts and
    end with a ``{"type": "round_complete", "responses": [...]}`` event.

    Two built-in strategies:
        - ``debate_round_parallel``: runs all models concurrently
        - ``debate_round_streaming``: runs models sequentially with token streaming
    """

    def __call__(
        self,
        *,
        round_type: str,
        user_query: str,
        context: dict[str, Any],
    ) -> AsyncGenerator[dict[str, Any], None]: ...


async def execute_tool(tool_name: str, tool_args: dict[str, Any]) -> str:
    """
    Execute a tool and return the result as a string.

    Args:
        tool_name: Name of the tool to execute
        tool_args: Arguments to pass to the tool

    Returns:
        String result of tool execution
    """
    if tool_name == "search_web":
        query = tool_args.get("query", "")
        search_response = await search_web(query)
        return format_search_results(search_response)
    else:
        return f"Unknown tool: {tool_name}"


@dataclass(frozen=True)
class RoundConfig:
    """Configuration for a single debate round.

    Captures the per-round-type differences so that execution strategies
    don't need to duplicate if/elif dispatch on round_type.

    Attributes:
        uses_tools: Whether the model should have access to web search tools.
        build_prompt: A callable (model) -> prompt_string for this round.
        has_revised_answer: Whether the response should be parsed for a revised answer.
        uses_react: Whether council members use text-based ReAct reasoning.
    """

    uses_tools: bool
    build_prompt: Callable[[str], str]
    has_revised_answer: bool
    uses_react: bool = False


def build_round_config(
    round_type: str,
    user_query: str,
    context: dict[str, Any],
    react_enabled: bool = False,
) -> RoundConfig:
    """Build a RoundConfig for the given round type.

    Single point of dispatch replacing duplicated if/elif chains in both
    parallel and streaming execution strategies.

    Args:
        round_type: One of "initial", "critique", or "defense"
        user_query: The user's question
        context: Context dict containing:
            - For critique: {"initial_responses": [...]}
            - For defense: {"initial_responses": [...], "critique_responses": [...]}
        react_enabled: Whether council members should use text-based ReAct reasoning.
            Only applies to tool-enabled rounds (initial, defense). Critique rounds
            never use ReAct.

    Returns:
        RoundConfig with the appropriate prompt builder and flags

    Raises:
        ValueError: If round_type is not recognized
    """
    if round_type == "initial":
        query_with_date = get_date_context() + user_query
        use_react = react_enabled  # initial round supports tools

        def _initial_prompt(_model: str) -> str:
            prompt = query_with_date
            if use_react:
                return wrap_prompt_with_react(prompt)
            return prompt

        return RoundConfig(
            uses_tools=True,
            build_prompt=_initial_prompt,
            has_revised_answer=False,
            uses_react=use_react,
        )

    if round_type == "critique":
        initial_responses = context.get("initial_responses", [])
        responses_text = format_responses_for_critique(initial_responses)

        def _critique_prompt(model: str) -> str:
            return build_critique_prompt(user_query, responses_text, model)

        return RoundConfig(
            uses_tools=False, build_prompt=_critique_prompt, has_revised_answer=False
        )

    if round_type == "defense":
        initial_responses = context.get("initial_responses", [])
        critique_responses = context.get("critique_responses", [])
        model_to_response = {r["model"]: r["response"] for r in initial_responses}
        use_react = react_enabled  # defense round supports tools

        def _defense_prompt(model: str) -> str:
            original = model_to_response.get(model, "")
            critiques = extract_critiques_for_model(model, critique_responses)
            prompt = build_defense_prompt(user_query, original, critiques)
            if use_react:
                return wrap_prompt_with_react(prompt)
            return prompt

        return RoundConfig(
            uses_tools=True,
            build_prompt=_defense_prompt,
            has_revised_answer=True,
            uses_react=use_react,
        )

    raise ValueError(f"Unknown round type: {round_type}")


async def run_debate(
    user_query: str,
    execute_round: ExecuteRound,
    cycles: int = 1,
) -> AsyncGenerator[dict[str, Any], None]:
    """
    Single orchestrator that defines the debate round sequence once.

    Delegates execution to the given `execute_round` callback, which must match
    the execute-round protocol: an async generator that yields events and must
    yield a final ``{"type": "round_complete", "responses": [...]}`` event.

    Args:
        user_query: The user's question
        execute_round: Async generator matching the execute-round protocol
        cycles: Number of critique-defense cycles after the initial round.
            cycles=1 (default) produces 3 interaction rounds: initial → critique → defense.
            cycles=2 produces 5 interaction rounds: initial → 2×(critique → defense).

    Yields:
        {'type': 'round_start', 'round_number': int, 'round_type': str}
        (pass-through events from execute_round)
        {'type': 'round_complete', 'round_number': int, 'round_type': str, 'responses': List}
        {'type': 'error', 'message': str}
        {'type': 'debate_complete', 'rounds': List}
    """
    rounds = []

    # Build the round sequence: initial, then N critique-defense cycles.
    # Always ends on defense — no dangling critiques.
    round_sequence = [(1, "initial")]
    round_num = 2
    for _ in range(cycles):
        round_sequence.append((round_num, "critique"))
        round_num += 1
        round_sequence.append((round_num, "defense"))
        round_num += 1

    initial_responses = []
    critique_responses = []
    current_responses = []

    for rnd_num, rnd_type in round_sequence:
        yield {"type": "round_start", "round_number": rnd_num, "round_type": rnd_type}

        # Build context for this round
        if rnd_type == "initial":
            context = {}
        elif rnd_type == "critique":
            context = {"initial_responses": current_responses or initial_responses}
        elif rnd_type == "defense":
            context = {
                "initial_responses": current_responses or initial_responses,
                "critique_responses": critique_responses,
            }
        else:
            context = {}

        # Delegate to executor and pass through events
        responses = []
        async for event in execute_round(
            round_type=rnd_type,
            user_query=user_query,
            context=context,
        ):
            if event["type"] == "round_complete":
                responses = event["responses"]
                # Augment with round metadata
                yield {
                    "type": "round_complete",
                    "round_number": rnd_num,
                    "round_type": rnd_type,
                    "responses": responses,
                }
            else:
                yield event

        # Track state for subsequent rounds
        rounds.append({"round_number": rnd_num, "round_type": rnd_type, "responses": responses})

        if rnd_type == "initial":
            initial_responses = responses
            if len(initial_responses) < 2:
                yield {
                    "type": "error",
                    "message": "Not enough models responded to conduct a debate. Need at least 2 models.",
                }
                return
        elif rnd_type == "critique":
            critique_responses = responses
        elif rnd_type == "defense":
            current_responses = responses

    yield {"type": "debate_complete", "rounds": rounds}


async def debate_round_parallel(
    round_type: str,
    user_query: str,
    context: dict[str, Any],
    model_timeout: float = 120.0,
    react_enabled: bool = False,
) -> AsyncGenerator[dict[str, Any], None]:
    """
    Stream a single debate round, yielding events as each model completes.

    Runs all models in parallel and yields results as they complete.

    Args:
        round_type: One of "initial", "critique", or "defense"
        user_query: The user's question
        context: Context dict containing:
            - For critique: {"initial_responses": [...]}
            - For defense: {"initial_responses": [...], "critique_responses": [...]}
        model_timeout: Timeout in seconds for each model (default: 120s)
        react_enabled: Whether council members use text-based ReAct reasoning

    Yields:
        {'type': 'model_start', 'model': str}
        {'type': 'model_complete', 'model': str, 'response': Dict}
        {'type': 'model_error', 'model': str, 'error': str}
        {'type': 'round_complete', 'responses': List}
    """
    config = build_round_config(round_type, user_query, context, react_enabled=react_enabled)

    async def _query_model(model: str) -> dict | None:
        """Query a single model using the round config."""
        prompt = config.build_prompt(model)

        if config.uses_react:
            # Use text-based ReAct loop — consume events, return final result
            content = ""
            tool_calls_made = []
            async for event in council_react_loop(model, prompt):
                if event["type"] == "done":
                    content = event["content"]
                    tool_calls_made = event.get("tool_calls_made", [])
            if not content:
                return None
            result = {"model": model, "response": content}
            if config.has_revised_answer:
                result["revised_answer"] = parse_revised_answer(content)
            if tool_calls_made:
                result["tool_calls_made"] = tool_calls_made
            return result

        messages = [{"role": "user", "content": prompt}]

        if config.uses_tools:
            response = await query_model_with_tools(
                model=model, messages=messages, tools=[SEARCH_TOOL], tool_executor=execute_tool
            )
        else:
            response = await query_model(model, messages)

        if response is None:
            return None

        result = {"model": model, "response": response.get("content", "")}
        if config.has_revised_answer:
            result["revised_answer"] = parse_revised_answer(result["response"])
        if response.get("tool_calls_made"):
            result["tool_calls_made"] = response["tool_calls_made"]
        return result

    # Wrapper to include model identity in result with timeout
    async def query_with_model(model: str):
        try:
            # Apply per-model timeout
            result = await asyncio.wait_for(_query_model(model), timeout=model_timeout)
            return model, result, None
        except asyncio.TimeoutError:
            return model, None, f"Timeout after {model_timeout}s"
        except Exception as e:
            return model, None, str(e)

    # Emit model_start events for all models (so CLI can show spinners)
    for model in COUNCIL_MODELS:
        yield {"type": "model_start", "model": model}

    # Create tasks and map them back to models
    tasks = {asyncio.create_task(query_with_model(model)): model for model in COUNCIL_MODELS}

    # Collect responses as they complete
    responses = []

    for completed_task in asyncio.as_completed(tasks.keys()):
        model, result, error = await completed_task
        if error:
            yield {"type": "model_error", "model": model, "error": error}
        elif result is None:
            yield {"type": "model_error", "model": model, "error": "Model returned None"}
        else:
            yield {"type": "model_complete", "model": model, "response": result}
            responses.append(result)

    # Yield round complete with all responses
    yield {"type": "round_complete", "responses": responses}


async def debate_round_streaming(
    round_type: str,
    user_query: str,
    context: dict[str, Any],
    react_enabled: bool = False,
) -> AsyncGenerator[dict[str, Any], None]:
    """
    Execute a single debate round with token-level streaming (sequential).

    Processes models one at a time, yielding token events as they stream.
    Matches the execute-round protocol: yields events and a final
    ``{"type": "round_complete", "responses": [...]}`` event.

    Args:
        round_type: One of "initial", "critique", or "defense"
        user_query: The user's question
        context: Context dict containing:
            - For critique: {"initial_responses": [...]}
            - For defense: {"initial_responses": [...], "critique_responses": [...]}
        react_enabled: Whether council members use text-based ReAct reasoning

    Yields:
        {'type': 'model_start', 'model': str}
        {'type': 'token', 'model': str, 'content': str}
        {'type': 'thought', 'model': str, 'content': str}
        {'type': 'action', 'model': str, 'tool': str, 'args': str}
        {'type': 'observation', 'model': str, 'content': str}
        {'type': 'tool_call', 'model': str, 'tool': str, 'args': dict}
        {'type': 'tool_result', 'model': str, 'tool': str, 'result': str}
        {'type': 'model_complete', 'model': str, 'response': Dict}
        {'type': 'model_error', 'model': str, 'error': str}
        {'type': 'round_complete', 'responses': List}
    """
    config = build_round_config(round_type, user_query, context, react_enabled=react_enabled)
    tools = [SEARCH_TOOL]
    responses = []

    for model in COUNCIL_MODELS:
        yield {"type": "model_start", "model": model}

        prompt = config.build_prompt(model)
        full_content = ""
        tool_calls_made = []
        had_error = False

        try:
            if config.uses_react:
                # Text-based ReAct loop — pass through thought/action/observation events
                async for event in council_react_loop(model, prompt):
                    if event["type"] == "token":
                        full_content += event["content"]
                        yield {"type": "token", "model": model, "content": event["content"]}
                    elif event["type"] == "thought":
                        yield {"type": "thought", "model": model, "content": event["content"]}
                    elif event["type"] == "action":
                        yield {
                            "type": "action",
                            "model": model,
                            "tool": event["tool"],
                            "args": event.get("args"),
                        }
                    elif event["type"] == "observation":
                        yield {
                            "type": "observation",
                            "model": model,
                            "content": event["content"],
                        }
                    elif event["type"] == "done":
                        full_content = event["content"]
                        tool_calls_made = event.get("tool_calls_made", [])
                    elif event["type"] == "error":
                        yield {"type": "model_error", "model": model, "error": event["error"]}
                        had_error = True
                        break

            elif config.uses_tools:
                messages = [{"role": "user", "content": prompt}]
                async for event in query_model_streaming_with_tools(
                    model=model,
                    messages=messages,
                    tools=tools,
                    tool_executor=execute_tool,
                ):
                    if event["type"] == "token":
                        full_content += event["content"]
                        yield {"type": "token", "model": model, "content": event["content"]}
                    elif event["type"] == "tool_call":
                        yield {
                            "type": "tool_call",
                            "model": model,
                            "tool": event["tool"],
                            "args": event["args"],
                        }
                    elif event["type"] == "tool_result":
                        yield {
                            "type": "tool_result",
                            "model": model,
                            "tool": event["tool"],
                            "result": event["result"],
                        }
                    elif event["type"] == "done":
                        full_content = event.get("content", full_content)
                        tool_calls_made = event.get("tool_calls_made", [])
                    elif event["type"] == "error":
                        yield {"type": "model_error", "model": model, "error": event["error"]}
                        had_error = True
                        break
            else:
                messages = [{"role": "user", "content": prompt}]
                async for event in query_model_streaming(model, messages):
                    if event["type"] == "token":
                        full_content += event["content"]
                        yield {"type": "token", "model": model, "content": event["content"]}
                    elif event["type"] == "error":
                        yield {"type": "model_error", "model": model, "error": event["error"]}
                        had_error = True
                        break

            if full_content and not had_error:
                result = {"model": model, "response": full_content}
                if config.has_revised_answer:
                    result["revised_answer"] = parse_revised_answer(full_content)
                if tool_calls_made:
                    result["tool_calls_made"] = tool_calls_made
                responses.append(result)
                yield {"type": "model_complete", "model": model, "response": result}

        except Exception as e:
            yield {"type": "model_error", "model": model, "error": str(e)}

    yield {"type": "round_complete", "responses": responses}
