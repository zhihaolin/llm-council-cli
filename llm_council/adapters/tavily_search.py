"""Web search functionality using Tavily API."""

import os
from typing import Any

import httpx

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
TAVILY_API_URL = "https://api.tavily.com/search"

# Tool definition for OpenRouter/OpenAI function calling
SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "search_web",
        "description": "Search the web for current information. Use this when you need up-to-date information, recent events, current statistics, or facts you're unsure about.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The search query to look up on the web"}
            },
            "required": ["query"],
        },
    },
}


async def search_web(query: str, max_results: int = 5) -> dict[str, Any]:
    """
    Search the web using Tavily API.

    Args:
        query: Search query string
        max_results: Maximum number of results to return

    Returns:
        Dict with 'results' list containing title, url, and content
    """
    if not TAVILY_API_KEY:
        return {"error": "TAVILY_API_KEY not configured", "results": []}

    payload = {
        "api_key": TAVILY_API_KEY,
        "query": query,
        "search_depth": "basic",
        "max_results": max_results,
        "include_answer": True,
        "include_raw_content": False,
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(TAVILY_API_URL, json=payload)
            response.raise_for_status()
            data = response.json()

            # Format results for LLM consumption
            results = []
            for item in data.get("results", []):
                results.append(
                    {
                        "title": item.get("title", ""),
                        "url": item.get("url", ""),
                        "content": item.get("content", ""),
                    }
                )

            return {"answer": data.get("answer", ""), "results": results}

    except Exception as e:
        return {"error": str(e), "results": []}


def format_search_results(search_response: dict[str, Any]) -> str:
    """
    Format search results as a string for inclusion in LLM context.

    Args:
        search_response: Response from search_web()

    Returns:
        Formatted string with search results
    """
    if "error" in search_response:
        return f"Search error: {search_response['error']}"

    parts = []

    # Include Tavily's AI-generated answer if available
    if search_response.get("answer"):
        parts.append(f"Quick Answer: {search_response['answer']}")
        parts.append("")

    # Include individual results
    parts.append("Search Results:")
    for i, result in enumerate(search_response.get("results", []), 1):
        parts.append(f"\n{i}. {result['title']}")
        parts.append(f"   URL: {result['url']}")
        parts.append(f"   {result['content']}")

    return "\n".join(parts)
