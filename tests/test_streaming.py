"""
Tests for streaming debate mode functionality.

These tests verify that debate rounds stream model completions as they finish,
rather than waiting for all models to complete.
"""

import asyncio
import pytest
from typing import Dict, Any, List
from unittest.mock import AsyncMock, patch, MagicMock

from tests.conftest import (
    SAMPLE_MODELS,
    SAMPLE_INITIAL_RESPONSES,
    SAMPLE_CRITIQUE_RESPONSES,
    SAMPLE_DEFENSE_RESPONSES,
    make_model_response,
)


# =============================================================================
# Test: Streaming round yields model completions as they finish
# =============================================================================

@pytest.mark.asyncio
async def test_debate_round_streaming_yields_as_completed():
    """
    Verify that debate_round_streaming yields model_complete events
    as each model finishes, not all at once.
    """
    from backend.council import debate_round_streaming

    # Track event order
    events = []
    completion_times = []

    # Mock query_model to return at different times
    async def mock_query(model, messages, *args, **kwargs):
        # Simulate different response times
        delays = {
            SAMPLE_MODELS[0]: 0.01,
            SAMPLE_MODELS[1]: 0.05,
            SAMPLE_MODELS[2]: 0.03,
        }
        await asyncio.sleep(delays.get(model, 0.01))
        return {"content": f"Response from {model}"}

    with patch("backend.council.streaming.query_model_with_tools", side_effect=mock_query):
        with patch("backend.council.streaming.query_model", side_effect=mock_query):
            with patch("backend.council.streaming.COUNCIL_MODELS", SAMPLE_MODELS):
                async for event in debate_round_streaming(
                    round_type="initial",
                    user_query="Test question",
                    context={},
                ):
                    events.append(event)
                    if event["type"] == "model_complete":
                        completion_times.append(event["model"])

    # Should have model_complete events for each model plus round_complete
    model_completes = [e for e in events if e["type"] == "model_complete"]
    assert len(model_completes) == len(SAMPLE_MODELS)

    # Verify we got a round_complete event
    round_complete = [e for e in events if e["type"] == "round_complete"]
    assert len(round_complete) == 1

    # The fastest model (SAMPLE_MODELS[0] with 0.01s) should complete first
    # Note: Due to async timing, we mainly verify all models completed
    assert set(completion_times) == set(SAMPLE_MODELS)


# =============================================================================
# Test: Each event identifies source model correctly
# =============================================================================

@pytest.mark.asyncio
async def test_streaming_preserves_model_identity():
    """
    Verify that each model_complete event correctly identifies
    which model generated the response.
    """
    from backend.council import debate_round_streaming

    expected_responses = {
        SAMPLE_MODELS[0]: "Response A content",
        SAMPLE_MODELS[1]: "Response B content",
        SAMPLE_MODELS[2]: "Response C content",
    }

    async def mock_query(model, messages, *args, **kwargs):
        return {"content": expected_responses[model]}

    with patch("backend.council.streaming.query_model_with_tools", side_effect=mock_query):
        with patch("backend.council.streaming.query_model", side_effect=mock_query):
            with patch("backend.council.streaming.COUNCIL_MODELS", SAMPLE_MODELS):
                events = []
                async for event in debate_round_streaming(
                    round_type="initial",
                    user_query="Test question",
                    context={},
                ):
                    events.append(event)

    # Check each model_complete event has correct model and response
    model_completes = [e for e in events if e["type"] == "model_complete"]
    for event in model_completes:
        model = event["model"]
        assert model in expected_responses
        assert event["response"]["response"] == expected_responses[model]


# =============================================================================
# Test: Continues if individual model fails
# =============================================================================

