"""
Async execution strategies for council deliberation.

Contains async generators that yield events as models complete or stream tokens.
"""

import asyncio
from collections.abc import AsyncGenerator, Callable
from typing import Any

from ..adapters.openrouter_client import (
    query_model,
    query_model_streaming,
    query_model_streaming_with_tools,
)
from ..adapters.tavily_search import SEARCH_TOOL, format_search_results, search_web
from ..settings import CHAIRMAN_MODEL, COUNCIL_MODELS
from .debate import query_critique, query_defense, query_initial
from .parsers import extract_critiques_for_model, parse_revised_answer
from .prompts import (
    build_critique_prompt,
    build_debate_synthesis_prompt,
    build_defense_prompt,
    format_responses_for_critique,
    get_date_context,
)


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


async def run_debate(
    user_query: str,
    execute_round: Callable,
    max_rounds: int = 2,
) -> AsyncGenerator[dict[str, Any], None]:
    """
    Single orchestrator that defines the debate round sequence once.

    Delegates execution to the given `execute_round` callback, which must match
    the execute-round protocol: an async generator that yields events and must
    yield a final ``{"type": "round_complete", "responses": [...]}`` event.

    Args:
        user_query: The user's question
        execute_round: Async generator matching the execute-round protocol
        max_rounds: Number of debate rounds (2 = initial + critique + defense)

    Yields:
        {'type': 'round_start', 'round_number': int, 'round_type': str}
        (pass-through events from execute_round)
        {'type': 'round_complete', 'round_number': int, 'round_type': str, 'responses': List}
        {'type': 'error', 'message': str}
        {'type': 'debate_complete', 'rounds': List}
    """
    rounds = []

    # Build the round sequence: initial, critique, defense, then alternating
    round_sequence = [
        (1, "initial"),
        (2, "critique"),
        (3, "defense"),
    ]
    # Additional rounds if max_rounds > 2
    round_num = 4
    while round_num <= max_rounds + 1:
        if round_num % 2 == 0:
            round_sequence.append((round_num, "critique"))
        else:
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

    Yields:
        {'type': 'model_start', 'model': str}
        {'type': 'model_complete', 'model': str, 'response': Dict}
        {'type': 'model_error', 'model': str, 'error': str}
        {'type': 'round_complete', 'responses': List}
    """
    # Build query functions based on round type using shared per-round functions
    if round_type == "initial":

        async def _query_initial(model: str):
            return await query_initial(model, user_query)

        query_funcs = {model: _query_initial for model in COUNCIL_MODELS}

    elif round_type == "critique":
        initial_responses = context.get("initial_responses", [])

        async def _query_critique(model: str):
            return await query_critique(model, user_query, initial_responses)

        query_funcs = {model: _query_critique for model in COUNCIL_MODELS}

    elif round_type == "defense":
        initial_responses = context.get("initial_responses", [])
        critique_responses = context.get("critique_responses", [])

        async def _query_defense(model: str):
            return await query_defense(model, user_query, initial_responses, critique_responses)

        query_funcs = {model: _query_defense for model in COUNCIL_MODELS}

    else:
        raise ValueError(f"Unknown round type: {round_type}")

    # Wrapper to include model identity in result with timeout
    async def query_with_model(model: str):
        try:
            # Apply per-model timeout
            result = await asyncio.wait_for(query_funcs[model](model), timeout=model_timeout)
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

    Yields:
        {'type': 'model_start', 'model': str}
        {'type': 'token', 'model': str, 'content': str}
        {'type': 'tool_call', 'model': str, 'tool': str, 'args': dict}
        {'type': 'tool_result', 'model': str, 'tool': str, 'result': str}
        {'type': 'model_complete', 'model': str, 'response': Dict}
        {'type': 'model_error', 'model': str, 'error': str}
        {'type': 'round_complete', 'responses': List}
    """
    query_with_date = get_date_context() + user_query
    tools = [SEARCH_TOOL]
    responses = []

    # Build per-model prompt and determine tool availability
    initial_responses = context.get("initial_responses", [])
    critique_responses = context.get("critique_responses", [])

    if round_type == "initial":
        with_tools = True

        def build_prompt(_model: str) -> str:
            return query_with_date

    elif round_type == "critique":
        with_tools = False
        responses_text = format_responses_for_critique(initial_responses)

        def build_prompt(model: str) -> str:
            return build_critique_prompt(user_query, responses_text, model)

    elif round_type == "defense":
        with_tools = True
        model_to_response = {r["model"]: r["response"] for r in initial_responses}

        def build_prompt(model: str) -> str:
            original = model_to_response.get(model, "")
            critiques = extract_critiques_for_model(model, critique_responses)
            return build_defense_prompt(user_query, original, critiques)

    else:
        raise ValueError(f"Unknown round type: {round_type}")

    for model in COUNCIL_MODELS:
        yield {"type": "model_start", "model": model}

        prompt = build_prompt(model)
        messages = [{"role": "user", "content": prompt}]
        full_content = ""
        tool_calls_made = []

        try:
            if with_tools:
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
                        break
            else:
                async for event in query_model_streaming(model, messages):
                    if event["type"] == "token":
                        full_content += event["content"]
                        yield {"type": "token", "model": model, "content": event["content"]}
                    elif event["type"] == "error":
                        yield {"type": "model_error", "model": model, "error": event["error"]}
                        break

            if full_content:
                result = {"model": model, "response": full_content}
                if round_type == "defense":
                    result["revised_answer"] = parse_revised_answer(full_content)
                if tool_calls_made:
                    result["tool_calls_made"] = tool_calls_made
                responses.append(result)
                yield {"type": "model_complete", "model": model, "response": result}

        except Exception as e:
            yield {"type": "model_error", "model": model, "error": str(e)}

    yield {"type": "round_complete", "responses": responses}


