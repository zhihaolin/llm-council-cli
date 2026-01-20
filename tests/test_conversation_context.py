"""
Tests for building conversation context from stored messages.
"""

from cli.chat import (
    extract_conversation_pairs,
    select_context_pairs,
    build_context_prompt,
)


def test_extract_pairs_standard():
    messages = [
        {"role": "user", "content": "Q1"},
        {"role": "assistant", "stage3": {"response": "A1"}},
        {"role": "user", "content": "Q2"},
        {"role": "assistant", "stage3": {"response": "A2"}},
    ]

    pairs = extract_conversation_pairs(messages)

    assert pairs == [("Q1", "A1"), ("Q2", "A2")]


def test_extract_pairs_debate_synthesis():
    messages = [
        {"role": "user", "content": "Debate Q"},
        {"role": "assistant", "mode": "debate", "synthesis": {"response": "Final A"}},
    ]

    pairs = extract_conversation_pairs(messages)

    assert pairs == [("Debate Q", "Final A")]


def test_select_context_pairs_includes_first_and_last():
    pairs = [
        ("Q1", "A1"),
        ("Q2", "A2"),
        ("Q3", "A3"),
        ("Q4", "A4"),
    ]

    selected = select_context_pairs(pairs, max_turns=2)

    assert selected == [("Q1", "A1"), ("Q3", "A3"), ("Q4", "A4")]


def test_build_context_prompt_empty():
    conversation = {"messages": []}

    context = build_context_prompt(conversation, max_turns=3)

    assert context == ""


def test_build_context_prompt_contains_pairs():
    conversation = {
        "messages": [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "stage3": {"response": "Hi there"}},
        ]
    }

    context = build_context_prompt(conversation, max_turns=3)

    assert "Conversation context" in context
    assert "User: Hello" in context
    assert "Assistant: Hi there" in context