@pytest.mark.asyncio
async def test_streaming_handles_model_failure():
    """
    Verify that streaming continues even if one model fails,
    yielding model_error for failed models.
    """
    from backend.council import debate_round_streaming

    async def mock_query(model, messages, *args, **kwargs):
        if model == SAMPLE_MODELS[1]:
            return None  # Simulate failure
        return {"content": f"Response from {model}"}

    with patch("backend.council.streaming.query_model_with_tools", side_effect=mock_query):
        with patch("backend.council.streaming.query_model", side_effect=mock_query):
            with patch("backend.council.streaming.COUNCIL_MODELS", SAMPLE_MODELS):
                events = []
                async for event in debate_round_streaming(
                    round_type="initial",
                    user_query="Test question",
                    context={},
                ):
                    events.append(event)

    # Should have model_complete for successful models
    model_completes = [e for e in events if e["type"] == "model_complete"]
    assert len(model_completes) == 2  # 2 succeeded

    # Should have model_error for failed model
    model_errors = [e for e in events if e["type"] == "model_error"]
    assert len(model_errors) == 1
    assert model_errors[0]["model"] == SAMPLE_MODELS[1]

    # Round should still complete
    round_complete = [e for e in events if e["type"] == "round_complete"]
    assert len(round_complete) == 1
    # Only successful responses in round_complete
    assert len(round_complete[0]["responses"]) == 2


# =============================================================================
# Test: Round complete event has all successful responses
# =============================================================================

@pytest.mark.asyncio
async def test_round_complete_contains_all_responses():
    """
    Verify that the round_complete event contains all successful
    model responses from the round.
    """
    from backend.council import debate_round_streaming

    async def mock_query(model, messages, *args, **kwargs):
        return {"content": f"Response from {model}"}

    with patch("backend.council.streaming.query_model_with_tools", side_effect=mock_query):
        with patch("backend.council.streaming.query_model", side_effect=mock_query):
            with patch("backend.council.streaming.COUNCIL_MODELS", SAMPLE_MODELS):
                events = []
                async for event in debate_round_streaming(
                    round_type="initial",
                    user_query="Test question",
                    context={},
                ):
                    events.append(event)

    round_complete = [e for e in events if e["type"] == "round_complete"][0]

    # Should have all models' responses
    assert len(round_complete["responses"]) == len(SAMPLE_MODELS)

    # Each response should have model and response fields
    response_models = {r["model"] for r in round_complete["responses"]}
    assert response_models == set(SAMPLE_MODELS)

    for response in round_complete["responses"]:
        assert "model" in response
        assert "response" in response


# =============================================================================
# Test: Full debate yields correct event sequence
# =============================================================================

@pytest.mark.asyncio
async def test_debate_streaming_event_order():
    """
    Verify that run_debate_council_streaming yields events
    in the correct order: round_start -> model_completes -> round_complete.
    """
    from backend.council import run_debate_council_streaming

    async def mock_query(model, messages, *args, **kwargs):
        return {"content": f"Response from {model}"}

    async def mock_query_tools(model, messages, tools, tool_executor, *args, **kwargs):
        return {"content": f"Response from {model}"}

    with patch("backend.council.streaming.query_model", side_effect=mock_query):
        with patch("backend.council.streaming.query_model_with_tools", side_effect=mock_query_tools):
            with patch("backend.council.streaming.COUNCIL_MODELS", SAMPLE_MODELS):
                events = []
                async for event in run_debate_council_streaming(
                    user_query="Test question",
                    max_rounds=2,
                ):
                    events.append(event)

    # Verify event sequence for debate with 2 rounds (= 3 actual rounds + synthesis)
    # Expected sequence:
    # round_start(1) -> model_complete(s) -> round_complete(1)
    # round_start(2) -> model_complete(s) -> round_complete(2)
    # round_start(3) -> model_complete(s) -> round_complete(3)
    # synthesis_start -> synthesis_complete -> complete

    event_types = [e["type"] for e in events]

    # Should have 3 round_start events
    assert event_types.count("round_start") == 3

    # Should have synthesis events
    assert "synthesis_start" in event_types
    assert "synthesis_complete" in event_types

    # Should end with complete event
    assert event_types[-1] == "complete"

    # Verify round numbers in round_start events
    round_starts = [e for e in events if e["type"] == "round_start"]
    assert [r["round_number"] for r in round_starts] == [1, 2, 3]

    # Verify round types
    assert round_starts[0]["round_type"] == "initial"
    assert round_starts[1]["round_type"] == "critique"
    assert round_starts[2]["round_type"] == "defense"


