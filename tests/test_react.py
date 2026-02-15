"""
Tests for ReAct Chairman (v1.6).

The ReAct pattern allows the chairman to reason, take actions (search),
observe results, and iterate before synthesizing.
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

REACT_RESPONSE_AFTER_SEARCH = """Thought: The search confirms Bitcoin is at $67,234. GPT was closest. I can now synthesize.

Action: synthesize()

Based on verification, Bitcoin is currently trading at $67,234 as of January 2026."""

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
# ReAct Loop Tests
# =============================================================================


class TestReactLoop:
    """Tests for the ReAct synthesis loop."""

    @pytest.mark.asyncio
    async def test_direct_synthesize_yields_correct_events(self):
        """When chairman synthesizes immediately, should yield thought then synthesis."""
        from llm_council.engine import synthesize_with_react

        with patch("llm_council.engine.react.query_model_streaming") as mock_stream:
            # Mock streaming to yield the full response
            async def mock_generator():
                yield {"type": "token", "content": REACT_RESPONSE_DIRECT_SYNTHESIZE}
                yield {"type": "done", "content": REACT_RESPONSE_DIRECT_SYNTHESIZE}

            mock_stream.return_value = mock_generator()

            events = []
            async for event in synthesize_with_react("test query", "test context"):
                events.append(event)

        # Should have: thought, action (synthesize), synthesis
        event_types = [e["type"] for e in events]
        assert "thought" in event_types
        assert "synthesis" in event_types

    @pytest.mark.asyncio
    async def test_search_then_synthesize_yields_observation(self):
        """When chairman searches, should yield thought, action, observation, then synthesis."""
        from llm_council.engine import synthesize_with_react

        call_count = 0

        async def mock_generator():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First call: chairman wants to search
                yield {"type": "done", "content": REACT_RESPONSE_WITH_SEARCH}
            else:
                # Second call: after search, chairman synthesizes
                yield {"type": "done", "content": REACT_RESPONSE_AFTER_SEARCH}

        with patch(
            "llm_council.engine.react.query_model_streaming",
            side_effect=lambda *args, **kwargs: mock_generator(),
        ):
            with patch(
                "llm_council.engine.react.search_web", new_callable=AsyncMock
            ) as mock_search:
                # Return proper Tavily response format
                mock_search.return_value = {
                    "answer": "Bitcoin is at $67,234",
                    "results": [
                        {
                            "title": "Bitcoin Price",
                            "content": "Bitcoin is at $67,234",
                            "url": "https://example.com",
                        }
                    ],
                }

                events = []
                async for event in synthesize_with_react("test query", "test context"):
                    events.append(event)

        event_types = [e["type"] for e in events]
        assert "thought" in event_types
        assert "action" in event_types
        assert "observation" in event_types
        assert "synthesis" in event_types

    @pytest.mark.asyncio
    async def test_max_iterations_prevents_infinite_loop(self):
        """Should stop after max_iterations even without synthesize action."""
        from llm_council.engine import synthesize_with_react

        # Always return a search action, never synthesize
        async def mock_generator():
            yield {"type": "done", "content": REACT_RESPONSE_WITH_SEARCH}

        with patch(
            "llm_council.engine.react.query_model_streaming",
            side_effect=lambda *args, **kwargs: mock_generator(),
        ):
            with patch(
                "llm_council.engine.react.search_web", new_callable=AsyncMock
            ) as mock_search:
                # Return proper Tavily response format
                mock_search.return_value = {
                    "answer": "Test result",
                    "results": [
                        {"title": "Test", "content": "Test result", "url": "https://example.com"}
                    ],
                }

                events = []
                async for event in synthesize_with_react(
                    "test query", "test context", max_iterations=2
                ):
                    events.append(event)

        # Should have forced synthesis after max iterations
        action_events = [e for e in events if e["type"] == "action"]
        assert len(action_events) <= 2  # Max 2 iterations

    @pytest.mark.asyncio
    async def test_invalid_action_forces_synthesize(self):
        """Invalid action should trigger forced synthesis."""
        from llm_council.engine import synthesize_with_react

        call_count = 0

        async def mock_generator():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                yield {"type": "done", "content": REACT_RESPONSE_INVALID_ACTION}
            else:
                yield {"type": "done", "content": REACT_RESPONSE_DIRECT_SYNTHESIZE}

        with patch(
            "llm_council.engine.react.query_model_streaming",
            side_effect=lambda *args, **kwargs: mock_generator(),
        ):
            events = []
            async for event in synthesize_with_react("test query", "test context"):
                events.append(event)

        # Should eventually synthesize
        assert any(e["type"] == "synthesis" for e in events)


# =============================================================================
# Integration Tests
# =============================================================================


class TestReactIntegration:
    """Integration tests for ReAct with full council flow."""

    @pytest.mark.asyncio
    async def test_react_with_ranking_mode(self):
        """ReAct should work with Stage 1/2 results (ranking mode)."""
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
    async def test_react_with_debate_mode(self):
        """ReAct should work with debate rounds."""
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
# Streaming Tests
# =============================================================================


class TestReactStreaming:
    """Tests for ReAct trace streaming."""

    @pytest.mark.asyncio
    async def test_thought_streams_token_by_token(self):
        """Thought content should stream as tokens arrive."""
        from llm_council.engine import synthesize_with_react

        tokens = ["Thought: ", "The ", "models ", "agree.\n\n", "Action: ", "synthesize()"]

        async def mock_generator():
            for token in tokens:
                yield {"type": "token", "content": token}
            yield {"type": "done", "content": "".join(tokens)}

        with patch("llm_council.engine.react.query_model_streaming", return_value=mock_generator()):
            events = []
            async for event in synthesize_with_react("test", "context"):
                events.append(event)

        # Should have token events
        token_events = [e for e in events if e["type"] == "token"]
        assert len(token_events) > 0

    @pytest.mark.asyncio
    async def test_observation_not_streamed(self):
        """Observation (search results) should appear as complete block, not streamed."""
        from llm_council.engine import synthesize_with_react

        call_count = 0

        async def mock_generator():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                yield {"type": "done", "content": REACT_RESPONSE_WITH_SEARCH}
            else:
                yield {"type": "done", "content": REACT_RESPONSE_AFTER_SEARCH}

        with patch(
            "llm_council.engine.react.query_model_streaming",
            side_effect=lambda *args, **kwargs: mock_generator(),
        ):
            with patch(
                "llm_council.engine.react.search_web", new_callable=AsyncMock
            ) as mock_search:
                # Return proper Tavily response format
                mock_search.return_value = {
                    "answer": "Bitcoin is at $67,234",
                    "results": [
                        {"title": "Price", "content": "$67,234", "url": "https://example.com"}
                    ],
                }

                events = []
                async for event in synthesize_with_react("test", "context"):
                    events.append(event)

        # Observation should be a single event, not multiple tokens
        obs_events = [e for e in events if e["type"] == "observation"]
        assert len(obs_events) == 1
        assert "$67,234" in obs_events[0]["content"]
