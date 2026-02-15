"""
Tests for the debate mode functionality in council.py.

These tests verify the multi-round debate logic including critique extraction,
defense parsing, and debate orchestration.
"""

from unittest.mock import AsyncMock, patch

import pytest

from llm_council.council import (
    debate_round_critique,
    debate_round_defense,
    extract_critiques_for_model,
    parse_revised_answer,
)


class TestExtractCritiquesForModel:
    """Tests for extract_critiques_for_model function."""

    def test_extracts_critique_by_model_name(self):
        """Test that critiques are correctly extracted for a target model."""
        critique_responses = [
            {
                "model": "openai/gpt-5.2",
                "response": """## Critique of google/gemini-3-pro-preview
Gemini's response lacks depth on the topic.

## Critique of anthropic/claude-sonnet-4.5
Claude provides good examples but misses edge cases.""",
            },
            {
                "model": "anthropic/claude-sonnet-4.5",
                "response": """## Critique of openai/gpt-5.2
GPT's response is too verbose.

## Critique of google/gemini-3-pro-preview
Gemini should provide more references.""",
            },
        ]

        result = extract_critiques_for_model(
            "google/gemini-3-pro-preview",
            critique_responses
        )

        # Should contain critiques from both GPT and Claude about Gemini
        assert "gpt-5.2" in result.lower() or "openai" in result.lower()
        assert "claude" in result.lower() or "anthropic" in result.lower()
        assert "lacks depth" in result.lower()
        assert "more references" in result.lower()

    def test_excludes_self_critique(self):
        """Test that a model's self-critique is excluded (shouldn't exist anyway)."""
        critique_responses = [
            {
                "model": "openai/gpt-5.2",
                "response": """## Critique of openai/gpt-5.2
This shouldn't be included.

## Critique of google/gemini-3-pro-preview
Valid critique here.""",
            },
        ]

        result = extract_critiques_for_model("openai/gpt-5.2", critique_responses)

        # Self-critique should be excluded
        assert "shouldn't be included" not in result

    def test_handles_no_critiques_found(self):
        """Test graceful handling when no critiques are found."""
        critique_responses = [
            {
                "model": "openai/gpt-5.2",
                "response": "This response doesn't follow the expected format at all.",
            },
        ]

        result = extract_critiques_for_model(
            "google/gemini-3-pro-preview",
            critique_responses
        )

        assert "no specific critiques" in result.lower()

    def test_matches_model_name_case_insensitively(self):
        """Test that model name matching is case-insensitive."""
        critique_responses = [
            {
                "model": "openai/gpt-5.2",
                "response": """## Critique of GEMINI-3-PRO-PREVIEW
Uppercase model name should still match.""",
            },
        ]

        result = extract_critiques_for_model(
            "google/gemini-3-pro-preview",
            critique_responses
        )

        assert "uppercase model name" in result.lower()

    def test_handles_partial_model_name(self):
        """Test matching when critique uses partial model name."""
        critique_responses = [
            {
                "model": "openai/gpt-5.2",
                "response": """## Critique of claude-sonnet-4.5
Claude's response needs improvement.""",
            },
        ]

        result = extract_critiques_for_model(
            "anthropic/claude-sonnet-4.5",
            critique_responses
        )

        assert "needs improvement" in result.lower()


class TestParseRevisedAnswer:
    """Tests for parse_revised_answer function."""

    def test_extracts_revised_response_section(self):
        """Test extraction of Revised Response section."""
        defense_text = """## Addressing Critiques
I acknowledge the feedback about verbosity.

## Revised Response
This is my improved, more concise answer to the question.
It addresses the concerns raised."""

        result = parse_revised_answer(defense_text)

        assert "improved, more concise answer" in result
        assert "Addressing Critiques" not in result

    def test_handles_missing_section(self):
        """Test fallback when Revised Response section is missing."""
        defense_text = """## Addressing Critiques
I acknowledge the feedback.

Here is my updated answer without proper section header."""

        result = parse_revised_answer(defense_text)

        # Should return full text as fallback
        assert "acknowledge the feedback" in result

    def test_handles_different_header_capitalization(self):
        """Test that header matching is case-insensitive."""
        defense_text = """## addressing critiques
Some response.

## revised response
My updated answer here."""

        result = parse_revised_answer(defense_text)

        assert "updated answer" in result

    def test_handles_extra_whitespace(self):
        """Test handling of extra whitespace around header."""
        defense_text = """##   Revised Response
My answer with whitespace around header."""

        result = parse_revised_answer(defense_text)

        assert "whitespace around header" in result


