"""
Tests for ReAct parsing and council member ReAct loop.

The ReAct pattern allows council members to reason, take actions (search),
observe results, and iterate before responding.
"""

from unittest.mock import AsyncMock, patch

import pytest

# =============================================================================
# Test Data
# =============================================================================

REACT_RESPONSE_DIRECT_SYNTHESIZE = """Thought: The models all agree that Python is best for beginners. No verification needed.

Action: synthesize()

Python is the best programming language for beginners due to its readable syntax and gentle learning curve."""

REACT_RESPONSE_WITH_SEARCH = """Thought: The models disagree on the current Bitcoin price. GPT says $67,000, Claude says $65,000. I should verify.

Action: search_web("bitcoin price today January 2026")"""

REACT_RESPONSE_INVALID_ACTION = """Thought: I need more information.

Action: invalid_tool("test")"""

REACT_RESPONSE_NO_ACTION = """Thought: Let me think about this more.

I'm not sure what to do next."""


# =============================================================================
# Parsing Tests
# =============================================================================


class TestParseReactOutput:
    """Tests for parsing Thought/Action from model output."""

    def test_parse_thought_and_action(self):
        """Should extract thought and action from well-formed output."""
        from llm_council.engine import parse_react_output

        thought, action, action_args = parse_react_output(REACT_RESPONSE_WITH_SEARCH)

        assert "models disagree" in thought.lower()
        assert action == "search_web"
        assert "bitcoin" in action_args.lower()

    def test_parse_synthesize_action(self):
        """Should recognize synthesize() as terminal action."""
        from llm_council.engine import parse_react_output

        thought, action, action_args = parse_react_output(REACT_RESPONSE_DIRECT_SYNTHESIZE)

        assert "models all agree" in thought.lower()
        assert action == "synthesize"
        assert action_args is None or action_args == ""

    def test_parse_invalid_action(self):
        """Should return None for unrecognized actions."""
        from llm_council.engine import parse_react_output

        thought, action, action_args = parse_react_output(REACT_RESPONSE_INVALID_ACTION)

        assert thought is not None
        assert action is None  # Invalid action not recognized

    def test_parse_missing_action(self):
        """Should handle output with thought but no action."""
        from llm_council.engine import parse_react_output

        thought, action, action_args = parse_react_output(REACT_RESPONSE_NO_ACTION)

        assert thought is not None
        assert action is None


# =============================================================================
# Context Builder Tests
# =============================================================================


class TestContextBuilders:
    """Tests for ReAct context builders (used by Reflection chairman)."""

    @pytest.mark.asyncio
    async def test_react_context_ranking(self):
        """Context builder works with Stage 1/2 results (ranking mode)."""
        from llm_council.engine import build_react_context_ranking

        stage1_results = [
            {"model": "gpt", "response": "Python is best"},
            {"model": "claude", "response": "JavaScript is best"},
        ]
        stage2_results = [
            {"model": "gpt", "ranking": "1. Response A\n2. Response B"},
        ]

        context = build_react_context_ranking("What language?", stage1_results, stage2_results)

        assert "Python is best" in context
        assert "JavaScript is best" in context

    @pytest.mark.asyncio
    async def test_react_context_debate(self):
        """Context builder works with debate rounds."""
        from llm_council.engine import build_react_context_debate

        rounds = [
            {
                "round_number": 1,
                "round_type": "initial",
                "responses": [{"model": "gpt", "response": "Initial answer"}],
            }
        ]

        context = build_react_context_debate("Question?", rounds, 1)

        assert "Initial answer" in context
        assert "ROUND 1" in context


# =============================================================================
# parse_react_output: respond() action
# =============================================================================


class TestParseRespondAction:
    """Tests for respond() as a terminal action."""

    def test_respond_recognized(self):
        """Should recognize respond() as a terminal action."""
        from llm_council.engine import parse_react_output

        text = """Thought: I know the answer from the question context.

Action: respond()

Python is the best language for beginners."""
        thought, action, action_args = parse_react_output(text)
        assert action == "respond"
        assert action_args is None
        assert "know the answer" in thought

    def test_respond_and_synthesize_both_terminal(self):
        """Both respond() and synthesize() should be recognized."""
        from llm_council.engine import parse_react_output

        text1 = "Thought: X\nAction: respond()"
        text2 = "Thought: X\nAction: synthesize()"
        _, action1, _ = parse_react_output(text1)
        _, action2, _ = parse_react_output(text2)
        assert action1 == "respond"
        assert action2 == "synthesize"


