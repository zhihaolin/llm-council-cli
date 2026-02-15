"""
Main orchestration for standard (ranking) council deliberation.

Contains Stage 1-2-3 flow: collect responses, rank, synthesize.
"""

import asyncio
from typing import Any

from ..adapters.openrouter_client import query_model, query_model_with_tools, query_models_parallel
from ..adapters.tavily_search import SEARCH_TOOL, format_search_results, search_web
from ..settings import COUNCIL_MODELS
from .aggregation import calculate_aggregate_rankings
from .parsers import parse_ranking_from_text
from .prompts import (
    build_ranking_prompt,
    build_title_prompt,
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


async def stage1_collect_responses(user_query: str) -> list[dict[str, Any]]:
    """
    Stage 1: Collect individual responses from all council models.

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
    stage1_results = []
    for model, response in results:
        if response is not None:  # Only include successful responses
            result = {"model": model, "response": response.get("content", "")}
            # Include tool calls info if any were made
            if response.get("tool_calls_made"):
                result["tool_calls_made"] = response["tool_calls_made"]
            stage1_results.append(result)

    return stage1_results


async def stage2_collect_rankings(
    user_query: str, stage1_results: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """
    Stage 2: Each model ranks the anonymized responses.

    Args:
        user_query: The original user query
        stage1_results: Results from Stage 1

    Returns:
        Tuple of (rankings list, label_to_model mapping)
    """
    # Create anonymized labels for responses (Response A, Response B, etc.)
    labels = [chr(65 + i) for i in range(len(stage1_results))]  # A, B, C, ...

    # Create mapping from label to model name
    label_to_model = {
        f"Response {label}": result["model"] for label, result in zip(labels, stage1_results)
    }

    # Build the responses text for ranking
    responses_text = "\n\n".join(
        [
            f"Response {label}:\n{result['response']}"
            for label, result in zip(labels, stage1_results)
        ]
    )

    ranking_prompt = build_ranking_prompt(user_query, responses_text)
    messages = [{"role": "user", "content": ranking_prompt}]

    # Get rankings from all council models in parallel
    responses = await query_models_parallel(COUNCIL_MODELS, messages)

    # Format results
    stage2_results = []
    for model, response in responses.items():
        if response is not None:
            full_text = response.get("content", "")
            parsed = parse_ranking_from_text(full_text)
            stage2_results.append({"model": model, "ranking": full_text, "parsed_ranking": parsed})

    return stage2_results, label_to_model


async def run_full_council(user_query: str) -> tuple[list, list, dict]:
    """
    Run Stages 1-2 of the council process (synthesis handled separately via Reflection).

    Args:
        user_query: The user's question

    Returns:
        Tuple of (stage1_results, stage2_results, metadata)
    """
    # Stage 1: Collect individual responses
    stage1_results = await stage1_collect_responses(user_query)

    # If no models responded successfully, return error
    if not stage1_results:
        return [], [], {}

    # Stage 2: Collect rankings
    stage2_results, label_to_model = await stage2_collect_rankings(user_query, stage1_results)

    # Calculate aggregate rankings
    aggregate_rankings = calculate_aggregate_rankings(stage2_results, label_to_model)

    # Prepare metadata
    metadata = {"label_to_model": label_to_model, "aggregate_rankings": aggregate_rankings}

    return stage1_results, stage2_results, metadata


async def generate_conversation_title(user_query: str) -> str:
    """
    Generate a short title for a conversation based on the first user message.

    Args:
        user_query: The first user message

    Returns:
        A short title (3-5 words)
    """
    title_prompt = build_title_prompt(user_query)
    messages = [{"role": "user", "content": title_prompt}]

    # Use gemini-2.5-flash for title generation (fast and cheap)
    response = await query_model("google/gemini-2.5-flash", messages, timeout=30.0)

    if response is None:
        # Fallback to a generic title
        return "New Conversation"

    title = response.get("content", "New Conversation").strip()

    # Clean up the title - remove quotes, limit length
    title = title.strip("\"'")

    # Truncate if too long
    if len(title) > 50:
        title = title[:47] + "..."

    return title