async def run_debate_parallel(
    user_query: str, max_rounds: int = 2, skip_synthesis: bool = False
) -> AsyncGenerator[dict[str, Any], None]:
    """
    Stream the complete debate flow, yielding events as each model completes.

    Args:
        user_query: The user's question
        max_rounds: Number of debate rounds (2 = initial + critique + defense)
        skip_synthesis: If True, skip chairman synthesis (for ReAct mode)

    Yields:
        {'type': 'round_start', 'round_number': int, 'round_type': str}
        {'type': 'model_complete', 'model': str, 'response': Dict}
        {'type': 'model_error', 'model': str, 'error': str}
        {'type': 'round_complete', 'round_number': int, 'round_type': str, 'responses': List}
        {'type': 'synthesis_start'}
        {'type': 'synthesis_complete', 'synthesis': Dict}
        {'type': 'complete', 'rounds': List, 'synthesis': Dict}
    """
    rounds = []

    # Round 1: Initial responses
    yield {"type": "round_start", "round_number": 1, "round_type": "initial"}

    initial_responses = []
    async for event in debate_round_parallel(
        round_type="initial",
        user_query=user_query,
        context={},
    ):
        if event["type"] == "round_complete":
            initial_responses = event["responses"]
            rounds.append(
                {"round_number": 1, "round_type": "initial", "responses": initial_responses}
            )
            yield {
                "type": "round_complete",
                "round_number": 1,
                "round_type": "initial",
                "responses": initial_responses,
            }
        else:
            yield event

    # Check if we have enough responses to continue
    if len(initial_responses) < 2:
        yield {
            "type": "complete",
            "rounds": rounds,
            "synthesis": {
                "model": "error",
                "response": "Not enough models responded to conduct a debate. Need at least 2 models.",
            },
        }
        return

    # Round 2: Critiques
    yield {"type": "round_start", "round_number": 2, "round_type": "critique"}

    critique_responses = []
    async for event in debate_round_parallel(
        round_type="critique",
        user_query=user_query,
        context={"initial_responses": initial_responses},
    ):
        if event["type"] == "round_complete":
            critique_responses = event["responses"]
            rounds.append(
                {"round_number": 2, "round_type": "critique", "responses": critique_responses}
            )
            yield {
                "type": "round_complete",
                "round_number": 2,
                "round_type": "critique",
                "responses": critique_responses,
            }
        else:
            yield event

    # Round 3: Defense/Revision
    yield {"type": "round_start", "round_number": 3, "round_type": "defense"}

    defense_responses = []
    async for event in debate_round_parallel(
        round_type="defense",
        user_query=user_query,
        context={
            "initial_responses": initial_responses,
            "critique_responses": critique_responses,
        },
    ):
        if event["type"] == "round_complete":
            defense_responses = event["responses"]
            rounds.append(
                {"round_number": 3, "round_type": "defense", "responses": defense_responses}
            )
            yield {
                "type": "round_complete",
                "round_number": 3,
                "round_type": "defense",
                "responses": defense_responses,
            }
        else:
            yield event

    # Additional rounds if requested
    current_responses = defense_responses
    round_num = 4
    while round_num <= max_rounds + 1:  # +1 because max_rounds=2 means 3 actual rounds
        if round_num % 2 == 0:
            # Even rounds: critique
            yield {"type": "round_start", "round_number": round_num, "round_type": "critique"}

            critique_responses = []
            async for event in debate_round_parallel(
                round_type="critique",
                user_query=user_query,
                context={"initial_responses": current_responses},
            ):
                if event["type"] == "round_complete":
                    critique_responses = event["responses"]
                    rounds.append(
                        {
                            "round_number": round_num,
                            "round_type": "critique",
                            "responses": critique_responses,
                        }
                    )
                    yield {
                        "type": "round_complete",
                        "round_number": round_num,
                        "round_type": "critique",
                        "responses": critique_responses,
                    }
                else:
                    yield event
        else:
            # Odd rounds: defense
            yield {"type": "round_start", "round_number": round_num, "round_type": "defense"}

            defense_responses = []
            async for event in debate_round_parallel(
                round_type="defense",
                user_query=user_query,
                context={
                    "initial_responses": current_responses,
                    "critique_responses": critique_responses,
                },
            ):
                if event["type"] == "round_complete":
                    defense_responses = event["responses"]
                    rounds.append(
                        {
                            "round_number": round_num,
                            "round_type": "defense",
                            "responses": defense_responses,
                        }
                    )
                    yield {
                        "type": "round_complete",
                        "round_number": round_num,
                        "round_type": "defense",
                        "responses": defense_responses,
                    }
                else:
                    yield event
            current_responses = defense_responses

        round_num += 1

    # Chairman synthesis (skip if using ReAct mode)
    synthesis = None
    if not skip_synthesis:
        yield {"type": "synthesis_start"}
        synthesis_prompt = build_debate_synthesis_prompt(user_query, rounds, len(rounds))
        messages = [{"role": "user", "content": synthesis_prompt}]
        response = await query_model(CHAIRMAN_MODEL, messages)
        if response is None:
            synthesis = {
                "model": CHAIRMAN_MODEL,
                "response": "Error: Unable to generate debate synthesis.",
            }
        else:
            synthesis = {"model": CHAIRMAN_MODEL, "response": response.get("content", "")}
        yield {"type": "synthesis_complete", "synthesis": synthesis}

    # Final complete event with all data
    yield {"type": "complete", "rounds": rounds, "synthesis": synthesis}


