"""
Chat session management for interactive REPL mode.

Contains run_chat_session and related state management.
"""

import asyncio
import uuid

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
    print_debate_synthesis,
    print_history_table,
    print_stage1,
    print_stage2,
    print_stage3,
    print_user_question_panel,
)
from llm_council.cli.runners import (
    run_council_with_progress,
    run_debate_parallel,
    run_debate_streaming,
    run_react_synthesis,
)
from llm_council.engine import generate_conversation_title


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


async def run_chat_session(max_turns: int, start_new: bool) -> None:
    """Run interactive chat session with stored conversation history."""
    conversations = storage.list_conversations()
    conversation_id = None
    conversation = None
    resumed = False
    debate_enabled = True
    debate_rounds = DEFAULT_DEBATE_ROUNDS
    stream_enabled = False
    react_enabled = True

    if not start_new and conversations:
        conversation_id = conversations[0]["id"]
        conversation = storage.get_conversation(conversation_id)
        resumed = conversation is not None

    if conversation is None:
        conversation_id = str(uuid.uuid4())
        conversation = storage.create_conversation(conversation_id)
        resumed = False

    title = conversation.get("title", "New Conversation")
    print_chat_banner(
        title,
        conversation_id,
        resumed=resumed,
        debate_enabled=debate_enabled,
        debate_rounds=debate_rounds,
        stream_enabled=stream_enabled,
        react_enabled=react_enabled,
    )

    while True:
        try:
            user_input = console.input(
                build_chat_prompt(debate_enabled, debate_rounds, stream_enabled)
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
            if command == "exit":
                console.print("[chat.meta]Exiting chat.[/chat.meta]")
                break
            if command == "help":
                print_chat_help()
                continue
            if command == "history":
                print_history_table(storage.list_conversations())
                continue
            if command == "use":
                if not argument:
                    console.print("[chat.error]Usage: /use <id>[/chat.error]")
                    continue
                prefix = argument
                resolved = resolve_conversation_id(prefix, storage.list_conversations())
                if resolved:
                    conversation_id = resolved
                    conversation = storage.get_conversation(conversation_id)
                    if conversation is None:
                        console.print("[chat.error]Conversation not found.[/chat.error]")
                        continue
                    title = conversation.get("title", "New Conversation")
                    print_chat_banner(
                        title,
                        conversation_id,
                        resumed=True,
                        debate_enabled=debate_enabled,
                        debate_rounds=debate_rounds,
                        stream_enabled=stream_enabled,
                        react_enabled=react_enabled,
                    )
                continue
            if command == "new":
                conversation_id = str(uuid.uuid4())
                conversation = storage.create_conversation(conversation_id)
                title = conversation.get("title", "New Conversation")
                print_chat_banner(
                    title,
                    conversation_id,
                    resumed=False,
                    debate_enabled=debate_enabled,
                    debate_rounds=debate_rounds,
                    stream_enabled=stream_enabled,
                    react_enabled=react_enabled,
                )
                continue
            if command == "debate":
                if argument not in ("on", "off"):
                    console.print("[chat.error]Usage: /debate on|off[/chat.error]")
                    continue
                debate_enabled = argument == "on"
                console.print(
                    format_chat_mode_line(
                        debate_enabled,
                        debate_rounds,
                        stream_enabled,
                        react_enabled=react_enabled,
                    )
                )
                continue
            if command == "rounds":
                if not argument:
                    console.print("[chat.error]Usage: /rounds N[/chat.error]")
                    continue
                try:
                    rounds_value = int(argument)
                except ValueError:
                    console.print("[chat.error]Rounds must be an integer.[/chat.error]")
                    continue
                if rounds_value < 2:
                    console.print("[chat.error]Rounds must be at least 2.[/chat.error]")
                    continue
                debate_rounds = rounds_value
                console.print(
                    format_chat_mode_line(
                        debate_enabled,
                        debate_rounds,
                        stream_enabled,
                        react_enabled=react_enabled,
                    )
                )
                continue
            if command == "stream":
                if argument not in ("on", "off"):
                    console.print("[chat.error]Usage: /stream on|off[/chat.error]")
                    continue
                stream_enabled = argument == "on"
                if stream_enabled and not debate_enabled:
                    console.print(
                        "[chat.meta]Note: Streaming only applies in debate mode.[/chat.meta]"
                    )
                console.print(
                    format_chat_mode_line(
                        debate_enabled,
                        debate_rounds,
                        stream_enabled,
                        react_enabled=react_enabled,
                    )
                )
                continue
            if command == "react":
                if argument not in ("on", "off"):
                    console.print("[chat.error]Usage: /react on|off[/chat.error]")
                    continue
                react_enabled = argument == "on"
                console.print(
                    format_chat_mode_line(
                        debate_enabled,
                        debate_rounds,
                        stream_enabled,
                        react_enabled=react_enabled,
                    )
                )
                continue
            if command == "mode":
                console.print(
                    format_chat_mode_line(
                        debate_enabled,
                        debate_rounds,
                        stream_enabled,
                        react_enabled=react_enabled,
                    )
                )
                continue

            console.print("[chat.error]Unknown command. Type /help for options.[/chat.error]")
            continue

        question = user_input
        conversation = storage.get_conversation(conversation_id)
        if conversation is None:
            conversation = storage.create_conversation(conversation_id)

        context = build_context_prompt(conversation, max_turns=max_turns)
        full_query = build_query_with_context(question, context)

        is_first_message = len(conversation.get("messages", [])) == 0
        storage.add_user_message(conversation_id, question)

        title_task = None
        if is_first_message:
            title_task = asyncio.create_task(generate_conversation_title(question))

        print_user_question_panel(question)

        if debate_enabled:
            # Use ReAct if enabled (works with all modes)
            use_react_here = react_enabled

            if stream_enabled:
                # Streaming mode - shows responses token-by-token (sequential)
                debate_rounds_data, synthesis = await run_debate_streaming(
                    full_query,
                    debate_rounds,
                    skip_synthesis=use_react_here,
                )
            else:
                # Parallel mode (default) - runs models concurrently with progress spinners
                debate_rounds_data, synthesis = await run_debate_parallel(
                    full_query,
                    debate_rounds,
                    skip_synthesis=use_react_here,
                )

            if debate_rounds_data is None:
                console.print(
                    "[chat.error]Error: Debate mode failed to produce responses.[/chat.error]"
                )
                continue

            # If using ReAct, run synthesis separately
            if use_react_here:
                from llm_council.engine import build_react_context_debate

                # Run ReAct synthesis (both parallel and streaming already displayed rounds)
                context = build_react_context_debate(
                    full_query, debate_rounds_data, len(debate_rounds_data)
                )
                synthesis = await run_react_synthesis(full_query, context)
                print_debate_synthesis(synthesis)

            storage.add_debate_message(conversation_id, debate_rounds_data, synthesis)

            if title_task:
                title = await title_task
                storage.update_conversation_title(conversation_id, title)
        else:
            # Standard ranking mode
            use_react_here = react_enabled
            stage1, stage2, stage3, metadata = await run_council_with_progress(
                full_query, skip_synthesis=use_react_here
            )

            if stage1 is None:
                console.print("[chat.error]Error: All models failed to respond.[/chat.error]")
                continue

            # If using ReAct, run synthesis separately
            if use_react_here:
                from llm_council.engine import build_react_context_ranking

                # Show Stage 1 and 2 first
                print_stage1(stage1)
                print_stage2(stage2, metadata["label_to_model"], metadata["aggregate_rankings"])
                # Run ReAct synthesis
                context = build_react_context_ranking(full_query, stage1, stage2)
                stage3 = await run_react_synthesis(full_query, context)
                print_stage3(stage3)

            storage.add_assistant_message(conversation_id, stage1, stage2, stage3)

            if title_task:
                title = await title_task
                storage.update_conversation_title(conversation_id, title)

            if not use_react_here:
                print_stage1(stage1)
                print_stage2(stage2, metadata["label_to_model"], metadata["aggregate_rankings"])
                print_stage3(stage3)
