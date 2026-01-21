"""OpenRouter API client for making LLM requests."""

import json
import httpx
from typing import List, Dict, Any, Optional, Callable, AsyncGenerator

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


async def query_model_streaming(
    model: str,
    messages: List[Dict[str, str]],
    timeout: float = 120.0
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    Query a model with streaming response.

    Args:
        model: OpenRouter model identifier
        messages: List of message dicts with 'role' and 'content'
        timeout: Request timeout in seconds

    Yields:
        {'type': 'token', 'content': str} - Content tokens as they arrive
        {'type': 'done', 'content': str} - Final complete content
        {'type': 'error', 'error': str} - If an error occurs
    """
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": model,
        "messages": messages,
        "stream": True,
    }

    full_content = ""

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream(
                "POST",
                OPENROUTER_API_URL,
                headers=headers,
                json=payload
            ) as response:
                response.raise_for_status()

                async for line in response.aiter_lines():
                    if not line:
                        continue
                    if not line.startswith("data: "):
                        continue

                    data_str = line[6:]  # Remove "data: " prefix

                    if data_str == "[DONE]":
                        break

                    try:
                        data = json.loads(data_str)
                        delta = data.get("choices", [{}])[0].get("delta", {})
                        content = delta.get("content", "")

                        if content:
                            full_content += content
                            yield {"type": "token", "content": content}

                    except json.JSONDecodeError:
                        continue

        yield {"type": "done", "content": full_content}

    except Exception as e:
        yield {"type": "error", "error": str(e)}


async def query_model_streaming_with_tools(
    model: str,
    messages: List[Dict[str, Any]],
    tools: List[Dict[str, Any]],
    tool_executor: Callable[[str, Dict[str, Any]], Any],
    timeout: float = 120.0,
    max_tool_calls: int = 3
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    Query a model with streaming response AND tool calling support.

    Args:
        model: OpenRouter model identifier
        messages: List of message dicts
        tools: List of tool definitions (OpenAI function calling format)
        tool_executor: Async function to execute tools: (tool_name, args) -> result
        timeout: Request timeout in seconds
        max_tool_calls: Maximum tool call rounds to prevent infinite loops

    Yields:
        {'type': 'token', 'content': str} - Content tokens as they arrive
        {'type': 'tool_call', 'tool': str, 'args': dict} - When a tool is called
        {'type': 'tool_result', 'tool': str, 'result': str} - Tool execution result
        {'type': 'done', 'content': str, 'tool_calls_made': list} - Final complete content
        {'type': 'error', 'error': str} - If an error occurs
    """
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }

    conversation = list(messages)
    tool_calls_made = []
    full_content = ""

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            for _ in range(max_tool_calls + 1):
                payload = {
                    "model": model,
                    "messages": conversation,
                    "tools": tools,
                    "stream": True,
                }

                current_content = ""
                tool_calls_buffer = {}  # id -> {name, arguments}

                async with client.stream(
                    "POST",
                    OPENROUTER_API_URL,
                    headers=headers,
                    json=payload
                ) as response:
                    response.raise_for_status()

                    async for line in response.aiter_lines():
                        if not line:
                            continue
                        if not line.startswith("data: "):
                            continue

                        data_str = line[6:]

                        if data_str == "[DONE]":
                            break

                        try:
                            data = json.loads(data_str)
                            choice = data.get("choices", [{}])[0]
                            delta = choice.get("delta", {})

                            # Handle content tokens
                            content = delta.get("content", "")
                            if content:
                                current_content += content
                                yield {"type": "token", "content": content}

                            # Handle tool calls (streamed in chunks)
                            # NOTE: First chunk has id+name, subsequent chunks have only index+arguments
                            # Use index as primary key since id is not repeated in subsequent chunks
                            if "tool_calls" in delta:
                                for tc in delta["tool_calls"]:
                                    tc_index = tc.get("index", 0)
                                    key = f"idx_{tc_index}"

                                    if key not in tool_calls_buffer:
                                        tool_calls_buffer[key] = {
                                            "id": None,
                                            "name": "",
                                            "arguments": ""
                                        }

                                    # Capture id from first chunk
                                    if tc.get("id"):
                                        tool_calls_buffer[key]["id"] = tc["id"]

                                    if "function" in tc:
                                        fn = tc["function"]
                                        if "name" in fn:
                                            tool_calls_buffer[key]["name"] = fn["name"]
                                        if "arguments" in fn:
                                            tool_calls_buffer[key]["arguments"] += fn["arguments"]

                        except json.JSONDecodeError:
                            continue

                # After stream ends, check if we have tool calls to execute
                if tool_calls_buffer:
                    # Build assistant message with tool calls
                    # Note: content must be string or omitted, not None, for some models
                    assistant_msg = {"role": "assistant", "tool_calls": []}
                    if current_content:
                        assistant_msg["content"] = current_content
                    tool_results_to_add = []

                    for key, tc_data in tool_calls_buffer.items():
                        tool_name = tc_data["name"]
                        try:
                            tool_args = json.loads(tc_data["arguments"]) if tc_data["arguments"] else {}
                        except json.JSONDecodeError:
                            tool_args = {}

                        tool_call_id = tc_data["id"] or f"call_{key}"
                        assistant_msg["tool_calls"].append({
                            "id": tool_call_id,
                            "type": "function",
                            "function": {"name": tool_name, "arguments": json.dumps(tool_args)}
                        })

                        # Yield tool call event
                        yield {"type": "tool_call", "tool": tool_name, "args": tool_args}

                        # Execute tool
                        try:
                            result = await tool_executor(tool_name, tool_args)
                            tool_result = str(result) if not isinstance(result, str) else result
                        except Exception as e:
                            tool_result = f"Error executing tool: {e}"

                        yield {"type": "tool_result", "tool": tool_name, "result": tool_result[:200]}

                        tool_calls_made.append({
                            "tool": tool_name,
                            "args": tool_args,
                            "result_preview": tool_result[:200] + "..." if len(tool_result) > 200 else tool_result
                        })

                        # Queue tool result to add to conversation
                        tool_results_to_add.append({
                            "role": "tool",
                            "tool_call_id": tool_call_id,
                            "content": tool_result
                        })

                    # Add assistant message with all tool calls, then all tool results
                    conversation.append(assistant_msg)
                    conversation.extend(tool_results_to_add)

                    # Continue loop to get response after tool execution
                    continue

                # No tool calls - we have the final response
                full_content = current_content
                break

        yield {"type": "done", "content": full_content, "tool_calls_made": tool_calls_made}

    except Exception as e:
        yield {"type": "error", "error": str(e)}


async def query_model_with_tools(
    model: str,
    messages: List[Dict[str, Any]],
    tools: List[Dict[str, Any]],
    tool_executor: Callable[[str, Dict[str, Any]], Any],
    timeout: float = 120.0,
    max_tool_calls: int = 10
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
