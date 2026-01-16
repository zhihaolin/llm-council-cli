"""OpenRouter API client for making LLM requests."""

import json
import httpx
from typing import List, Dict, Any, Optional, Callable

from .config import OPENROUTER_API_KEY, OPENROUTER_API_URL


async def query_model(
    model: str,
    messages: List[Dict[str, str]],
    timeout: float = 120.0
) -> Optional[Dict[str, Any]]:
    """
    Query a single model via OpenRouter API.

    Args:
        model: OpenRouter model identifier (e.g., "openai/gpt-4o")
        messages: List of message dicts with 'role' and 'content'
        timeout: Request timeout in seconds

    Returns:
        Response dict with 'content' and optional 'reasoning_details', or None if failed
    """
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": model,
        "messages": messages,
    }

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                OPENROUTER_API_URL,
                headers=headers,
                json=payload
            )
            response.raise_for_status()

            data = response.json()
            message = data['choices'][0]['message']

            return {
                'content': message.get('content'),
                'reasoning_details': message.get('reasoning_details')
            }

    except Exception as e:
        print(f"Error querying model {model}: {e}")
        return None


async def query_model_with_tools(
    model: str,
    messages: List[Dict[str, Any]],
    tools: List[Dict[str, Any]],
    tool_executor: Callable[[str, Dict[str, Any]], Any],
    timeout: float = 120.0,
    max_tool_calls: int = 5
) -> Optional[Dict[str, Any]]:
    """
    Query a model with tool calling support.

    Args:
        model: OpenRouter model identifier
        messages: List of message dicts
        tools: List of tool definitions (OpenAI function calling format)
        tool_executor: Async function to execute tools: (tool_name, args) -> result
        timeout: Request timeout in seconds
        max_tool_calls: Maximum number of tool call rounds to prevent infinite loops

    Returns:
        Response dict with 'content', 'tool_calls_made' list, or None if failed
    """
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }

    # Copy messages to avoid mutating original
    conversation = list(messages)
    tool_calls_made = []

    async with httpx.AsyncClient(timeout=timeout) as client:
        for _ in range(max_tool_calls):
            payload = {
                "model": model,
                "messages": conversation,
                "tools": tools,
            }

            try:
                response = await client.post(
                    OPENROUTER_API_URL,
                    headers=headers,
                    json=payload
                )
                response.raise_for_status()
                data = response.json()
                message = data['choices'][0]['message']

                # Check if model wants to call a tool
                if message.get('tool_calls'):
                    # Add assistant message with tool calls
                    conversation.append(message)

                    # Process each tool call
                    for tool_call in message['tool_calls']:
                        tool_name = tool_call['function']['name']
                        tool_args = json.loads(tool_call['function']['arguments'])

                        # Execute the tool
                        try:
                            result = await tool_executor(tool_name, tool_args)
                            tool_result = str(result) if not isinstance(result, str) else result
                        except Exception as e:
                            tool_result = f"Error executing tool: {e}"

                        tool_calls_made.append({
                            "tool": tool_name,
                            "args": tool_args,
                            "result_preview": tool_result[:200] + "..." if len(tool_result) > 200 else tool_result
                        })

                        # Add tool result to conversation
                        conversation.append({
                            "role": "tool",
                            "tool_call_id": tool_call['id'],
                            "content": tool_result
                        })

                    # Continue loop to get next response
                    continue

                # No tool calls - we have the final response
                return {
                    'content': message.get('content'),
                    'reasoning_details': message.get('reasoning_details'),
                    'tool_calls_made': tool_calls_made
                }

            except Exception as e:
                print(f"Error querying model {model}: {e}")
                return None

    # Max tool calls reached
    return {
        'content': "Max tool calls reached without final response.",
        'tool_calls_made': tool_calls_made
    }


async def query_models_parallel(
    models: List[str],
    messages: List[Dict[str, str]]
) -> Dict[str, Optional[Dict[str, Any]]]:
    """
    Query multiple models in parallel.

    Args:
        models: List of OpenRouter model identifiers
        messages: List of message dicts to send to each model

    Returns:
        Dict mapping model identifier to response dict (or None if failed)
    """
    import asyncio

    # Create tasks for all models
    tasks = [query_model(model, messages) for model in models]

    # Wait for all to complete
    responses = await asyncio.gather(*tasks)

    # Map models to their responses
    return {model: response for model, response in zip(models, responses)}
