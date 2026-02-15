"""
Tests for streaming debate mode functionality.

These tests verify that debate rounds stream model completions as they finish,
rather than waiting for all models to complete.
"""

import asyncio
from unittest.mock import patch

import pytest

from tests.conftest import (
    SAMPLE_MODELS,
)

# Mock targets — all functions now live in llm_council.engine.debate
DEBATE_QUERY_MODEL = "llm_council.engine.debate.query_model"
DEBATE_QUERY_MODEL_WITH_TOOLS = "llm_council.engine.debate.query_model_with_tools"
DEBATE_COUNCIL_MODELS = "llm_council.engine.debate.COUNCIL_MODELS"

# =============================================================================
# Test: Streaming round yields model completions as they finish
# =============================================================================


@pytest.mark.asyncio
async def test_debate_round_parallel_yields_as_completed():
    """
    Verify that debate_round_parallel yields model_complete events
    as each model finishes, not all at once.
    """
    from llm_council.engine import debate_round_parallel

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

    with patch(DEBATE_QUERY_MODEL_WITH_TOOLS, side_effect=mock_query):
        with patch(DEBATE_COUNCIL_MODELS, SAMPLE_MODELS):
            async for event in debate_round_parallel(
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
    from llm_council.engine import debate_round_parallel

    expected_responses = {
        SAMPLE_MODELS[0]: "Response A content",
        SAMPLE_MODELS[1]: "Response B content",
        SAMPLE_MODELS[2]: "Response C content",
    }

    async def mock_query(model, messages, *args, **kwargs):
        return {"content": expected_responses[model]}

    with patch(DEBATE_QUERY_MODEL_WITH_TOOLS, side_effect=mock_query):
        with patch(DEBATE_COUNCIL_MODELS, SAMPLE_MODELS):
            events = []
            async for event in debate_round_parallel(
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
    from llm_council.engine import debate_round_parallel

    async def mock_query(model, messages, *args, **kwargs):
        if model == SAMPLE_MODELS[1]:
            return None  # Simulate failure
        return {"content": f"Response from {model}"}

    with patch(DEBATE_QUERY_MODEL_WITH_TOOLS, side_effect=mock_query):
        with patch(DEBATE_COUNCIL_MODELS, SAMPLE_MODELS):
            events = []
            async for event in debate_round_parallel(
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
    from llm_council.engine import debate_round_parallel

    async def mock_query(model, messages, *args, **kwargs):
        return {"content": f"Response from {model}"}

    with patch(DEBATE_QUERY_MODEL_WITH_TOOLS, side_effect=mock_query):
        with patch(DEBATE_COUNCIL_MODELS, SAMPLE_MODELS):
            events = []
            async for event in debate_round_parallel(
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
    Verify that run_debate with debate_round_parallel yields events
    in the correct order: round_start -> model events -> round_complete -> debate_complete.
    """
    from llm_council.engine.debate import debate_round_parallel, run_debate

    async def mock_query(model, messages, *args, **kwargs):
        return {"content": f"Response from {model}"}

    async def mock_query_tools(model, messages, tools, tool_executor, *args, **kwargs):
        return {"content": f"Response from {model}"}

    with patch(DEBATE_QUERY_MODEL, side_effect=mock_query):
        with patch(DEBATE_QUERY_MODEL_WITH_TOOLS, side_effect=mock_query_tools):
            with patch(DEBATE_COUNCIL_MODELS, SAMPLE_MODELS):
                events = []
                async for event in run_debate(
                    user_query="Test question",
                    execute_round=debate_round_parallel,
                    cycles=1,
                ):
                    events.append(event)

    # Expected sequence (no synthesis — that's now the CLI's responsibility):
    # round_start(1) -> model_start(s) -> model_complete(s) -> round_complete(1)
    # round_start(2) -> model_complete(s) -> round_complete(2)
    # round_start(3) -> model_complete(s) -> round_complete(3)
    # debate_complete

    event_types = [e["type"] for e in events]

    # Should have 3 round_start events
    assert event_types.count("round_start") == 3

    # No synthesis events (synthesis is now a CLI concern)
    assert "synthesis_start" not in event_types
    assert "synthesis_complete" not in event_types

    # Should end with debate_complete event
    assert event_types[-1] == "debate_complete"

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
async def test_run_debate_produces_correct_rounds():
    """
    Verify that run_debate with debate_round_parallel produces correct rounds
    with expected round types and response counts.
    """
    from llm_council.engine.debate import debate_round_parallel, run_debate

    async def mock_query(model, messages, *args, **kwargs):
        # Return deterministic responses based on message content
        content = str(messages)
        if "critique" in content.lower() or "Critique" in content:
            return {"content": f"Critique from {model}"}
        elif "defense" in content.lower() or "Addressing" in content:
            return {
                "content": f"## Addressing Critiques\nDefense\n\n## Revised Response\nRevised from {model}"
            }
        return {"content": f"Initial response from {model}"}

    async def mock_query_tools(model, messages, tools, tool_executor, *args, **kwargs):
        content = str(messages)
        if "defense" in content.lower() or "Addressing" in content:
            return {
                "content": f"## Addressing Critiques\nDefense\n\n## Revised Response\nRevised from {model}"
            }
        return {"content": f"Initial response from {model}"}

    with patch(DEBATE_QUERY_MODEL, side_effect=mock_query):
        with patch(DEBATE_QUERY_MODEL_WITH_TOOLS, side_effect=mock_query_tools):
            with patch(DEBATE_COUNCIL_MODELS, SAMPLE_MODELS):
                rounds = None
                async for event in run_debate(
                    "Test question",
                    execute_round=debate_round_parallel,
                    cycles=1,
                ):
                    if event["type"] == "debate_complete":
                        rounds = event["rounds"]

    # Should have 3 rounds
    assert len(rounds) == 3

    # Verify round types and numbers
    assert rounds[0]["round_number"] == 1
    assert rounds[0]["round_type"] == "initial"
    assert rounds[1]["round_number"] == 2
    assert rounds[1]["round_type"] == "critique"
    assert rounds[2]["round_number"] == 3
    assert rounds[2]["round_type"] == "defense"

    # Each round should have responses from all models
    for rnd in rounds:
        assert len(rnd["responses"]) == len(SAMPLE_MODELS)


# =============================================================================
# Test: Critique round streaming
# =============================================================================


@pytest.mark.asyncio
async def test_critique_round_streaming():
    """
    Verify that critique rounds stream correctly with proper context.
    """
    from llm_council.engine import debate_round_parallel

    async def mock_query(model, messages, *args, **kwargs):
        return {"content": f"## Critique of other model\nCritique from {model}"}

    initial_responses = [{"model": m, "response": f"Initial from {m}"} for m in SAMPLE_MODELS]

    with patch(DEBATE_QUERY_MODEL, side_effect=mock_query):
        with patch(DEBATE_COUNCIL_MODELS, SAMPLE_MODELS):
            events = []
            async for event in debate_round_parallel(
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
    from llm_council.engine import debate_round_parallel

    async def mock_query(model, messages, *args, **kwargs):
        return {
            "content": f"## Addressing Critiques\nDefense\n\n## Revised Response\nRevised from {model}"
        }

    initial_responses = [{"model": m, "response": f"Initial from {m}"} for m in SAMPLE_MODELS]
    critique_responses = [
        {"model": m, "response": f"## Critique of other\nCritique from {m}"} for m in SAMPLE_MODELS
    ]

    with patch(DEBATE_QUERY_MODEL_WITH_TOOLS, side_effect=mock_query):
        with patch(DEBATE_COUNCIL_MODELS, SAMPLE_MODELS):
            events = []
            async for event in debate_round_parallel(
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
    Verify that debate_round_parallel emits model_start events
    for all models before completions.
    """
    from llm_council.engine import debate_round_parallel

    async def mock_query(model, messages, *args, **kwargs):
        return {"content": f"Response from {model}"}

    with patch(DEBATE_QUERY_MODEL_WITH_TOOLS, side_effect=mock_query):
        with patch(DEBATE_COUNCIL_MODELS, SAMPLE_MODELS):
            events = []
            async for event in debate_round_parallel(
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

    assert max(start_indices) < min(complete_indices), (
        "All model_start events should come before any model_complete"
    )


# =============================================================================
# Test: Per-model timeout functionality
# =============================================================================


@pytest.mark.asyncio
async def test_streaming_handles_model_timeout():
    """
    Verify that debate_round_parallel handles model timeouts gracefully.
    """
    from llm_council.engine import debate_round_parallel

    async def mock_query(model, messages, *args, **kwargs):
        if model == SAMPLE_MODELS[0]:
            # This model will timeout
            await asyncio.sleep(10)
            return {"content": "Should not reach this"}
        return {"content": f"Response from {model}"}

    with patch(DEBATE_QUERY_MODEL_WITH_TOOLS, side_effect=mock_query):
        with patch(DEBATE_COUNCIL_MODELS, SAMPLE_MODELS):
            events = []
            async for event in debate_round_parallel(
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


# =============================================================================
# Test: run_debate orchestrator event sequence
# =============================================================================


@pytest.mark.asyncio
async def test_run_debate_event_sequence():
    """
    Verify that run_debate with debate_round_parallel yields correct event
    sequence: round_start → model events → round_complete × 3 → debate_complete.
    """
    from llm_council.engine.debate import debate_round_parallel, run_debate

    async def mock_query(model, messages, *args, **kwargs):
        return {"content": f"Response from {model}"}

    async def mock_query_tools(model, messages, tools, tool_executor, *args, **kwargs):
        return {"content": f"Response from {model}"}

    with patch(DEBATE_QUERY_MODEL, side_effect=mock_query):
        with patch(DEBATE_QUERY_MODEL_WITH_TOOLS, side_effect=mock_query_tools):
            with patch(DEBATE_COUNCIL_MODELS, SAMPLE_MODELS):
                events = []
                async for event in run_debate(
                    user_query="Test question",
                    execute_round=debate_round_parallel,
                    cycles=1,
                ):
                    events.append(event)

    event_types = [e["type"] for e in events]

    # Should have 3 round_start events
    assert event_types.count("round_start") == 3

    # Should have 3 round_complete events
    assert event_types.count("round_complete") == 3

    # Should end with debate_complete event
    assert event_types[-1] == "debate_complete"

    # Verify round numbers in round_start events
    round_starts = [e for e in events if e["type"] == "round_start"]
    assert [r["round_number"] for r in round_starts] == [1, 2, 3]

    # Verify round types
    assert round_starts[0]["round_type"] == "initial"
    assert round_starts[1]["round_type"] == "critique"
    assert round_starts[2]["round_type"] == "defense"

    # Verify round_complete events carry augmented data
    round_completes = [e for e in events if e["type"] == "round_complete"]
    for rc in round_completes:
        assert "round_number" in rc
        assert "round_type" in rc
        assert "responses" in rc

    # Verify debate_complete has rounds data
    debate_complete = events[-1]
    assert debate_complete["type"] == "debate_complete"
    assert len(debate_complete["rounds"]) == 3


# =============================================================================
# Test: run_debate error on insufficient models
# =============================================================================


@pytest.mark.asyncio
async def test_run_debate_error_on_insufficient_models():
    """
    Verify that run_debate yields error event when <2 models respond.
    """
    from llm_council.engine.debate import debate_round_parallel, run_debate

    async def mock_query(model, messages, *args, **kwargs):
        # Only one model succeeds
        if model == SAMPLE_MODELS[0]:
            return {"content": f"Response from {model}"}
        return None

    async def mock_query_tools(model, messages, tools, tool_executor, *args, **kwargs):
        if model == SAMPLE_MODELS[0]:
            return {"content": f"Response from {model}"}
        return None

    with patch(DEBATE_QUERY_MODEL, side_effect=mock_query):
        with patch(DEBATE_QUERY_MODEL_WITH_TOOLS, side_effect=mock_query_tools):
            with patch(DEBATE_COUNCIL_MODELS, SAMPLE_MODELS):
                events = []
                async for event in run_debate(
                    user_query="Test question",
                    execute_round=debate_round_parallel,
                    cycles=1,
                ):
                    events.append(event)

    event_types = [e["type"] for e in events]

    # Should have an error event
    assert "error" in event_types

    # Should only have 1 round_start (initial) before error
    assert event_types.count("round_start") == 1


# =============================================================================
# Test: debate_round_streaming yields token events
# =============================================================================

DEBATE_QUERY_MODEL_STREAMING = "llm_council.engine.debate.query_model_streaming"
DEBATE_QUERY_MODEL_STREAMING_WITH_TOOLS = (
    "llm_council.engine.debate.query_model_streaming_with_tools"
)


@pytest.mark.asyncio
async def test_debate_round_streaming_yields_tokens():
    """
    Verify that debate_round_streaming yields token events, model_start/complete,
    and round_complete matching the execute-round protocol.
    """
    from llm_council.engine.debate import debate_round_streaming

    async def mock_streaming_with_tools(model, messages, tools, tool_executor, **kwargs):
        """Mock streaming with tools - yields token events then done."""
        yield {"type": "token", "content": "Hello "}
        yield {"type": "token", "content": "world"}
        yield {"type": "done", "content": "Hello world", "tool_calls_made": []}

    with patch(DEBATE_QUERY_MODEL_STREAMING_WITH_TOOLS, side_effect=mock_streaming_with_tools):
        with patch(DEBATE_COUNCIL_MODELS, SAMPLE_MODELS):
            events = []
            async for event in debate_round_streaming(
                round_type="initial",
                user_query="Test question",
                context={},
            ):
                events.append(event)

    # Should have model_start for each model
    model_starts = [e for e in events if e["type"] == "model_start"]
    assert len(model_starts) == len(SAMPLE_MODELS)

    # Should have token events
    token_events = [e for e in events if e["type"] == "token"]
    assert len(token_events) > 0

    # Each token event should identify the model
    for te in token_events:
        assert "model" in te
        assert te["model"] in SAMPLE_MODELS

    # Should have model_complete for each model
    model_completes = [e for e in events if e["type"] == "model_complete"]
    assert len(model_completes) == len(SAMPLE_MODELS)

    # Should end with round_complete
    round_completes = [e for e in events if e["type"] == "round_complete"]
    assert len(round_completes) == 1
    assert len(round_completes[0]["responses"]) == len(SAMPLE_MODELS)


# =============================================================================
# Test: Multiple cycles produce correct round sequence
# =============================================================================


@pytest.mark.asyncio
async def test_multiple_cycles_produces_correct_rounds():
    """
    Verify that cycles=2 produces 5 interaction rounds:
    initial, critique, defense, critique, defense.
    """
    from llm_council.engine.debate import debate_round_parallel, run_debate

    async def mock_query(model, messages, *args, **kwargs):
        return {"content": f"Response from {model}"}

    async def mock_query_tools(model, messages, tools, tool_executor, *args, **kwargs):
        return {"content": f"Response from {model}"}

    with patch(DEBATE_QUERY_MODEL, side_effect=mock_query):
        with patch(DEBATE_QUERY_MODEL_WITH_TOOLS, side_effect=mock_query_tools):
            with patch(DEBATE_COUNCIL_MODELS, SAMPLE_MODELS):
                events = []
                async for event in run_debate(
                    user_query="Test question",
                    execute_round=debate_round_parallel,
                    cycles=2,
                ):
                    events.append(event)

    round_starts = [e for e in events if e["type"] == "round_start"]
    assert len(round_starts) == 5

    # Verify round numbers and types
    assert [r["round_number"] for r in round_starts] == [1, 2, 3, 4, 5]
    assert round_starts[0]["round_type"] == "initial"
    assert round_starts[1]["round_type"] == "critique"
    assert round_starts[2]["round_type"] == "defense"
    assert round_starts[3]["round_type"] == "critique"
    assert round_starts[4]["round_type"] == "defense"

    # Should end with debate_complete
    assert events[-1]["type"] == "debate_complete"
    assert len(events[-1]["rounds"]) == 5


# =============================================================================
# Test: Streaming error prevents model_complete
# =============================================================================


@pytest.mark.asyncio
async def test_streaming_error_prevents_model_complete():
    """
    Verify that if tokens stream and then an error arrives,
    model_error is emitted but model_complete is NOT.
    """
    from llm_council.engine.debate import debate_round_streaming

    async def mock_streaming_with_tools(model, messages, tools, tool_executor, **kwargs):
        """Mock streaming that yields tokens then an error."""
        yield {"type": "token", "content": "Partial "}
        yield {"type": "token", "content": "content"}
        yield {"type": "error", "error": "Connection lost"}

    with patch(DEBATE_QUERY_MODEL_STREAMING_WITH_TOOLS, side_effect=mock_streaming_with_tools):
        with patch(DEBATE_COUNCIL_MODELS, [SAMPLE_MODELS[0]]):
            events = []
            async for event in debate_round_streaming(
                round_type="initial",
                user_query="Test question",
                context={},
            ):
                events.append(event)

    event_types = [e["type"] for e in events]

    # Should have token events
    assert event_types.count("token") == 2

    # Should have model_error
    assert "model_error" in event_types

    # Should NOT have model_complete (the bug fix)
    assert "model_complete" not in event_types

    # round_complete should have empty responses (the errored model is excluded)
    round_completes = [e for e in events if e["type"] == "round_complete"]
    assert len(round_completes) == 1
    assert len(round_completes[0]["responses"]) == 0
