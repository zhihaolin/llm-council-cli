"""
Tests for the debate mode functionality in debate.py.

These tests verify the multi-round debate logic including critique extraction,
defense parsing, RoundConfig, and debate orchestration.
"""

import pytest

from llm_council.engine import (
    build_round_config,
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

        result = extract_critiques_for_model("google/gemini-3-pro-preview", critique_responses)

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

        result = extract_critiques_for_model("google/gemini-3-pro-preview", critique_responses)

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

        result = extract_critiques_for_model("google/gemini-3-pro-preview", critique_responses)

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

        result = extract_critiques_for_model("anthropic/claude-sonnet-4.5", critique_responses)

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


class TestDebateDataStructures:
    """Tests for debate mode data structures and storage format."""

    def test_round_data_structure(self):
        """Verify round data has required fields."""
        round_data = {
            "round_number": 1,
            "round_type": "initial",
            "responses": [{"model": "test/model", "response": "Test response"}],
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
            "revised_answer": "Extracted revised answer",
        }

        assert "model" in defense_response
        assert "response" in defense_response
        assert "revised_answer" in defense_response


class TestBuildRoundConfig:
    """Tests for the build_round_config factory function."""

    def test_initial_config(self):
        """Initial round should use tools and not parse revised answers."""
        config = build_round_config("initial", "What is AI?", {})
        assert config.uses_tools is True
        assert config.has_revised_answer is False

    def test_critique_config(self):
        """Critique round should not use tools and not parse revised answers."""
        context = {
            "initial_responses": [{"model": "test/m", "response": "answer"}],
        }
        config = build_round_config("critique", "What is AI?", context)
        assert config.uses_tools is False
        assert config.has_revised_answer is False

    def test_defense_config(self):
        """Defense round should use tools and parse revised answers."""
        context = {
            "initial_responses": [{"model": "test/m", "response": "answer"}],
            "critique_responses": [{"model": "test/m2", "response": "critique"}],
        }
        config = build_round_config("defense", "What is AI?", context)
        assert config.uses_tools is True
        assert config.has_revised_answer is True

    def test_initial_prompt_includes_date(self):
        """Initial prompt should contain date context."""
        config = build_round_config("initial", "What is AI?", {})
        prompt = config.build_prompt("test/model")
        assert "Today's date is" in prompt
        assert "What is AI?" in prompt

    def test_critique_prompt_per_model(self):
        """Critique prompts should differ per model (model name in prompt)."""
        context = {
            "initial_responses": [{"model": "test/m", "response": "answer"}],
        }
        config = build_round_config("critique", "Q?", context)
        prompt_a = config.build_prompt("model/a")
        prompt_b = config.build_prompt("model/b")
        assert "model/a" in prompt_a
        assert "model/b" in prompt_b
        assert prompt_a != prompt_b

    def test_defense_prompt_includes_critiques(self):
        """Defense prompt should include critique content for the model."""
        context = {
            "initial_responses": [
                {"model": "test/m", "response": "my original answer"},
            ],
            "critique_responses": [
                {
                    "model": "test/m2",
                    "response": "## Critique of test/m\nYour answer is weak.",
                },
            ],
        }
        config = build_round_config("defense", "Q?", context)
        prompt = config.build_prompt("test/m")
        assert "my original answer" in prompt
        assert "weak" in prompt.lower()

    def test_unknown_round_type_raises(self):
        """Unknown round type should raise ValueError."""
        with pytest.raises(ValueError, match="Unknown round type"):
            build_round_config("invalid", "Q?", {})

    def test_initial_with_react_sets_uses_react(self):
        """Initial round with react_enabled=True should set uses_react=True."""
        config = build_round_config("initial", "What is AI?", {}, react_enabled=True)
        assert config.uses_react is True
        assert config.uses_tools is True

    def test_critique_ignores_react(self):
        """Critique round should never use ReAct, even with react_enabled=True."""
        context = {
            "initial_responses": [{"model": "test/m", "response": "answer"}],
        }
        config = build_round_config("critique", "What is AI?", context, react_enabled=True)
        assert config.uses_react is False
        assert config.uses_tools is False

    def test_defense_with_react_sets_uses_react(self):
        """Defense round with react_enabled=True should set uses_react=True."""
        context = {
            "initial_responses": [{"model": "test/m", "response": "answer"}],
            "critique_responses": [{"model": "test/m2", "response": "critique"}],
        }
        config = build_round_config("defense", "What is AI?", context, react_enabled=True)
        assert config.uses_react is True
        assert config.uses_tools is True

    def test_react_wraps_initial_prompt(self):
        """When react_enabled, initial prompt should include ReAct instructions."""
        config = build_round_config("initial", "What is AI?", {}, react_enabled=True)
        prompt = config.build_prompt("test/model")
        assert "search_web" in prompt
        assert "respond()" in prompt

    def test_react_wraps_defense_prompt(self):
        """When react_enabled, defense prompt should include ReAct instructions."""
        context = {
            "initial_responses": [{"model": "test/m", "response": "answer"}],
            "critique_responses": [{"model": "test/m2", "response": "critique"}],
        }
        config = build_round_config("defense", "Q?", context, react_enabled=True)
        prompt = config.build_prompt("test/m")
        assert "search_web" in prompt
        assert "respond()" in prompt

    def test_no_react_by_default(self):
        """Without react_enabled, uses_react should be False."""
        config = build_round_config("initial", "What is AI?", {})
        assert config.uses_react is False
