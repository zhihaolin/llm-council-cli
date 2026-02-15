"""
Debate mode orchestration for council deliberation.

Contains non-streaming debate functions for running multi-round debates.
"""

import asyncio
from typing import Any

from ..adapters.openrouter_client import query_model, query_model_with_tools
from ..adapters.tavily_search import SEARCH_TOOL, format_search_results, search_web
from ..settings import CHAIRMAN_MODEL, COUNCIL_MODELS
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


async def query_initial(model: str, user_query: str) -> dict | None:
    """
    Query a single model for its initial response (Round 1).

    Uses query_model_with_tools so the model can search the web if needed.

    Args:
        model: The model identifier
        user_query: The user's question

    Returns:
        Dict with 'model', 'response', and optionally 'tool_calls_made', or None on failure
    """
    query_with_date = get_date_context() + user_query
    messages = [{"role": "user", "content": query_with_date}]
    tools = [SEARCH_TOOL]

    response = await query_model_with_tools(
        model=model, messages=messages, tools=tools, tool_executor=execute_tool
    )
    if response is None:
        return None

    result = {"model": model, "response": response.get("content", "")}
    if response.get("tool_calls_made"):
        result["tool_calls_made"] = response["tool_calls_made"]
    return result


async def query_critique(
    model: str, user_query: str, initial_responses: list[dict[str, Any]]
) -> dict | None:
    """
    Query a single model for its critique of other models (Round 2).

    Uses query_model (no tools) — critiques evaluate existing responses.

    Args:
        model: The model identifier
        user_query: The original user query
        initial_responses: Results from round 1

    Returns:
        Dict with 'model' and 'response', or None on failure
    """
    responses_text = format_responses_for_critique(initial_responses)
    critique_prompt = build_critique_prompt(user_query, responses_text, model)
    messages = [{"role": "user", "content": critique_prompt}]

    response = await query_model(model, messages)
    if response is None:
        return None

    return {"model": model, "response": response.get("content", "")}


async def query_defense(
    model: str,
    user_query: str,
    initial_responses: list[dict[str, Any]],
    critique_responses: list[dict[str, Any]],
) -> dict | None:
    """
    Query a single model for its defense/revision (Round 3).

    Uses query_model_with_tools so the model can search for evidence to support
    its defense. This fixes the previous asymmetry where batch mode lacked tools.

    Args:
        model: The model identifier
        user_query: The original user query
        initial_responses: Results from round 1
        critique_responses: Critiques from round 2

    Returns:
        Dict with 'model', 'response', 'revised_answer', and optionally
        'tool_calls_made', or None on failure
    """
    model_to_response = {r["model"]: r["response"] for r in initial_responses}
    original_response = model_to_response.get(model, "")
    critiques_for_me = extract_critiques_for_model(model, critique_responses)
    defense_prompt = build_defense_prompt(user_query, original_response, critiques_for_me)
    messages = [{"role": "user", "content": defense_prompt}]
    tools = [SEARCH_TOOL]

    response = await query_model_with_tools(
        model=model, messages=messages, tools=tools, tool_executor=execute_tool
    )
    if response is None:
        return None

    content = response.get("content", "")
    result = {
        "model": model,
        "response": content,
        "revised_answer": parse_revised_answer(content),
    }
    if response.get("tool_calls_made"):
        result["tool_calls_made"] = response["tool_calls_made"]
    return result


async def debate_round_initial(user_query: str) -> list[dict[str, Any]]:
    """
    Debate Round 1: Collect initial responses from all models.

    Models have access to web search tool and can decide when to use it.

    Args:
        user_query: The user's question

    Returns:
        List of dicts with 'model', 'response', and optionally 'tool_calls_made' keys
    """
    tasks = [query_initial(model, user_query) for model in COUNCIL_MODELS]
    results = await asyncio.gather(*tasks)
    return [r for r in results if r is not None]


async def debate_round_critique(
    user_query: str, initial_responses: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """
    Debate Round 2: Each model critiques all other models' responses.

    Args:
        user_query: The original user query
        initial_responses: Results from round 1 (initial answers)

    Returns:
        List of dicts with 'model' and 'response' containing critiques
    """
    tasks = [
        query_critique(result["model"], user_query, initial_responses)
        for result in initial_responses
    ]
    results = await asyncio.gather(*tasks)
    return [r for r in results if r is not None]


async def debate_round_defense(
    user_query: str,
    initial_responses: list[dict[str, Any]],
    critique_responses: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Debate Round 3+: Each model defends/revises based on critiques received.

    Models have access to web search tool to find evidence for their defense.

    Args:
        user_query: The original user query
        initial_responses: Results from round 1
        critique_responses: Critiques from round 2

    Returns:
        List of dicts with 'model', 'response', 'revised_answer', and optionally
        'tool_calls_made' keys
    """
    tasks = [
        query_defense(result["model"], user_query, initial_responses, critique_responses)
        for result in initial_responses
    ]
    results = await asyncio.gather(*tasks)
    return [r for r in results if r is not None]


async def synthesize_debate(
    user_query: str, rounds: list[dict[str, Any]], num_rounds: int
) -> dict[str, Any]:
    """
    Chairman synthesizes based on the full debate transcript.

    Args:
        user_query: The original user query
        rounds: List of round data dicts
        num_rounds: Number of debate rounds completed

    Returns:
        Dict with 'model' and 'response' keys
    """
    chairman_prompt = build_debate_synthesis_prompt(user_query, rounds, num_rounds)
    messages = [{"role": "user", "content": chairman_prompt}]

    # Query the chairman model
    response = await query_model(CHAIRMAN_MODEL, messages)

    if response is None:
        return {"model": CHAIRMAN_MODEL, "response": "Error: Unable to generate debate synthesis."}

    return {"model": CHAIRMAN_MODEL, "response": response.get("content", "")}
