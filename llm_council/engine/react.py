"""
ReAct (Reasoning + Acting) logic for council members.

Contains:
- ``council_react_loop``: Per-model ReAct loop for council members
"""

import re
from collections.abc import AsyncGenerator
from typing import Any

from ..adapters.openrouter_client import query_model_streaming
from ..adapters.tavily_search import format_search_results, search_web
from .parsers import parse_react_output


async def council_react_loop(
    model: str, prompt: str, max_iterations: int = 3
) -> AsyncGenerator[dict[str, Any], None]:
    """
    Text-based ReAct reasoning loop for a single council member.

    The model reasons about whether to search, executes searches, and
    eventually calls ``respond()`` to produce its final answer.

    Args:
        model: Model identifier (e.g. "openai/gpt-5.2")
        prompt: Pre-built prompt string (already wrapped with ReAct instructions)
        max_iterations: Maximum reasoning iterations (default: 3)

    Yields:
        {'type': 'token', 'content': str} - Streaming tokens
        {'type': 'thought', 'content': str} - Complete thought
        {'type': 'action', 'tool': str, 'args': str} - Action taken
        {'type': 'observation', 'content': str} - Tool result
        {'type': 'done', 'content': str, 'tool_calls_made': list} - Final response
    """
    messages = [{"role": "user", "content": prompt}]
    iteration = 0
    accumulated_content = ""
    tool_calls_made: list[dict[str, Any]] = []

    while iteration < max_iterations:
        iteration += 1
        accumulated_content = ""

        async for event in query_model_streaming(model, messages):
            if event["type"] == "token":
                accumulated_content += event["content"]
                yield {"type": "token", "content": event["content"]}
            elif event["type"] == "done":
                accumulated_content = event["content"]
            elif event["type"] == "error":
                yield {
                    "type": "done",
                    "content": f"Error: {event['error']}",
                    "tool_calls_made": tool_calls_made,
                }
                return

        thought, action, action_args = parse_react_output(accumulated_content)

        if thought:
            yield {"type": "thought", "content": thought}

        if action == "respond":
            # Extract response content after "Action: respond()"
            resp_match = re.search(
                r"Action:\s*respond\s*\(\s*\)\s*\n*(.*)",
                accumulated_content,
                re.DOTALL | re.IGNORECASE,
            )
            response_text = resp_match.group(1).strip() if resp_match else accumulated_content

            yield {"type": "action", "tool": "respond", "args": None}
            yield {"type": "done", "content": response_text, "tool_calls_made": tool_calls_made}
            return

        elif action == "synthesize":
            # Also accept synthesize() as terminal (backward compat)
            resp_match = re.search(
                r"Action:\s*synthesize\s*\(\s*\)\s*\n*(.*)",
                accumulated_content,
                re.DOTALL | re.IGNORECASE,
            )
            response_text = resp_match.group(1).strip() if resp_match else accumulated_content

            yield {"type": "action", "tool": "respond", "args": None}
            yield {"type": "done", "content": response_text, "tool_calls_made": tool_calls_made}
            return

        elif action == "search_web":
            yield {"type": "action", "tool": "search_web", "args": action_args}

            try:
                search_results = await search_web(action_args)
                observation = format_search_results(search_results)
            except Exception as e:
                observation = f"Search failed: {str(e)}"

            tool_calls_made.append(
                {
                    "tool": "search_web",
                    "args": {"query": action_args},
                    "result_preview": observation[:200],
                }
            )
            yield {"type": "observation", "content": observation}

            messages.append({"role": "assistant", "content": accumulated_content})
            messages.append(
                {
                    "role": "user",
                    "content": f"Observation: {observation}\n\nContinue your reasoning:",
                }
            )

        else:
            # Invalid or missing action
            if iteration < max_iterations:
                messages.append({"role": "assistant", "content": accumulated_content})
                messages.append(
                    {
                        "role": "user",
                        "content": 'Please respond with a valid Action: either search_web("query") or respond()',
                    }
                )
            else:
                yield {
                    "type": "done",
                    "content": accumulated_content,
                    "tool_calls_made": tool_calls_made,
                }
                return

    # Max iterations reached
    yield {"type": "done", "content": accumulated_content, "tool_calls_made": tool_calls_made}