# =============================================================================
# Council ReAct Loop Tests
# =============================================================================


COUNCIL_REACT_DIRECT_RESPOND = """Thought: I can answer this directly from my training data.

Action: respond()

Python is the best programming language for beginners due to its readable syntax."""

COUNCIL_REACT_SEARCH_THEN_RESPOND = """Thought: I need to check the current Bitcoin price.

Action: search_web("bitcoin price today")"""

COUNCIL_REACT_AFTER_SEARCH = """Thought: Now I have the data I need.

Action: respond()

Bitcoin is currently trading at $67,234."""


class TestCouncilReactLoop:
    """Tests for council_react_loop."""

    @pytest.mark.asyncio
    async def test_direct_respond(self):
        """Model responds directly without searching."""
        from llm_council.engine.react import council_react_loop

        async def mock_generator():
            yield {"type": "done", "content": COUNCIL_REACT_DIRECT_RESPOND}

        with patch(
            "llm_council.engine.react.query_model_streaming",
            return_value=mock_generator(),
        ):
            events = []
            async for event in council_react_loop("test/model", "test prompt"):
                events.append(event)

        event_types = [e["type"] for e in events]
        assert "thought" in event_types
        assert "done" in event_types

        done = next(e for e in events if e["type"] == "done")
        assert "Python is the best" in done["content"]
        assert done["tool_calls_made"] == []

    @pytest.mark.asyncio
    async def test_search_then_respond(self):
        """Model searches, then responds."""
        from llm_council.engine.react import council_react_loop

        call_count = 0

        async def mock_generator():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                yield {"type": "done", "content": COUNCIL_REACT_SEARCH_THEN_RESPOND}
            else:
                yield {"type": "done", "content": COUNCIL_REACT_AFTER_SEARCH}

        with patch(
            "llm_council.engine.react.query_model_streaming",
            side_effect=lambda *args, **kwargs: mock_generator(),
        ):
            with patch(
                "llm_council.engine.react.search_web", new_callable=AsyncMock
            ) as mock_search:
                mock_search.return_value = {
                    "answer": "Bitcoin is at $67,234",
                    "results": [
                        {"title": "Price", "content": "$67,234", "url": "https://example.com"}
                    ],
                }

                events = []
                async for event in council_react_loop("test/model", "test prompt"):
                    events.append(event)

        event_types = [e["type"] for e in events]
        assert "thought" in event_types
        assert "action" in event_types
        assert "observation" in event_types
        assert "done" in event_types

        done = next(e for e in events if e["type"] == "done")
        assert "$67,234" in done["content"]
        assert len(done["tool_calls_made"]) == 1
        assert done["tool_calls_made"][0]["tool"] == "search_web"

    @pytest.mark.asyncio
    async def test_max_iterations(self):
        """Should stop after max_iterations and yield done with accumulated content."""
        from llm_council.engine.react import council_react_loop

        async def mock_generator():
            yield {"type": "done", "content": COUNCIL_REACT_SEARCH_THEN_RESPOND}

        with patch(
            "llm_council.engine.react.query_model_streaming",
            side_effect=lambda *args, **kwargs: mock_generator(),
        ):
            with patch(
                "llm_council.engine.react.search_web", new_callable=AsyncMock
            ) as mock_search:
                mock_search.return_value = {
                    "answer": "Test",
                    "results": [{"title": "T", "content": "C", "url": "U"}],
                }

                events = []
                async for event in council_react_loop(
                    "test/model", "test prompt", max_iterations=2
                ):
                    events.append(event)

        # Should have a done event
        done_events = [e for e in events if e["type"] == "done"]
        assert len(done_events) == 1

    @pytest.mark.asyncio
    async def test_error_handling(self):
        """Should yield done with error on streaming error."""
        from llm_council.engine.react import council_react_loop

        async def mock_generator():
            yield {"type": "error", "error": "Connection failed"}

        with patch(
            "llm_council.engine.react.query_model_streaming",
            return_value=mock_generator(),
        ):
            events = []
            async for event in council_react_loop("test/model", "test prompt"):
                events.append(event)

        done = next(e for e in events if e["type"] == "done")
        assert "Error" in done["content"]
