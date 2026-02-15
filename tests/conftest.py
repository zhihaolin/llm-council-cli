"""
Pytest configuration and fixtures for LLM Council tests.

This module provides mock responses and fixtures for testing the engine
without making actual API calls.
"""

from typing import Any

import pytest

# =============================================================================
# Sample Model Responses
# =============================================================================

SAMPLE_MODELS = [
    "openai/gpt-5.2",
    "google/gemini-3-pro-preview",
    "anthropic/claude-sonnet-4.5",
]

SAMPLE_INITIAL_RESPONSES = [
    {
        "model": "openai/gpt-5.2",
        "response": "Python is the best language for beginners due to its readable syntax.",
    },
    {
        "model": "google/gemini-3-pro-preview",
        "response": "JavaScript is ideal for beginners because it runs in browsers.",
    },
    {
        "model": "anthropic/claude-sonnet-4.5",
        "response": "Python offers the gentlest learning curve for new programmers.",
    },
]

SAMPLE_CRITIQUE_RESPONSES = [
    {
        "model": "openai/gpt-5.2",
        "response": """## Critique of google/gemini-3-pro-preview
JavaScript has a steeper learning curve due to async concepts.

## Critique of anthropic/claude-sonnet-4.5
Good point about Python, but lacks specific examples.""",
    },
    {
        "model": "google/gemini-3-pro-preview",
        "response": """## Critique of openai/gpt-5.2
Python syntax is readable but doesn't teach web development.

## Critique of anthropic/claude-sonnet-4.5
Agrees with Python but could mention JavaScript's ubiquity.""",
    },
    {
        "model": "anthropic/claude-sonnet-4.5",
        "response": """## Critique of openai/gpt-5.2
Valid point about Python. Could elaborate on learning resources.

## Critique of google/gemini-3-pro-preview
Browser availability is good, but JavaScript quirks confuse beginners.""",
    },
]

SAMPLE_DEFENSE_RESPONSES = [
    {
        "model": "openai/gpt-5.2",
        "response": """## Addressing Critiques
The web development point is valid. However, Python can be used for web via Django/Flask.

## Revised Response
Python remains the best choice for beginners due to its readable syntax and versatility. While JavaScript is essential for web development, Python's gentler learning curve makes it ideal for first-time programmers.""",
    },
    {
        "model": "google/gemini-3-pro-preview",
        "response": """## Addressing Critiques
I concede that async concepts can be challenging. However, modern tutorials handle this well.

## Revised Response
JavaScript is a strong choice for beginners who want to see immediate visual results in the browser. For those focused on general programming concepts, Python may be more appropriate.""",
    },
    {
        "model": "anthropic/claude-sonnet-4.5",
        "response": """## Addressing Critiques
I'll add more specific examples as suggested.

## Revised Response
Python offers the gentlest learning curve due to: 1) English-like syntax, 2) No compilation step, 3) Extensive beginner resources like Codecademy and freeCodeCamp.""",
    },
]

SAMPLE_RANKING_TEXT = """Response A provides good practical advice with clear reasoning.
Response B offers a different perspective but lacks depth.
Response C is comprehensive but could be more concise.

FINAL RANKING:
1. Response A
2. Response C
3. Response B"""

SAMPLE_RANKING_TEXT_NO_HEADER = """Response A is best.
Response C is second.
Response B is third."""


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def sample_models() -> list[str]:
    """Return sample model identifiers."""
    return SAMPLE_MODELS.copy()


@pytest.fixture
def sample_initial_responses() -> list[dict[str, Any]]:
    """Return sample initial responses from models."""
    return [r.copy() for r in SAMPLE_INITIAL_RESPONSES]


@pytest.fixture
def sample_critique_responses() -> list[dict[str, Any]]:
    """Return sample critique responses."""
    return [r.copy() for r in SAMPLE_CRITIQUE_RESPONSES]


@pytest.fixture
def sample_defense_responses() -> list[dict[str, Any]]:
    """Return sample defense responses."""
    return [r.copy() for r in SAMPLE_DEFENSE_RESPONSES]


@pytest.fixture
def sample_ranking_text() -> str:
    """Return sample ranking text with FINAL RANKING header."""
    return SAMPLE_RANKING_TEXT


@pytest.fixture
def sample_ranking_text_no_header() -> str:
    """Return sample ranking text without proper header."""
    return SAMPLE_RANKING_TEXT_NO_HEADER


