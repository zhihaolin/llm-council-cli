"""
ReAct (Reasoning + Acting) chairman logic for council deliberation.

The chairman uses a reasoning loop to optionally verify facts via web search
before synthesizing the final answer.
"""

import re
from typing import Any, AsyncGenerator, Dict, List

from ..config import CHAIRMAN_MODEL
from ..openrouter import query_model_streaming
from ..search import search_web, format_search_results
from .parsers import parse_react_output
from .prompts import build_react_prompt


async def synthesize_with_react(
    user_query: str,
    context: str,
    max_iterations: int = 3
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    ReAct synthesis loop for chairman.

    The chairman reasons about the responses, optionally searches for
    verification, and produces a final synthesis.

    Args:
        user_query: Original user question
        context: Formatted context from ranking or debate mode
        max_iterations: Maximum reasoning iterations (default: 3)

    Yields:
        {'type': 'token', 'content': str} - Streaming tokens
        {'type': 'thought', 'content': str} - Complete thought
        {'type': 'action', 'tool': str, 'args': str} - Action taken
        {'type': 'observation', 'content': str} - Tool result
        {'type': 'synthesis', 'response': str, 'model': str} - Final synthesis
    """
    messages = [{"role": "user", "content": build_react_prompt(context)}]
    iteration = 0
    accumulated_content = ""

    while iteration < max_iterations:
        iteration += 1
        accumulated_content = ""

        # Stream the chairman's response
        async for event in query_model_streaming(CHAIRMAN_MODEL, messages):
            if event["type"] == "token":
                accumulated_content += event["content"]
                yield {"type": "token", "content": event["content"]}
            elif event["type"] == "done":
                accumulated_content = event["content"]
            elif event["type"] == "error":
                # On error, force synthesis with error message
                yield {"type": "synthesis", "response": f"Error: {event['error']}", "model": CHAIRMAN_MODEL}
                return

        # Parse the response
        thought, action, action_args = parse_react_output(accumulated_content)

        if thought:
            yield {"type": "thought", "content": thought}

        if action == "synthesize":
            # Extract synthesis content (everything after "Action: synthesize()")
            synth_match = re.search(r'Action:\s*synthesize\s*\(\s*\)\s*\n*(.*)', accumulated_content, re.DOTALL | re.IGNORECASE)
            synthesis_text = synth_match.group(1).strip() if synth_match else ""

            # If model didn't provide synthesis content, ask for it directly
            if not synthesis_text:
                yield {"type": "action", "tool": "synthesize", "args": None}
                # Request just the synthesis
                messages.append({"role": "assistant", "content": accumulated_content})
                messages.append({"role": "user", "content": "Please provide your final synthesized answer now (no Thought/Action format, just the answer):"})

                synthesis_text = ""
                async for event in query_model_streaming(CHAIRMAN_MODEL, messages):
                    if event["type"] == "token":
                        synthesis_text += event["content"]
                        yield {"type": "token", "content": event["content"]}
                    elif event["type"] == "done":
                        synthesis_text = event["content"]

                yield {"type": "synthesis", "response": synthesis_text.strip(), "model": CHAIRMAN_MODEL}
                return

            yield {"type": "action", "tool": "synthesize", "args": None}
            yield {"type": "synthesis", "response": synthesis_text, "model": CHAIRMAN_MODEL}
            return

        elif action == "search_web":
            yield {"type": "action", "tool": "search_web", "args": action_args}

            # Execute search
            try:
                search_results = await search_web(action_args)
                observation = format_search_results(search_results)
            except Exception as e:
                observation = f"Search failed: {str(e)}"

            yield {"type": "observation", "content": observation}

            # Add to conversation for next iteration
            messages.append({"role": "assistant", "content": accumulated_content})
            messages.append({"role": "user", "content": f"Observation: {observation}\n\nContinue your reasoning:"})

        else:
            # Invalid or missing action - prompt to try again or synthesize
            if iteration < max_iterations:
                messages.append({"role": "assistant", "content": accumulated_content})
                messages.append({"role": "user", "content": "Please respond with a valid Action: either search_web(\"query\") or synthesize()"})
            else:
                # Max iterations reached, force synthesis
                yield {"type": "synthesis", "response": accumulated_content, "model": CHAIRMAN_MODEL}
                return

    # Max iterations reached without synthesize
    yield {"type": "synthesis", "response": accumulated_content, "model": CHAIRMAN_MODEL}
