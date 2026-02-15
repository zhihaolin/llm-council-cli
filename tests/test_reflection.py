"""
Tests for Chairman Reflection synthesis.

Reflection replaces the ReAct chairman pattern — the chairman deeply
analyses council responses before producing a final synthesis (no tools).
"""

from unittest.mock import patch

import pytest

from llm_council.engine.parsers import parse_reflection_output

# =============================================================================
# Test Data
# =============================================================================

REFLECTION_FULL = """The models mostly agree that Python is best for beginners.
GPT and Claude emphasise readable syntax, while Gemini focuses on browser availability.

The disagreement on JavaScript vs Python is mostly about use-case:
JavaScript wins for web-first learners, Python for general CS foundations.

## Synthesis
Python is the best programming language for beginners due to its readable
syntax and gentle learning curve. JavaScript is a strong alternative for
those specifically interested in web development."""

REFLECTION_NO_HEADER = """Python is the best programming language for beginners due to its readable
syntax and gentle learning curve."""

REFLECTION_CASE_INSENSITIVE = """Some analysis here.

## synthesis
The final answer after a lowercase header."""


# =============================================================================
# Parsing Tests
# =============================================================================


class TestParseReflectionOutput:
    """Tests for parse_reflection_output."""

    def test_splits_at_synthesis_header(self):
        """Should split at ## Synthesis header."""
        reflection, synthesis = parse_reflection_output(REFLECTION_FULL)

        assert "models mostly agree" in reflection
        assert "Python is the best programming language" in synthesis
        assert "## Synthesis" not in synthesis

    def test_falls_back_when_no_header(self):
        """Should return ('', full_text) when header is missing."""
        reflection, synthesis = parse_reflection_output(REFLECTION_NO_HEADER)

        assert reflection == ""
        assert "Python is the best" in synthesis

    def test_case_insensitive(self):
        """Should match ## synthesis (lowercase)."""
        reflection, synthesis = parse_reflection_output(REFLECTION_CASE_INSENSITIVE)

        assert "analysis here" in reflection
        assert "final answer after a lowercase header" in synthesis


# =============================================================================
# Reflection Loop Tests
# =============================================================================


class TestReflectionLoop:
    """Tests for synthesize_with_reflection."""

    @pytest.mark.asyncio
    async def test_yields_tokens_then_reflection_then_synthesis(self):
        """Should yield token events, then reflection, then synthesis."""
        from llm_council.engine.reflection import synthesize_with_reflection

        async def mock_generator():
            yield {"type": "token", "content": REFLECTION_FULL}
            yield {"type": "done", "content": REFLECTION_FULL}

        with patch(
            "llm_council.engine.reflection.query_model_streaming",
            return_value=mock_generator(),
        ):
            events = []
            async for event in synthesize_with_reflection("test query", "test context"):
                events.append(event)

        event_types = [e["type"] for e in events]
        assert "token" in event_types
        assert "reflection" in event_types
        assert "synthesis" in event_types

        # Reflection should contain the analysis
        reflection_event = next(e for e in events if e["type"] == "reflection")
        assert "models mostly agree" in reflection_event["content"]

        # Synthesis should contain the final answer
        synthesis_event = next(e for e in events if e["type"] == "synthesis")
        assert "Python is the best" in synthesis_event["response"]
        assert "model" in synthesis_event

    @pytest.mark.asyncio
    async def test_error_yields_synthesis_with_error(self):
        """On streaming error, should yield synthesis with error message."""
        from llm_council.engine.reflection import synthesize_with_reflection

        async def mock_generator():
            yield {"type": "error", "error": "Connection failed"}

        with patch(
            "llm_council.engine.reflection.query_model_streaming",
            return_value=mock_generator(),
        ):
            events = []
            async for event in synthesize_with_reflection("test query", "test context"):
                events.append(event)

        assert len(events) == 1
        assert events[0]["type"] == "synthesis"
        assert "Error" in events[0]["response"]

    @pytest.mark.asyncio
    async def test_no_header_still_yields_synthesis(self):
        """When model omits ## Synthesis header, full text becomes synthesis."""
        from llm_council.engine.reflection import synthesize_with_reflection

        async def mock_generator():
            yield {"type": "done", "content": REFLECTION_NO_HEADER}

        with patch(
            "llm_council.engine.reflection.query_model_streaming",
            return_value=mock_generator(),
        ):
            events = []
            async for event in synthesize_with_reflection("test query", "test context"):
                events.append(event)

        synthesis_event = next(e for e in events if e["type"] == "synthesis")
        assert "Python is the best" in synthesis_event["response"]
