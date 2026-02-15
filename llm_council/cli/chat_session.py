"""
Chat session management for interactive REPL mode.

Contains ChatState, command handlers, and run_chat_session.
"""

import asyncio
import uuid
from dataclasses import dataclass, field
from typing import Any

from llm_council.adapters import json_storage as storage
from llm_council.cli.chat_commands import (
    CHAT_COMMANDS,
    build_chat_prompt,
    build_context_prompt,
    format_chat_mode_line,
    parse_chat_command,
)
from llm_council.cli.constants import DEFAULT_DEBATE_ROUNDS
from llm_council.cli.presenters import (
    console,
    print_chat_banner,
    print_chat_help,
    print_chat_suggestions,
    print_history_table,
    print_stage1,
    print_stage2,
    print_user_question_panel,
)
from llm_council.cli.runners import (
    run_council_with_progress,
    run_debate_parallel,
    run_debate_streaming,
    run_reflection_synthesis,
)
from llm_council.engine import generate_conversation_title


@dataclass
class ChatState:
    """Mutable state for the chat REPL session."""

    debate_enabled: bool = True
    debate_rounds: int = DEFAULT_DEBATE_ROUNDS
    stream_enabled: bool = False
    react_enabled: bool = True
    conversation_id: str = ""
    conversation: dict[str, Any] | None = None
    title: str = field(default="New Conversation")


def resolve_conversation_id(prefix: str, conversations: list) -> str | None:
    """Resolve a conversation ID by prefix."""
    matches = [item["id"] for item in conversations if item["id"].startswith(prefix)]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        console.print("[chat.error]Multiple conversations match that prefix.[/chat.error]")
        return None
    console.print("[chat.error]No conversation matches that ID prefix.[/chat.error]")
    return None


def build_query_with_context(question: str, context: str) -> str:
    """Combine context and question into a single prompt string."""
    if not context:
        return question
    return f"{context}\n\nCurrent question: {question}"


# ---------------------------------------------------------------------------
# Helpers to reduce repeated argument passing
# ---------------------------------------------------------------------------


def _print_mode(state: ChatState) -> None:
    """Print the current mode line."""
    console.print(
        format_chat_mode_line(
            state.debate_enabled,
            state.debate_rounds,
            state.stream_enabled,
            react_enabled=state.react_enabled,
        )
    )


def _print_banner(state: ChatState, resumed: bool) -> None:
    """Print the chat banner."""
    print_chat_banner(
        state.title,
        state.conversation_id,
        resumed=resumed,
        debate_enabled=state.debate_enabled,
        debate_rounds=state.debate_rounds,
        stream_enabled=state.stream_enabled,
        react_enabled=state.react_enabled,
    )


# ---------------------------------------------------------------------------
# Command handlers — each returns True to continue the REPL, False to exit.
# ---------------------------------------------------------------------------


def cmd_exit(state: ChatState, argument: str | None) -> bool:
    console.print("[chat.meta]Exiting chat.[/chat.meta]")
    return False


def cmd_help(state: ChatState, argument: str | None) -> bool:
    print_chat_help()
    return True


def cmd_history(state: ChatState, argument: str | None) -> bool:
    print_history_table(storage.list_conversations())
    return True


def cmd_use(state: ChatState, argument: str | None) -> bool:
    if not argument:
        console.print("[chat.error]Usage: /use <id>[/chat.error]")
        return True
    resolved = resolve_conversation_id(argument, storage.list_conversations())
    if resolved:
        state.conversation_id = resolved
        state.conversation = storage.get_conversation(resolved)
        if state.conversation is None:
            console.print("[chat.error]Conversation not found.[/chat.error]")
            return True
        state.title = state.conversation.get("title", "New Conversation")
        _print_banner(state, resumed=True)
    return True


def cmd_new(state: ChatState, argument: str | None) -> bool:
    state.conversation_id = str(uuid.uuid4())
    state.conversation = storage.create_conversation(state.conversation_id)
    state.title = state.conversation.get("title", "New Conversation")
    _print_banner(state, resumed=False)
    return True


def cmd_debate(state: ChatState, argument: str | None) -> bool:
    if argument not in ("on", "off"):
        console.print("[chat.error]Usage: /debate on|off[/chat.error]")
        return True
    state.debate_enabled = argument == "on"
    _print_mode(state)
    return True


def cmd_rounds(state: ChatState, argument: str | None) -> bool:
    if not argument:
        console.print("[chat.error]Usage: /rounds N[/chat.error]")
        return True
    try:
        rounds_value = int(argument)
    except ValueError:
        console.print("[chat.error]Rounds must be an integer.[/chat.error]")
        return True
    if rounds_value < 2:
        console.print("[chat.error]Rounds must be at least 2.[/chat.error]")
        return True
    state.debate_rounds = rounds_value
    _print_mode(state)
    return True