async def run_debate_streaming(
    user_query: str, max_rounds: int = 2, skip_synthesis: bool = False
) -> AsyncGenerator[dict[str, Any], None]:
    """
    Stream debate with token-level streaming, one model at a time.

    Args:
        user_query: The user's question
        max_rounds: Number of debate rounds (2 = initial + critique + defense)
        skip_synthesis: If True, skip chairman synthesis (for ReAct mode)

    Yields:
        {'type': 'round_start', 'round_number': int, 'round_type': str}
        {'type': 'model_start', 'model': str}
        {'type': 'token', 'model': str, 'content': str}
        {'type': 'model_complete', 'model': str, 'response': Dict}
        {'type': 'model_error', 'model': str, 'error': str}
        {'type': 'round_complete', 'round_number': int, 'round_type': str, 'responses': List}
        {'type': 'synthesis_start'}
        {'type': 'synthesis_token', 'content': str}
        {'type': 'synthesis_complete', 'synthesis': Dict}
        {'type': 'complete', 'rounds': List, 'synthesis': Dict}
    """
    query_with_date = get_date_context() + user_query
    rounds = []
    tools = [SEARCH_TOOL]

    async def stream_initial_round_with_tools():
        """
        Initial round with tool support (web search) AND token streaming.
        Uses query_model_streaming_with_tools for both streaming and tool calling.
        """
        yield {"type": "round_start", "round_number": 1, "round_type": "initial"}

        responses = []
        messages = [{"role": "user", "content": query_with_date}]

        for model in COUNCIL_MODELS:
            yield {"type": "model_start", "model": model}

            full_content = ""
            tool_calls_made = []

            try:
                async for event in query_model_streaming_with_tools(
                    model=model, messages=messages, tools=tools, tool_executor=execute_tool
                ):
                    if event["type"] == "token":
                        full_content += event["content"]
                        yield {"type": "token", "model": model, "content": event["content"]}
                    elif event["type"] == "tool_call":
                        # Yield tool call event so CLI can show "searching..."
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
                        break

                if full_content:
                    result = {"model": model, "response": full_content}
                    if tool_calls_made:
                        result["tool_calls_made"] = tool_calls_made
                    responses.append(result)
                    yield {"type": "model_complete", "model": model, "response": result}

            except Exception as e:
                yield {"type": "model_error", "model": model, "error": str(e)}

        yield {
            "type": "round_complete",
            "round_number": 1,
            "round_type": "initial",
            "responses": responses,
        }

    async def stream_round(
        round_num: int,
        round_type: str,
        build_prompt_fn: Callable[[str], str],
        with_tools: bool = False,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Stream a single round (critique/defense), one model at a time.

        Args:
            round_num: The round number
            round_type: Type of round ("critique" or "defense")
            build_prompt_fn: Function that takes model name and returns prompt
            with_tools: If True, enable web search tool for this round
        """
        yield {"type": "round_start", "round_number": round_num, "round_type": round_type}

        responses = []
        round_tools = [SEARCH_TOOL] if with_tools else None

        for model in COUNCIL_MODELS:
            yield {"type": "model_start", "model": model}

            prompt = build_prompt_fn(model)
            messages = [{"role": "user", "content": prompt}]
            full_content = ""
            tool_calls_made = []

            if with_tools:
                # Use streaming with tool support
                async for event in query_model_streaming_with_tools(
                    model=model, messages=messages, tools=round_tools, tool_executor=execute_tool
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
                        break
            else:
                # Regular streaming without tools
                async for event in query_model_streaming(model, messages):
                    if event["type"] == "token":
                        full_content += event["content"]
                        yield {"type": "token", "model": model, "content": event["content"]}
                    elif event["type"] == "error":
                        yield {"type": "model_error", "model": model, "error": event["error"]}
                        break

            if full_content:
                result = {"model": model, "response": full_content}
                if round_type == "defense":
                    result["revised_answer"] = parse_revised_answer(full_content)
                if tool_calls_made:
                    result["tool_calls_made"] = tool_calls_made
                responses.append(result)
                yield {"type": "model_complete", "model": model, "response": result}

        yield {
            "type": "round_complete",
            "round_number": round_num,
            "round_type": round_type,
            "responses": responses,
        }

    # Round 1: Initial responses (with tool support for web search)
    initial_responses = []
    async for event in stream_initial_round_with_tools():
        yield event
        if event["type"] == "round_complete":
            initial_responses = event["responses"]
            rounds.append(
                {"round_number": 1, "round_type": "initial", "responses": initial_responses}
            )

    if len(initial_responses) < 2:
        yield {
            "type": "complete",
            "rounds": rounds,
            "synthesis": {
                "model": "error",
                "response": "Not enough models responded to conduct a debate.",
            },
        }
        return

    # Round 2: Critiques
    responses_text = format_responses_for_critique(initial_responses)

    def build_critique_prompt_for_model(model):
        return build_critique_prompt(user_query, responses_text, model)

    critique_responses = []
    async for event in stream_round(2, "critique", build_critique_prompt_for_model):
        yield event
        if event["type"] == "round_complete":
            critique_responses = event["responses"]
            rounds.append(
                {"round_number": 2, "round_type": "critique", "responses": critique_responses}
            )

    # Round 3: Defense
    model_to_response = {r["model"]: r["response"] for r in initial_responses}

    def build_defense_prompt_for_model(model):
        original = model_to_response.get(model, "")
        critiques = extract_critiques_for_model(model, critique_responses)
        return build_defense_prompt(user_query, original, critiques)

    defense_responses = []
    async for event in stream_round(3, "defense", build_defense_prompt_for_model, with_tools=True):
        yield event
        if event["type"] == "round_complete":
            defense_responses = event["responses"]
            rounds.append(
                {"round_number": 3, "round_type": "defense", "responses": defense_responses}
            )

    # Chairman synthesis with streaming (skip if using ReAct mode)
    synthesis = None
    if not skip_synthesis:
        yield {"type": "synthesis_start"}

        chairman_prompt = build_debate_synthesis_prompt(user_query, rounds, len(rounds))
        messages = [{"role": "user", "content": chairman_prompt}]
        synthesis_content = ""

        async for event in query_model_streaming(CHAIRMAN_MODEL, messages):
            if event["type"] == "token":
                synthesis_content += event["content"]
                yield {"type": "synthesis_token", "content": event["content"]}
            elif event["type"] == "error":
                synthesis_content = f"Error: {event['error']}"

        synthesis = {"model": CHAIRMAN_MODEL, "response": synthesis_content}
        yield {"type": "synthesis_complete", "synthesis": synthesis}

    yield {"type": "complete", "rounds": rounds, "synthesis": synthesis}