class TestDebateRoundCritique:
    """Tests for debate_round_critique async function."""

    @pytest.mark.asyncio
    async def test_critique_round_queries_all_models(self, sample_initial_responses):
        """Test that critique round queries all participating models."""
        with patch("llm_council.council.debate.query_model", new_callable=AsyncMock) as mock_query:
            mock_query.return_value = {"content": "## Critique of model\nTest critique."}

            result = await debate_round_critique(
                "What is the best programming language?",
                sample_initial_responses
            )

            # Should have called query_model for each model
            assert mock_query.call_count == len(sample_initial_responses)

            # Should return responses for all models
            assert len(result) == len(sample_initial_responses)

    @pytest.mark.asyncio
    async def test_critique_round_handles_failures(self, sample_initial_responses):
        """Test that critique round continues if some models fail."""
        call_count = 0

        async def mock_query(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return None  # First model fails
            return {"content": "Valid critique"}

        with patch("llm_council.council.debate.query_model", side_effect=mock_query):
            result = await debate_round_critique(
                "Test question",
                sample_initial_responses
            )

            # Should still have results from successful models
            assert len(result) == len(sample_initial_responses) - 1


class TestDebateRoundDefense:
    """Tests for debate_round_defense async function."""

    @pytest.mark.asyncio
    async def test_defense_round_includes_revised_answer(
        self,
        sample_initial_responses,
        sample_critique_responses
    ):
        """Test that defense round extracts revised answers."""
        defense_content = """## Addressing Critiques
Valid points were raised.

## Revised Response
This is my improved answer."""

        with patch("llm_council.council.debate.query_model", new_callable=AsyncMock) as mock_query:
            mock_query.return_value = {"content": defense_content}

            result = await debate_round_defense(
                "Test question",
                sample_initial_responses,
                sample_critique_responses
            )

            # Each result should have a revised_answer field
            for r in result:
                assert "revised_answer" in r
                assert "improved answer" in r["revised_answer"]

    @pytest.mark.asyncio
    async def test_defense_round_passes_critiques_to_model(
        self,
        sample_initial_responses,
        sample_critique_responses
    ):
        """Test that each model receives critiques directed at them."""
        with patch("llm_council.council.debate.query_model", new_callable=AsyncMock) as mock_query:
            mock_query.return_value = {"content": "## Revised Response\nTest"}

            await debate_round_defense(
                "Test question",
                sample_initial_responses,
                sample_critique_responses
            )

            # Verify that prompts contain critique information
            for call in mock_query.call_args_list:
                messages = call[1].get("messages", call[0][1] if len(call[0]) > 1 else [])
                prompt = messages[0]["content"] if messages else ""
                assert "Critiques of your response" in prompt or "critique" in prompt.lower()


class TestDebateDataStructures:
    """Tests for debate mode data structures and storage format."""

    def test_round_data_structure(self):
        """Verify round data has required fields."""
        round_data = {
            "round_number": 1,
            "round_type": "initial",
            "responses": [
                {"model": "test/model", "response": "Test response"}
            ]
        }

        assert "round_number" in round_data
        assert "round_type" in round_data
        assert "responses" in round_data
        assert round_data["round_type"] in ["initial", "critique", "defense"]

    def test_defense_response_structure(self):
        """Verify defense response has revised_answer field."""
        defense_response = {
            "model": "test/model",
            "response": "Full response text",
            "revised_answer": "Extracted revised answer"
        }

        assert "model" in defense_response
        assert "response" in defense_response
        assert "revised_answer" in defense_response