def cmd_stream(state: ChatState, argument: str | None) -> bool:
    if argument not in ("on", "off"):
        console.print("[chat.error]Usage: /stream on|off[/chat.error]")
        return True
    state.stream_enabled = argument == "on"
    if state.stream_enabled and not state.debate_enabled:
        console.print("[chat.meta]Note: Streaming only applies in debate mode.[/chat.meta]")
    _print_mode(state)
    return True


def cmd_react(state: ChatState, argument: str | None) -> bool:
    if argument not in ("on", "off"):
        console.print("[chat.error]Usage: /react on|off[/chat.error]")
        return True
    state.react_enabled = argument == "on"
    _print_mode(state)
    return True


def cmd_mode(state: ChatState, argument: str | None) -> bool:
    _print_mode(state)
    return True


COMMAND_HANDLERS: dict[str, Any] = {
    "exit": cmd_exit,
    "help": cmd_help,
    "history": cmd_history,
    "use": cmd_use,
    "new": cmd_new,
    "debate": cmd_debate,
    "rounds": cmd_rounds,
    "stream": cmd_stream,
    "react": cmd_react,
    "mode": cmd_mode,
}


# ---------------------------------------------------------------------------
# Main session loop
# ---------------------------------------------------------------------------


async def run_chat_session(max_turns: int, start_new: bool) -> None:
    """Run interactive chat session with stored conversation history."""
    state = ChatState()
    conversations = storage.list_conversations()
    resumed = False

    if not start_new and conversations:
        state.conversation_id = conversations[0]["id"]
        state.conversation = storage.get_conversation(state.conversation_id)
        resumed = state.conversation is not None

    if state.conversation is None:
        state.conversation_id = str(uuid.uuid4())
        state.conversation = storage.create_conversation(state.conversation_id)
        resumed = False

    state.title = state.conversation.get("title", "New Conversation")
    _print_banner(state, resumed=resumed)

    while True:
        try:
            user_input = console.input(
                build_chat_prompt(state.debate_enabled, state.debate_rounds, state.stream_enabled)
            ).strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[chat.meta]Exiting chat.[/chat.meta]")
            break

        if not user_input:
            continue

        if user_input.startswith(("/", ":")):
            command, argument = parse_chat_command(user_input)
            if not command:
                print_chat_suggestions("")
                continue
            if command not in CHAT_COMMANDS:
                print_chat_suggestions(command)
                continue
            handler = COMMAND_HANDLERS.get(command)
            if handler is not None:
                if not handler(state, argument):
                    break
                continue
            console.print("[chat.error]Unknown command. Type /help for options.[/chat.error]")
            continue

        question = user_input
        state.conversation = storage.get_conversation(state.conversation_id)
        if state.conversation is None:
            state.conversation = storage.create_conversation(state.conversation_id)

        context = build_context_prompt(state.conversation, max_turns=max_turns)
        full_query = build_query_with_context(question, context)

        is_first_message = len(state.conversation.get("messages", [])) == 0
        storage.add_user_message(state.conversation_id, question)

        title_task = None
        if is_first_message:
            title_task = asyncio.create_task(generate_conversation_title(question))

        print_user_question_panel(question)

        if state.debate_enabled:
            # Run debate rounds (synthesis always via Reflection)
            if state.stream_enabled:
                debate_rounds_data, _ = await run_debate_streaming(
                    full_query,
                    state.debate_rounds,
                    react_enabled=state.react_enabled,
                )
            else:
                debate_rounds_data, _ = await run_debate_parallel(
                    full_query,
                    state.debate_rounds,
                    react_enabled=state.react_enabled,
                )

            if debate_rounds_data is None:
                console.print(
                    "[chat.error]Error: Debate mode failed to produce responses.[/chat.error]"
                )
                continue

            # Always run Reflection synthesis for chairman
            from llm_council.engine import build_react_context_debate

            context = build_react_context_debate(
                full_query, debate_rounds_data, len(debate_rounds_data)
            )
            synthesis = await run_reflection_synthesis(full_query, context)

            storage.add_debate_message(state.conversation_id, debate_rounds_data, synthesis)

            if title_task:
                state.title = await title_task
                storage.update_conversation_title(state.conversation_id, state.title)
        else:
            # Standard ranking mode (synthesis always via Reflection)
            stage1, stage2, metadata = await run_council_with_progress(full_query)

            if stage1 is None:
                console.print("[chat.error]Error: All models failed to respond.[/chat.error]")
                continue

            # Show Stage 1 and 2
            print_stage1(stage1)
            print_stage2(stage2, metadata["label_to_model"], metadata["aggregate_rankings"])

            # Always run Reflection synthesis for chairman
            from llm_council.engine import build_react_context_ranking

            context = build_react_context_ranking(full_query, stage1, stage2)
            stage3 = await run_reflection_synthesis(full_query, context)

            storage.add_assistant_message(state.conversation_id, stage1, stage2, stage3)

            if title_task:
                state.title = await title_task
                storage.update_conversation_title(state.conversation_id, state.title)
