"""
Chairman Reflection synthesis for council deliberation.

The chairman analyses council responses deeply, then produces a final
synthesis — no tools, no iteration, just focused reasoning.
"""

from collections.abc import AsyncGenerator
from typing import Any

from ..adapters.openrouter_client import query_model_streaming
from ..settings import CHAIRMAN_MODEL
from .parsers import parse_reflection_output
from .prompts import build_reflection_prompt


async def synthesize_with_reflection(
    user_query: str, context: str
) -> AsyncGenerator[dict[str, Any], None]:
    """
    Reflection synthesis for chairman.

    Streams a single LLM call. The model analyses the council output,
    then writes its final answer after a ``## Synthesis`` header.

    Args:
        user_query: Original user question
        context: Formatted context from ranking or debate mode

    Yields:
        {'type': 'token', 'content': str} - Streaming tokens
        {'type': 'reflection', 'content': str} - The reflection analysis text
        {'type': 'synthesis', 'response': str, 'model': str} - Final synthesis
    """
    messages = [{"role": "user", "content": build_reflection_prompt(context)}]
    accumulated_content = ""

    async for event in query_model_streaming(CHAIRMAN_MODEL, messages):
        if event["type"] == "token":
            accumulated_content += event["content"]
            yield {"type": "token", "content": event["content"]}
        elif event["type"] == "done":
            accumulated_content = event["content"]
        elif event["type"] == "error":
            yield {
                "type": "synthesis",
                "response": f"Error: {event['error']}",
                "model": CHAIRMAN_MODEL,
            }
            return

    reflection_text, synthesis_text = parse_reflection_output(accumulated_content)
    yield {"type": "reflection", "content": reflection_text}
    yield {"type": "synthesis", "response": synthesis_text, "model": CHAIRMAN_MODEL}
