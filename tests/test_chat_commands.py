"""
Tests for chat helpers.
"""

from llm_council.cli.chat_commands import (
    build_chat_prompt,
    format_chat_mode_line,
    parse_chat_command,
)
from llm_council.cli.presenters import build_model_panel


def test_parse_command_with_argument():
    command, argument = parse_chat_command("/debate on")
    assert command == "debate"
    assert argument == "on"


def test_parse_command_without_argument():
    command, argument = parse_chat_command("/exit")
    assert command == "exit"
    assert argument is None


def test_parse_command_trims_whitespace():
    command, argument = parse_chat_command("  /use   abc123  ")
    assert command == "use"
    assert argument == "abc123"


def test_parse_non_command_text():
    command, argument = parse_chat_command("hello")
    assert command == ""
    assert argument is None


def test_parse_empty_command():
    command, argument = parse_chat_command("/")
    assert command == ""
    assert argument is None


def test_parse_alias_quit():
    command, argument = parse_chat_command("/q")
    assert command == "exit"
    assert argument is None


def test_format_chat_mode_line_debate():
    line = format_chat_mode_line(True, 3)
    assert line == "Debate \u00b7 3 rounds \u00b7 React on \u00b7 Stream off"


def test_format_chat_mode_line_debate_single_round():
    line = format_chat_mode_line(True, 1)
    assert line == "Debate \u00b7 1 round \u00b7 React on \u00b7 Stream off"


def test_format_chat_mode_line_debate_stream_on():
    line = format_chat_mode_line(True, 2, stream_enabled=True, react_enabled=False)
    assert line == "Debate \u00b7 2 rounds \u00b7 React off \u00b7 Stream on"


def test_format_chat_mode_line_ranking():
    line = format_chat_mode_line(False, 2)
    assert line == "Ranking \u00b7 React on"


def test_format_chat_mode_line_ranking_react_off():
    line = format_chat_mode_line(False, 2, react_enabled=False)
    assert line == "Ranking \u00b7 React off"


def test_build_chat_prompt_always_council():
    prompt = build_chat_prompt()
    assert "council>" in prompt


def test_build_model_panel_with_indicators():
    panel = build_model_panel("openai/gpt-4.1", "Hello", reasoned=True, searched=True)
    # Title should contain the short model name and both indicators
    title_text = panel.title
    assert "gpt-4.1" in title_text
    assert "[reasoned]" in title_text
    assert "[searched]" in title_text


def test_build_model_panel_no_indicators():
    panel = build_model_panel("openai/gpt-4.1", "Hello")
    title_text = panel.title
    assert "gpt-4.1" in title_text
    assert "[reasoned]" not in title_text
    assert "[searched]" not in title_text
