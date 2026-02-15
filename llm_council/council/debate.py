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


async def debate_round_initial(user_query: str) -> list[dict[str, Any]]:
    """
    Debate Round 1: Collect initial responses from all models.

    Models have access to web search tool and can decide when to use it.

    Args:
        user_query: The user's question

    Returns:
        List of dicts with 'model', 'response', and optionally 'tool_calls_made' keys
    """
    query_with_date = get_date_context() + user_query
    messages = [{"role": "user", "content": query_with_date}]
    tools = [SEARCH_TOOL]

    # Query all models in parallel with tool support
    async def query_single_model(model: str) -> tuple:
        response = await query_model_with_tools(
            model=model, messages=messages, tools=tools, tool_executor=execute_tool
        )
        return model, response

    # Create tasks for all models
    tasks = [query_single_model(model) for model in COUNCIL_MODELS]
    results = await asyncio.gather(*tasks)

    # Format results
    responses = []
    for model, response in results:
        if response is not None:  # Only include successful responses
            result = {"model": model, "response": response.get("content", "")}
            # Include tool calls info if any were made
            if response.get("tool_calls_made"):
                result["tool_calls_made"] = response["tool_calls_made"]
            responses.append(result)

    return responses


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
    # Build the list of all responses for critique
    responses_text = format_responses_for_critique(initial_responses)

    async def get_critique(model: str, own_response: str) -> tuple[str, dict]:
        """Get critique from a single model."""
        critique_prompt = build_critique_prompt(user_query, responses_text, model)
        messages = [{"role": "user", "content": critique_prompt}]
        response = await query_model(model, messages)
        return model, response

    # Query all models in parallel
    tasks = [get_critique(result["model"], result["response"]) for result in initial_responses]
    results = await asyncio.gather(*tasks)

    # Format results
    critique_results = []
    for model, response in results:
        if response is not None:
            critique_results.append({"model": model, "response": response.get("content", "")})

    return critique_results


async def debate_round_defense(
    user_query: str,
    initial_responses: list[dict[str, Any]],
    critique_responses: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Debate Round 3+: Each model defends/revises based on critiques received.

    Args:
        user_query: The original user query
        initial_responses: Results from round 1
        critique_responses: Critiques from round 2

    Returns:
        List of dicts with 'model', 'response', and 'revised_answer' keys
    """

    async def get_defense(model: str, original_response: str) -> tuple[str, dict]:
        """Get defense/revision from a single model."""
        # Extract critiques specifically directed at this model
        critiques_for_me = extract_critiques_for_model(model, critique_responses)
        defense_prompt = build_defense_prompt(user_query, original_response, critiques_for_me)
        messages = [{"role": "user", "content": defense_prompt}]
        response = await query_model(model, messages)
        return model, response

    # Get the original response for each model
    model_to_response = {r["model"]: r["response"] for r in initial_responses}

    # Query all models in parallel
    tasks = [
        get_defense(result["model"], model_to_response[result["model"]])
        for result in initial_responses
        if result["model"] in model_to_response
    ]
    results = await asyncio.gather(*tasks)

    # Format results
    defense_results = []
    for model, response in results:
        if response is not None:
            content = response.get("content", "")
            defense_results.append(
                {
                    "model": model,
                    "response": content,
                    "revised_answer": parse_revised_answer(content),
                }
            )

    return defense_results


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


async def run_debate_council(
    user_query: str, max_rounds: int = 2
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """
    Orchestrate the complete debate flow.

    Args:
        user_query: The user's question
        max_rounds: Number of debate rounds (2 = initial + critique + defense)

    Returns:
        Tuple of (rounds list, synthesis result)
        Each round is: {round_number, round_type, responses}
    """
    rounds = []

    # Round 1: Initial responses
    initial_responses = await debate_round_initial(user_query)

    if len(initial_responses) < 2:
        # Not enough models to have a debate
        return [], {
            "model": "error",
            "response": "Not enough models responded to conduct a debate. Need at least 2 models.",
        }

    rounds.append({"round_number": 1, "round_type": "initial", "responses": initial_responses})

    # Round 2: Critiques
    critique_responses = await debate_round_critique(user_query, initial_responses)

    if len(critique_responses) < 2:
        # Continue with partial results
        pass

    rounds.append({"round_number": 2, "round_type": "critique", "responses": critique_responses})

    # Round 3: Defense/Revision
    defense_responses = await debate_round_defense(
        user_query, initial_responses, critique_responses
    )

    rounds.append({"round_number": 3, "round_type": "defense", "responses": defense_responses})

    # Additional rounds if requested (alternating critique/defense)
    current_responses = defense_responses
    for round_num in range(4, max_rounds + 2):  # +2 because max_rounds=2 means 3 actual rounds
        if round_num % 2 == 0:
            # Even rounds: critique
            critique_responses = await debate_round_critique(user_query, current_responses)
            rounds.append(
                {
                    "round_number": round_num,
                    "round_type": "critique",
                    "responses": critique_responses,
                }
            )
        else:
            # Odd rounds: defense
            defense_responses = await debate_round_defense(
                user_query, current_responses, critique_responses
            )
            rounds.append(
                {"round_number": round_num, "round_type": "defense", "responses": defense_responses}
            )
            current_responses = defense_responses

    # Chairman synthesis
    synthesis = await synthesize_debate(user_query, rounds, len(rounds))

    return rounds, synthesis