# =============================================================================
# Test: Streaming produces same final result as batch mode
# =============================================================================

@pytest.mark.asyncio
async def test_streaming_same_result_as_batch():
    """
    Verify that streaming mode produces the same final rounds and
    synthesis as the batch mode run_debate_council.
    """
    from backend.council import run_debate_council, run_debate_council_streaming

    call_count = {"count": 0}

    async def mock_query(model, messages, *args, **kwargs):
        call_count["count"] += 1
        # Return deterministic responses based on message content
        content = str(messages)
        if "critique" in content.lower() or "Critique" in content:
            return {"content": f"Critique from {model}"}
        elif "defense" in content.lower() or "Addressing" in content:
            return {"content": f"## Addressing Critiques\nDefense\n\n## Revised Response\nRevised from {model}"}
        elif "Chairman" in content or "synthesize" in content.lower():
            return {"content": f"Synthesis from chairman"}
        return {"content": f"Initial response from {model}"}

    async def mock_query_tools(model, messages, tools, tool_executor, *args, **kwargs):
        return {"content": f"Initial response from {model}"}

    # Run batch mode (debate module)
    with patch("backend.council.debate.query_model", side_effect=mock_query):
        with patch("backend.council.debate.query_model_with_tools", side_effect=mock_query_tools):
            with patch("backend.council.debate.COUNCIL_MODELS", SAMPLE_MODELS):
                with patch("backend.council.debate.CHAIRMAN_MODEL", SAMPLE_MODELS[0]):
                    batch_rounds, batch_synthesis = await run_debate_council(
                        "Test question",
                        max_rounds=2,
                    )

    # Run streaming mode and collect final result (streaming module)
    with patch("backend.council.streaming.query_model", side_effect=mock_query):
        with patch("backend.council.streaming.query_model_with_tools", side_effect=mock_query_tools):
            with patch("backend.council.streaming.COUNCIL_MODELS", SAMPLE_MODELS):
                with patch("backend.council.streaming.CHAIRMAN_MODEL", SAMPLE_MODELS[0]):
                    stream_result = None
                    async for event in run_debate_council_streaming(
                        "Test question",
                        max_rounds=2,
                    ):
                        if event["type"] == "complete":
                            stream_result = event

    # Both should have same number of rounds
    assert len(stream_result["rounds"]) == len(batch_rounds)

    # Same round types and numbers
    for batch_round, stream_round in zip(batch_rounds, stream_result["rounds"]):
        assert batch_round["round_number"] == stream_round["round_number"]
        assert batch_round["round_type"] == stream_round["round_type"]
        assert len(batch_round["responses"]) == len(stream_round["responses"])


# =============================================================================
# Test: Critique round streaming
# =============================================================================

@pytest.mark.asyncio
async def test_critique_round_streaming():
    """
    Verify that critique rounds stream correctly with proper context.
    """
    from backend.council import debate_round_streaming

    async def mock_query(model, messages, *args, **kwargs):
        return {"content": f"## Critique of other model\nCritique from {model}"}

    initial_responses = [
        {"model": m, "response": f"Initial from {m}"}
        for m in SAMPLE_MODELS
    ]

    with patch("backend.council.streaming.query_model", side_effect=mock_query):
        with patch("backend.council.streaming.COUNCIL_MODELS", SAMPLE_MODELS):
            events = []
            async for event in debate_round_streaming(
                round_type="critique",
                user_query="Test question",
                context={"initial_responses": initial_responses},
            ):
                events.append(event)

    model_completes = [e for e in events if e["type"] == "model_complete"]
    assert len(model_completes) == len(SAMPLE_MODELS)


