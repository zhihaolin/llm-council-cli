"""
Tests for chat helpers.
"""

from cli.chat import (
    build_chat_prompt,
    format_chat_mode_line,
    parse_chat_command,
)


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
    assert "Debate (3 rounds)" in line


def test_format_chat_mode_line_ranking():
    line = format_chat_mode_line(False, 2)
    assert "Council (ranking)" in line


def test_build_chat_prompt_debate():
    prompt = build_chat_prompt(True, 3)
    assert "debate(3)>" in prompt


def test_build_chat_prompt_ranking():
    prompt = build_chat_prompt(False, 2)
    assert "rank>" in prompt