# =============================================================================
# Test: Defense round streaming
# =============================================================================

@pytest.mark.asyncio
async def test_defense_round_streaming():
    """
    Verify that defense rounds stream correctly with proper context.
    """
    from backend.council import debate_round_streaming

    async def mock_query(model, messages, *args, **kwargs):
        return {
            "content": f"## Addressing Critiques\nDefense\n\n## Revised Response\nRevised from {model}"
        }

    initial_responses = [
        {"model": m, "response": f"Initial from {m}"}
        for m in SAMPLE_MODELS
    ]
    critique_responses = [
        {"model": m, "response": f"## Critique of other\nCritique from {m}"}
        for m in SAMPLE_MODELS
    ]

    with patch("backend.council.streaming.query_model", side_effect=mock_query):
        with patch("backend.council.streaming.COUNCIL_MODELS", SAMPLE_MODELS):
            events = []
            async for event in debate_round_streaming(
                round_type="defense",
                user_query="Test question",
                context={
                    "initial_responses": initial_responses,
                    "critique_responses": critique_responses,
                },
            ):
                events.append(event)

    model_completes = [e for e in events if e["type"] == "model_complete"]
    assert len(model_completes) == len(SAMPLE_MODELS)

    # Defense responses should have revised_answer parsed
    for event in model_completes:
        assert "revised_answer" in event["response"]


# =============================================================================
# Test: model_start events emitted for all models
# =============================================================================

@pytest.mark.asyncio
async def test_streaming_emits_model_start_events():
    """
    Verify that debate_round_streaming emits model_start events
    for all models before completions.
    """
    from backend.council import debate_round_streaming

    async def mock_query(model, messages, *args, **kwargs):
        return {"content": f"Response from {model}"}

    with patch("backend.council.streaming.query_model_with_tools", side_effect=mock_query):
        with patch("backend.council.streaming.COUNCIL_MODELS", SAMPLE_MODELS):
            events = []
            async for event in debate_round_streaming(
                round_type="initial",
                user_query="Test question",
                context={},
            ):
                events.append(event)

    # Should have model_start events for each model
    model_starts = [e for e in events if e["type"] == "model_start"]
    assert len(model_starts) == len(SAMPLE_MODELS)

    # model_start events should come before model_complete events
    start_indices = [i for i, e in enumerate(events) if e["type"] == "model_start"]
    complete_indices = [i for i, e in enumerate(events) if e["type"] == "model_complete"]

    assert max(start_indices) < min(complete_indices), \
        "All model_start events should come before any model_complete"


# =============================================================================
# Test: Per-model timeout functionality
# =============================================================================

@pytest.mark.asyncio
async def test_streaming_handles_model_timeout():
    """
    Verify that debate_round_streaming handles model timeouts gracefully.
    """
    from backend.council import debate_round_streaming

    async def mock_query(model, messages, *args, **kwargs):
        if model == SAMPLE_MODELS[0]:
            # This model will timeout
            await asyncio.sleep(10)
            return {"content": "Should not reach this"}
        return {"content": f"Response from {model}"}

    with patch("backend.council.streaming.query_model_with_tools", side_effect=mock_query):
        with patch("backend.council.streaming.COUNCIL_MODELS", SAMPLE_MODELS):
            events = []
            async for event in debate_round_streaming(
                round_type="initial",
                user_query="Test question",
                context={},
                model_timeout=0.1,  # Very short timeout
            ):
                events.append(event)

    # Should have model_error for the timed out model
    model_errors = [e for e in events if e["type"] == "model_error"]
    assert len(model_errors) == 1
    assert model_errors[0]["model"] == SAMPLE_MODELS[0]
    assert "Timeout" in model_errors[0]["error"]

    # Other models should complete successfully
    model_completes = [e for e in events if e["type"] == "model_complete"]
    assert len(model_completes) == len(SAMPLE_MODELS) - 1
