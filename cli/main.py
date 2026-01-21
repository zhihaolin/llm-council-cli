#!/usr/bin/env python3
"""
LLM Council CLI - Query multiple LLMs and synthesize their responses.

Usage:
    llm-council "Your question here"
    llm-council --simple "Quick question"
    llm-council models
"""

import asyncio
import sys
import uuid
from typing import Optional

import typer
from rich.console import Console, Group
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich.markdown import Markdown
from rich.theme import Theme
from rich.live import Live
from rich.text import Text

# Import council logic from backend
sys.path.insert(0, str(__file__).rsplit("/", 2)[0])  # Add project root to path
from backend.council import (
    stage1_collect_responses,
    stage2_collect_rankings,
    stage3_synthesize_final,
    calculate_aggregate_rankings,
    run_debate_council,
    run_debate_council_streaming,
    run_debate_token_streaming,
    generate_conversation_title,
)
from backend.config import COUNCIL_MODELS, CHAIRMAN_MODEL
from backend import storage

from cli.chat import (
    CHAT_COMMANDS,
    build_context_prompt,
    build_chat_prompt,
    format_chat_mode_line,
    parse_chat_command,
    suggest_chat_commands,
)

CHAT_THEME = Theme({
    "chat.accent": "bold #5B8DEF",
    "chat.prompt": "bold #5B8DEF",
    "chat.meta": "dim",
    "chat.command": "#E0B15A",
    "chat.success": "green",
    "chat.error": "bold red",
})

app = typer.Typer(
    name="llm-council",
    help="Query multiple LLMs and get a synthesized council response.",
    add_completion=False,
    no_args_is_help=True,
)
console = Console(theme=CHAT_THEME)

CHAT_BORDER_COLOR = "#5B8DEF"
DEFAULT_CONTEXT_TURNS = 6
DEFAULT_DEBATE_ROUNDS = 2


def print_chat_banner(
    title: str,
    conversation_id: str,
    resumed: bool,
    debate_enabled: bool,
    debate_rounds: int,
    stream_enabled: bool = False,
    parallel_enabled: bool = False,
    react_enabled: bool = True,
) -> None:
    """Show chat banner with conversation details."""
    short_id = conversation_id[:8]
    status = "Resumed" if resumed else "Started"
    body = (
        f"[chat.meta]{status} conversation[/chat.meta]\n"
        f"[chat.accent]{title}[/chat.accent]\n"
        f"[chat.meta]ID: {short_id}[/chat.meta]\n"
        f"{format_chat_mode_line(debate_enabled, debate_rounds, stream_enabled, parallel_enabled, react_enabled)}"
    )
    console.print()
    console.print(Panel(
        body,
        title="[chat.accent]Council Chat[/chat.accent]",
        border_style=CHAT_BORDER_COLOR,
        padding=(1, 2),
    ))
    console.print("[chat.meta]Commands: /help, /history, /use <id>, /new, /debate, /rounds, /stream, /mode, /exit[/chat.meta]")
    console.print()


def print_chat_help() -> None:
    """Print available chat commands."""
    console.print("[chat.accent]Chat commands[/chat.accent]")
    console.print("[chat.command]/help[/chat.command]    Show this help")
    console.print("[chat.command]/history[/chat.command] List saved conversations")
    console.print("[chat.command]/use <id>[/chat.command] Switch to a conversation by ID prefix")
    console.print("[chat.command]/new[/chat.command]     Start a new conversation")
    console.print("[chat.command]/debate on|off[/chat.command] Toggle debate mode")
    console.print("[chat.command]/rounds N[/chat.command] Set debate rounds")
    console.print("[chat.command]/stream on|off[/chat.command] Toggle streaming (debate only)")
    console.print("[chat.command]/mode[/chat.command]    Show current mode")
    console.print("[chat.command]/exit[/chat.command]    Exit chat")
    console.print()


def print_chat_suggestions(prefix: str) -> None:
    """Print command suggestions based on a prefix."""
    suggestions = suggest_chat_commands(prefix)
    if not suggestions:
        console.print("[chat.error]No matching commands.[/chat.error]")
        console.print()
        return

    label = "Commands" if not prefix else f"Commands matching '{prefix}'"
    console.print(f"[chat.meta]{label}[/chat.meta]")
    for command in suggestions:
        console.print(f"[chat.command]/{command}[/chat.command]  {CHAT_COMMANDS[command]}")
    console.print()


def print_history_table(conversations: list) -> None:
    """Print a table of conversation history."""
    table = Table(title="Conversation History", show_header=True, header_style="chat.accent")
    table.add_column("ID", style="chat.accent", width=10)
    table.add_column("Title", style="white")
    table.add_column("Messages", justify="right", width=8)
    table.add_column("Created", style="chat.meta", width=19)

    for item in conversations:
        created = item.get("created_at", "").replace("T", " ")[:19]
        table.add_row(
            item["id"][:8],
            item.get("title", "New Conversation"),
            str(item.get("message_count", 0)),
            created,
        )

    console.print(table)
    console.print()


def resolve_conversation_id(prefix: str, conversations: list) -> Optional[str]:
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


def print_stage1(results: list) -> None:
    """Display Stage 1 results."""
    console.print("\n[bold cyan]━━━ STAGE 1: Individual Responses ━━━[/bold cyan]\n")
    for result in results:
        model = result["model"]
        response = result["response"]
        searched = result.get("tool_calls_made")
        title = f"[bold blue]{model}[/bold blue]"
        if searched:
            title += " [dim]• searched[/dim]"
        console.print(Panel(
            Markdown(response),
            title=title,
            border_style="blue",
            padding=(1, 2),
        ))
        console.print()


def print_stage2(results: list, label_to_model: dict, aggregate: list) -> None:
    """Display Stage 2 results."""
    console.print("\n[bold cyan]━━━ STAGE 2: Peer Rankings ━━━[/bold cyan]\n")

    # Show aggregate rankings table
    table = Table(title="Aggregate Rankings", show_header=True, header_style="bold magenta")
    table.add_column("Rank", style="cyan", justify="center", width=6)
    table.add_column("Model", style="green")
    table.add_column("Avg Position", justify="center", width=12)
    table.add_column("Votes", justify="center", width=6)

    for i, entry in enumerate(aggregate, 1):
        table.add_row(
            str(i),
            entry["model"],
            f"{entry['average_rank']:.2f}",
            str(entry["rankings_count"]),
        )

    console.print(table)
    console.print()

    # Show individual evaluations (condensed)
    console.print("[dim]Individual evaluations:[/dim]\n")
    for result in results:
        model = result["model"]
        parsed = result.get("parsed_ranking", [])

        # De-anonymize the parsed ranking for display
        parsed_display = " → ".join([
            label_to_model.get(label, label).split("/")[-1]  # Just model name, not provider
            for label in parsed
        ])

        console.print(f"  [bold]{model.split('/')[-1]}[/bold]: {parsed_display}")

    console.print()


def print_stage3(result: dict) -> None:
    """Display Stage 3 results."""
    console.print("\n[bold cyan]━━━ STAGE 3: Chairman's Synthesis ━━━[/bold cyan]\n")
    console.print(Panel(
        Markdown(result["response"]),
        title=f"[bold green]Final Answer • {result['model']}[/bold green]",
        border_style="green",
        padding=(1, 2),
    ))


def print_debate_round(round_data: dict, round_num: int) -> None:
    """Display a single debate round."""
    round_type = round_data["round_type"]
    responses = round_data["responses"]

    # Color coding by round type
    type_colors = {
        "initial": "cyan",
        "critique": "yellow",
        "defense": "magenta",
    }
    color = type_colors.get(round_type, "white")

    type_labels = {
        "initial": "Initial Responses",
        "critique": "Critiques",
        "defense": "Defense & Revision",
    }
    label = type_labels.get(round_type, round_type.title())

    console.print(f"\n[bold {color}]━━━ ROUND {round_num}: {label} ━━━[/bold {color}]\n")

    for result in responses:
        model = result["model"]
        response = result["response"]
        searched = result.get("tool_calls_made")

        title = f"[bold blue]{model}[/bold blue]"
        if searched:
            title += " [dim]• searched[/dim]"

        console.print(Panel(
            Markdown(response),
            title=title,
            border_style="blue",
            padding=(1, 2),
        ))
        console.print()


def print_debate_synthesis(synthesis: dict) -> None:
    """Display chairman's debate synthesis."""
    console.print("\n[bold cyan]━━━ CHAIRMAN'S SYNTHESIS ━━━[/bold cyan]\n")
    console.print(Panel(
        Markdown(synthesis["response"]),
        title=f"[bold green]Final Answer • {synthesis['model']}[/bold green]",
        border_style="green",
        padding=(1, 2),
    ))


async def run_react_synthesis(
    user_query: str,
    context: str,
    header: str = "CHAIRMAN'S REASONING"
) -> dict:
    """
    Run ReAct synthesis with streaming display.

    Displays the reasoning trace as it streams, then shows the final synthesis.

    Args:
        user_query: Original user question
        context: Formatted context from ranking or debate mode
        header: Header text to display

    Returns:
        Dict with 'model' and 'response' keys
    """
    from backend.council import synthesize_with_react

    console.print(f"\n[bold cyan]━━━ {header} ━━━[/bold cyan]\n")

    synthesis_result = None
    current_text = ""
    terminal_width = console.width or 80

    # Track lines for clearing streaming output
    line_count = 0
    current_col = 0

    def track_output(text: str):
        """Track line count including terminal wrapping."""
        nonlocal line_count, current_col
        for char in text:
            if char == "\n":
                line_count += 1
                current_col = 0
            else:
                current_col += 1
                if current_col >= terminal_width:
                    line_count += 1
                    current_col = 0

    def clear_streaming():
        """Clear the streamed text."""
        nonlocal line_count, current_col
        if line_count > 0:
            sys.stdout.write(f"\033[{line_count}A\033[J")
            sys.stdout.flush()
        line_count = 0
        current_col = 0

    async for event in synthesize_with_react(user_query, context):
        event_type = event["type"]

        if event_type == "token":
            # Stream tokens in dim text
            token = event["content"]
            sys.stdout.write(f"\033[2m{token}\033[0m")
            sys.stdout.flush()
            track_output(token)
            current_text += token

        elif event_type == "thought":
            # After streaming completes, show formatted thought
            clear_streaming()
            thought = event["content"]
            console.print(f"[cyan]Thought:[/cyan] {thought}\n")
            current_text = ""

        elif event_type == "action":
            tool = event["tool"]
            args = event.get("args")
            if tool == "search_web":
                console.print(f"[yellow]Action:[/yellow] search_web(\"{args}\")\n")
            elif tool == "synthesize":
                console.print(f"[yellow]Action:[/yellow] synthesize()\n")

        elif event_type == "observation":
            # Show observation in dim text
            observation = event["content"]
            # Truncate long observations
            if len(observation) > 500:
                observation = observation[:500] + "..."
            console.print(f"[dim]Observation: {observation}[/dim]\n")

        elif event_type == "synthesis":
            # Clear any remaining streaming text
            clear_streaming()
            synthesis_result = {
                "model": event["model"],
                "response": event["response"]
            }

    return synthesis_result


async def run_chat_session(max_turns: int, start_new: bool) -> None:
    """Run interactive chat session with stored conversation history."""
    conversations = storage.list_conversations()
    conversation_id = None
    conversation = None
    resumed = False
    debate_enabled = True
    debate_rounds = DEFAULT_DEBATE_ROUNDS
    parallel_enabled = True
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
        parallel_enabled=parallel_enabled,
        react_enabled=react_enabled,
    )

    while True:
        try:
            user_input = console.input(
                build_chat_prompt(debate_enabled, debate_rounds, stream_enabled, parallel_enabled)
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
                        parallel_enabled=parallel_enabled,
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
                    parallel_enabled=parallel_enabled,
                    react_enabled=react_enabled,
                )
                continue
            if command == "debate":
                if argument not in ("on", "off"):
                    console.print("[chat.error]Usage: /debate on|off[/chat.error]")
                    continue
                debate_enabled = argument == "on"
                console.print(format_chat_mode_line(debate_enabled, debate_rounds, stream_enabled, parallel_enabled, react_enabled))
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
                console.print(format_chat_mode_line(debate_enabled, debate_rounds, stream_enabled, parallel_enabled, react_enabled))
                continue
            if command == "parallel":
                if argument not in ("on", "off"):
                    console.print("[chat.error]Usage: /parallel on|off[/chat.error]")
                    continue
                parallel_enabled = argument == "on"
                if parallel_enabled:
                    stream_enabled = False  # Parallel and stream are mutually exclusive
                if parallel_enabled and not debate_enabled:
                    console.print("[chat.meta]Note: Parallel only applies in debate mode.[/chat.meta]")
                console.print(format_chat_mode_line(debate_enabled, debate_rounds, stream_enabled, parallel_enabled, react_enabled))
                continue
            if command == "stream":
                if argument not in ("on", "off"):
                    console.print("[chat.error]Usage: /stream on|off[/chat.error]")
                    continue
                stream_enabled = argument == "on"
                if stream_enabled:
                    parallel_enabled = False  # Stream and parallel are mutually exclusive
                if stream_enabled and not debate_enabled:
                    console.print("[chat.meta]Note: Streaming only applies in debate mode.[/chat.meta]")
                console.print(format_chat_mode_line(debate_enabled, debate_rounds, stream_enabled, parallel_enabled, react_enabled))
                continue
            if command == "react":
                if argument not in ("on", "off"):
                    console.print("[chat.error]Usage: /react on|off[/chat.error]")
                    continue
                react_enabled = argument == "on"
                console.print(format_chat_mode_line(debate_enabled, debate_rounds, stream_enabled, parallel_enabled, react_enabled))
                continue
            if command == "mode":
                console.print(format_chat_mode_line(debate_enabled, debate_rounds, stream_enabled, parallel_enabled, react_enabled))
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

        console.print()
        console.print(Panel(
            f"[bold]{question}[/bold]",
            border_style=CHAT_BORDER_COLOR,
        ))
        console.print()

        if debate_enabled:
            # Determine if we should use ReAct (only for batch mode currently)
            use_react_here = react_enabled and not parallel_enabled and not stream_enabled

            if parallel_enabled:
                # Parallel mode - runs models in parallel with progress spinners
                debate_rounds_data, synthesis = await run_debate_parallel(
                    full_query,
                    debate_rounds,
                )
            elif stream_enabled:
                # Streaming mode - shows responses as they complete (sequential)
                debate_rounds_data, synthesis = await run_debate_streaming(
                    full_query,
                    debate_rounds,
                )
            else:
                # Batch mode - shows progress spinners
                debate_rounds_data, synthesis = await run_debate_with_progress(
                    full_query,
                    debate_rounds,
                    skip_synthesis=use_react_here,
                )

            if debate_rounds_data is None:
                console.print("[chat.error]Error: Debate mode failed to produce responses.[/chat.error]")
                continue

            # If using ReAct, run synthesis separately
            if use_react_here:
                from backend.council import build_react_context_debate
                # Show rounds first
                for round_data in debate_rounds_data:
                    print_debate_round(round_data, round_data["round_number"])
                # Run ReAct synthesis
                context = build_react_context_debate(full_query, debate_rounds_data, len(debate_rounds_data))
                synthesis = await run_react_synthesis(full_query, context)
                print_debate_synthesis(synthesis)

            storage.add_debate_message(conversation_id, debate_rounds_data, synthesis)

            if title_task:
                title = await title_task
                storage.update_conversation_title(conversation_id, title)

            if not stream_enabled and not parallel_enabled and not use_react_here:
                # Only print rounds if not streaming/parallel/react (they already displayed them)
                for round_data in debate_rounds_data:
                    print_debate_round(round_data, round_data["round_number"])
                print_debate_synthesis(synthesis)
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
                from backend.council import build_react_context_ranking
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


async def run_council_with_progress(query: str, skip_synthesis: bool = False) -> tuple:
    """Run the council with progress indicators.

    Args:
        query: The user's question
        skip_synthesis: If True, skip Stage 3 synthesis (for ReAct mode)

    Returns:
        Tuple of (stage1_results, stage2_results, stage3_result, metadata)
        If skip_synthesis=True, stage3_result will be None
    """
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        # Stage 1
        task1 = progress.add_task(
            f"[cyan]Stage 1: Querying {len(COUNCIL_MODELS)} models...",
            total=None
        )
        stage1_results = await stage1_collect_responses(query)
        progress.remove_task(task1)

        if not stage1_results:
            console.print("[red]Error: All models failed to respond.[/red]")
            return None, None, None, None

        console.print(f"[green]✓[/green] Stage 1 complete: {len(stage1_results)} responses")

        # Stage 2
        task2 = progress.add_task(
            "[cyan]Stage 2: Collecting peer rankings...",
            total=None
        )
        stage2_results, label_to_model = await stage2_collect_rankings(query, stage1_results)
        aggregate_rankings = calculate_aggregate_rankings(stage2_results, label_to_model)
        progress.remove_task(task2)

        console.print(f"[green]✓[/green] Stage 2 complete: {len(stage2_results)} rankings")

        # Stage 3 (optional)
        stage3_result = None
        if not skip_synthesis:
            task3 = progress.add_task(
                f"[cyan]Stage 3: Chairman synthesizing...",
                total=None
            )
            stage3_result = await stage3_synthesize_final(query, stage1_results, stage2_results)
            progress.remove_task(task3)

            console.print(f"[green]✓[/green] Stage 3 complete: Final answer ready")

    return stage1_results, stage2_results, stage3_result, {
        "label_to_model": label_to_model,
        "aggregate_rankings": aggregate_rankings,
    }


async def run_debate_with_progress(query: str, max_rounds: int = 2, skip_synthesis: bool = False) -> tuple:
    """Run the debate council with progress indicators."""
    from backend.council import (
        stage1_collect_responses,
        debate_round_critique,
        debate_round_defense,
        synthesize_debate,
    )

    rounds = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        # Round 1: Initial responses
        task = progress.add_task(
            f"[cyan]Round 1: Collecting initial responses from {len(COUNCIL_MODELS)} models...",
            total=None
        )
        initial_responses = await stage1_collect_responses(query)
        progress.remove_task(task)

        if len(initial_responses) < 2:
            console.print("[red]Error: Not enough models responded for debate (need at least 2).[/red]")
            return None, None

        console.print(f"[green]✓[/green] Round 1 complete: {len(initial_responses)} initial responses")

        rounds.append({
            "round_number": 1,
            "round_type": "initial",
            "responses": initial_responses
        })

        # Round 2: Critiques
        task = progress.add_task(
            "[yellow]Round 2: Models critiquing each other...",
            total=None
        )
        critique_responses = await debate_round_critique(query, initial_responses)
        progress.remove_task(task)

        console.print(f"[green]✓[/green] Round 2 complete: {len(critique_responses)} critiques")

        rounds.append({
            "round_number": 2,
            "round_type": "critique",
            "responses": critique_responses
        })

        # Round 3: Defense/Revision
        task = progress.add_task(
            "[magenta]Round 3: Models defending and revising...",
            total=None
        )
        defense_responses = await debate_round_defense(
            query,
            initial_responses,
            critique_responses
        )
        progress.remove_task(task)

        console.print(f"[green]✓[/green] Round 3 complete: {len(defense_responses)} revised responses")

        rounds.append({
            "round_number": 3,
            "round_type": "defense",
            "responses": defense_responses
        })

        # Additional rounds if requested
        current_responses = defense_responses
        for round_num in range(4, max_rounds + 2):
            if round_num % 2 == 0:
                # Even rounds: critique
                task = progress.add_task(
                    f"[yellow]Round {round_num}: Additional critiques...",
                    total=None
                )
                critique_responses = await debate_round_critique(query, current_responses)
                progress.remove_task(task)

                console.print(f"[green]✓[/green] Round {round_num} complete: {len(critique_responses)} critiques")

                rounds.append({
                    "round_number": round_num,
                    "round_type": "critique",
                    "responses": critique_responses
                })
            else:
                # Odd rounds: defense
                task = progress.add_task(
                    f"[magenta]Round {round_num}: Defense and revision...",
                    total=None
                )
                defense_responses = await debate_round_defense(
                    query,
                    current_responses,
                    critique_responses
                )
                progress.remove_task(task)

                console.print(f"[green]✓[/green] Round {round_num} complete: {len(defense_responses)} revised responses")

                rounds.append({
                    "round_number": round_num,
                    "round_type": "defense",
                    "responses": defense_responses
                })
                current_responses = defense_responses

        # Chairman synthesis (optional)
        synthesis = None
        if not skip_synthesis:
            task = progress.add_task(
                "[green]Chairman synthesizing debate...",
                total=None
            )
            synthesis = await synthesize_debate(query, rounds, len(rounds))
            progress.remove_task(task)

            console.print(f"[green]✓[/green] Chairman synthesis complete")

    return rounds, synthesis


def build_model_panel(model: str, content: str, color: str = "blue", searched: bool = False) -> Panel:
    """Build a panel with rendered markdown for a model response."""
    short_name = model.split("/")[-1]
    title = f"[bold {color}]{short_name}[/bold {color}]"
    if searched:
        title += " [dim]• searched[/dim]"
    return Panel(
        Markdown(content) if content.strip() else Text("(empty)", style="dim"),
        title=title,
        border_style=color if color else "white",
        padding=(1, 2),
    )


async def run_debate_streaming(query: str, max_rounds: int = 2) -> tuple:
    """
    Run debate with token-by-token streaming.

    Streams raw text while generating, then shows rendered markdown panel when complete.

    Returns:
        Tuple of (rounds list, synthesis dict)
    """
    import shutil

    type_styles = {
        "initial": ("cyan", "Initial Responses"),
        "critique": ("yellow", "Critiques"),
        "defense": ("magenta", "Defense & Revision"),
    }

    rounds_data = []
    synthesis_data = None
    current_content = ""
    current_model = ""
    line_count = 0
    current_col = 0  # Track current column position for line wrap calculation
    terminal_width = shutil.get_terminal_size().columns

    def clear_streaming_output():
        """Clear the streaming output lines to replace with panel."""
        nonlocal line_count, current_col
        if line_count > 0:
            # Move cursor up and clear lines (write directly to bypass Rich escaping)
            import sys
            sys.stdout.write(f"\033[{line_count}A\033[J")
            sys.stdout.flush()
            line_count = 0
            current_col = 0

    def track_output(text: str):
        """Track line count including terminal wrapping."""
        nonlocal line_count, current_col
        for char in text:
            if char == "\n":
                line_count += 1
                current_col = 0
            else:
                current_col += 1
                if current_col >= terminal_width:
                    line_count += 1
                    current_col = 0

    current_round_type = ""

    async for event in run_debate_token_streaming(query, max_rounds):
        event_type = event["type"]

        if event_type == "round_start":
            round_num = event["round_number"]
            current_round_type = event["round_type"]
            color, label = type_styles.get(current_round_type, ("white", current_round_type.title()))
            console.print()
            console.print(f"[bold {color}]━━━ ROUND {round_num}: {label} ━━━[/bold {color}]")
            console.print()

        elif event_type == "model_start":
            current_model = event["model"]
            current_content = ""
            line_count = 0  # Reset - track_output will count actual lines
            current_col = 0
            short_name = current_model.split("/")[-1]

            # All rounds now stream - show header for token display
            header = f"{short_name}: "
            track_output(header)
            console.print(f"[grey62]{short_name}:[/grey62] ", end="")

        elif event_type == "token":
            current_content += event["content"]
            token = event["content"]
            track_output(token)
            console.print(f"[grey62]{token}[/grey62]", end="")

        elif event_type == "tool_call":
            # Model is calling a tool (e.g., web search)
            tool_name = event.get("tool", "tool")
            # Clear current streaming output and show search indicator
            console.print()
            track_output("\n")
            clear_streaming_output()
            console.print(f"[grey62]{current_model.split('/')[-1]}: [italic]searching...[/italic][/grey62]", end="")
            line_count = 1
            current_col = 0

        elif event_type == "tool_result":
            # Tool finished, clear search indicator and resume streaming header
            console.print()
            track_output("\n")
            clear_streaming_output()
            short_name = current_model.split("/")[-1]
            header = f"{short_name}: "
            track_output(header)
            console.print(f"[grey62]{short_name}:[/grey62] ", end="")

        elif event_type == "model_complete":
            # Clear streaming output
            console.print()  # End the streaming line
            track_output("\n")
            clear_streaming_output()
            # Show rendered panel (check if model used web search)
            response_data = event.get("response", {})
            searched = bool(response_data.get("tool_calls_made"))
            console.print(build_model_panel(current_model, current_content, searched=searched))
            console.print()

        elif event_type == "model_error":
            console.print()
            clear_streaming_output()
            console.print(Panel(
                f"[bold red]Error: {event.get('error', 'Unknown')}[/bold red]",
                title=f"[bold red]{current_model.split('/')[-1]}[/bold red]",
                border_style="red",
            ))
            console.print()

        elif event_type == "round_complete":
            rounds_data.append({
                "round_number": event["round_number"],
                "round_type": event["round_type"],
                "responses": event["responses"],
            })

        elif event_type == "synthesis_start":
            console.print()
            console.print("[bold green]━━━ CHAIRMAN'S SYNTHESIS ━━━[/bold green]")
            console.print()
            current_model = CHAIRMAN_MODEL
            current_content = ""
            line_count = 0  # Reset - track_output will count actual lines
            current_col = 0
            short_name = current_model.split("/")[-1]
            header = f"{short_name}: "
            track_output(header)
            console.print(f"[grey62]{short_name}:[/grey62] ", end="")

        elif event_type == "synthesis_token":
            current_content += event["content"]
            token = event["content"]
            track_output(token)
            console.print(f"[grey62]{token}[/grey62]", end="")

        elif event_type == "synthesis_complete":
            synthesis_data = event["synthesis"]
            console.print()
            track_output("\n")
            clear_streaming_output()
            console.print(build_model_panel(current_model, current_content, "green"))
            console.print()

        elif event_type == "complete":
            rounds_data = event["rounds"]
            synthesis_data = event["synthesis"]

    return rounds_data, synthesis_data


async def run_debate_parallel(query: str, max_rounds: int = 2) -> tuple:
    """
    Run debate with parallel execution and progress spinners.

    Shows all models querying simultaneously with spinners,
    then displays panels as each model completes.
    """
    from rich.live import Live
    from rich.table import Table
    from rich.text import Text
    from rich.spinner import Spinner
    from rich.console import Group
    from backend.council import run_debate_council_streaming

    rounds_data = []
    synthesis_data = None
    current_round_type = ""
    current_round_num = 0

    # Track model status: "querying", "done", "error"
    model_status = {}
    completed_panels = []
    live_display = None

    def build_status_table() -> Table:
        """Build a table showing current status of all models."""
        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column("Model", style="bold")
        table.add_column("Status")

        for model in model_status:
            short_name = model.split("/")[-1]
            status = model_status.get(model, "waiting")

            if status == "querying":
                # Use Rich Spinner for animation
                spinner = Spinner("dots", text="querying...", style="yellow")
                table.add_row(short_name, spinner)
            elif status == "done":
                table.add_row(short_name, Text("✓ done", style="green"))
            elif status == "error":
                table.add_row(short_name, Text("✗ error", style="red"))
            else:
                table.add_row(short_name, Text("○ waiting", style="dim"))

        return table

    def print_round_header(round_num: int, round_type: str):
        """Print the round header."""
        color = {"initial": "cyan", "critique": "yellow", "defense": "magenta"}.get(
            round_type, "white"
        )
        console.print()
        console.print(f"[bold {color}]━━━ ROUND {round_num}: {round_type.upper()} ━━━[/bold {color}]")
        console.print()

    async for event in run_debate_council_streaming(query, max_rounds):
        event_type = event["type"]

        if event_type == "round_start":
            current_round_num = event["round_number"]
            current_round_type = event["round_type"]

            # Reset for new round
            model_status.clear()
            completed_panels.clear()

            # Print round header
            print_round_header(current_round_num, current_round_type)

        elif event_type == "model_start":
            model = event["model"]
            model_status[model] = "querying"
            # Start or update live display
            if live_display is None:
                live_display = Live(build_status_table(), console=console, refresh_per_second=10, transient=True)
                live_display.start()
            else:
                live_display.update(build_status_table())

        elif event_type == "model_complete":
            model = event["model"]
            response_data = event.get("response", {})
            model_status[model] = "done"
            if live_display:
                live_display.update(build_status_table())

            # Check if model used web search
            searched = bool(response_data.get("tool_calls_made"))
            content = response_data.get("response", "")
            panel = build_model_panel(model, content, color="", searched=searched)
            completed_panels.append(panel)

        elif event_type == "model_error":
            model = event["model"]
            error = event.get("error", "Unknown error")
            model_status[model] = "error"
            if live_display:
                live_display.update(build_status_table())

            panel = Panel(
                f"[red]Error: {error}[/red]",
                title=f"[bold red]{model.split('/')[-1]}[/bold red]",
                border_style="red",
            )
            completed_panels.append(panel)

        elif event_type == "round_complete":
            # Stop live display (transient=True clears it)
            if live_display:
                live_display.stop()
                live_display = None

            # Print all completed panels
            for panel in completed_panels:
                console.print(panel)
                console.print()

            responses = event.get("responses", [])
            rounds_data.append({
                "round_number": current_round_num,
                "round_type": current_round_type,
                "responses": responses,
            })

        elif event_type == "synthesis_start":
            console.print()
            console.print("[bold green]━━━ CHAIRMAN'S SYNTHESIS ━━━[/bold green]")
            console.print()

            # Show spinner for chairman
            model_status.clear()
            model_status[CHAIRMAN_MODEL] = "querying"
            live_display = Live(build_status_table(), console=console, refresh_per_second=10, transient=True)
            live_display.start()

        elif event_type == "synthesis_complete":
            synthesis_data = event["synthesis"]

            # Stop live display (transient=True clears it)
            if live_display:
                live_display.stop()
                live_display = None

            content = synthesis_data.get("response", "")
            console.print(build_model_panel(CHAIRMAN_MODEL, content, "green"))
            console.print()

        elif event_type == "complete":
            # Ensure live display is stopped
            if live_display:
                live_display.stop()
                live_display = None
            rounds_data = event.get("rounds", rounds_data)
            synthesis_data = event.get("synthesis", synthesis_data)

    return rounds_data, synthesis_data


@app.command()
def chat(
    max_turns: int = typer.Option(
        DEFAULT_CONTEXT_TURNS,
        "--max-turns",
        "-t",
        help="Number of recent exchanges to include (plus the first exchange).",
    ),
    new: bool = typer.Option(
        False,
        "--new",
        help="Start a new conversation instead of resuming the latest.",
    ),
):
    """
    Start an interactive chat session with conversation history.
    """
    asyncio.run(run_chat_session(max_turns=max_turns, start_new=new))


@app.command()
def query(
    question: Optional[str] = typer.Argument(
        None,
        help="The question to ask the council",
    ),
    simple: bool = typer.Option(
        False,
        "--simple", "-s",
        help="Simple output mode (just the final answer)",
    ),
    final_only: bool = typer.Option(
        False,
        "--final-only", "-f",
        help="Show only the final answer (skip stages 1 & 2)",
    ),
    debate: bool = typer.Option(
        False,
        "--debate", "-d",
        help="Enable debate mode (models critique and defend positions)",
    ),
    rounds: int = typer.Option(
        2,
        "--rounds", "-r",
        help="Number of debate rounds (default: 2 = initial + critique + defense)",
    ),
    stream: bool = typer.Option(
        False,
        "--stream",
        help="Stream token-by-token (sequential, debate mode only)",
    ),
    parallel: bool = typer.Option(
        False,
        "--parallel", "-p",
        help="Run models in parallel with progress spinners (debate mode only)",
    ),
    no_react: bool = typer.Option(
        False,
        "--no-react",
        help="Disable ReAct reasoning for chairman (skips reasoning trace)",
    ),
):
    """
    Query the LLM Council with a question.

    By default, the chairman uses ReAct reasoning to verify facts before synthesis.
    Use --no-react to disable this behavior.

    Examples:
        llm-council "What is the best programming language?"
        llm-council -s "Quick question"
        llm-council -f "Just give me the answer"
        llm-council --debate "Complex question"
        llm-council --debate --rounds 3 "Very complex question"
        llm-council --no-react "Skip reasoning trace"
        llm-council --debate --stream "Watch responses stream token-by-token"
        llm-council --debate --parallel "Watch models query in parallel"
    """
    if not question:
        question = typer.prompt("Enter your question")

    console.print()
    console.print(Panel(
        f"[bold]{question}[/bold]",
        title="Query",
        border_style="white",
    ))
    console.print()
    console.print(f"[dim]Council: {', '.join([m.split('/')[-1] for m in COUNCIL_MODELS])}[/dim]")
    console.print(f"[dim]Chairman: {CHAIRMAN_MODEL.split('/')[-1]}[/dim]")
    mode_parts = []
    if debate:
        mode_parts.append(f"Debate ({rounds} rounds)")
        if stream:
            mode_parts.append("[streaming]")
        elif parallel:
            mode_parts.append("[parallel]")
    else:
        mode_parts.append("Ranking")
    if not no_react:
        mode_parts.append("[react]")
    console.print(f"[dim]Mode: {' '.join(mode_parts)}[/dim]")
    console.print()

    if debate:
        # Run debate mode
        use_react = not no_react

        if stream:
            # Streaming mode - shows responses token-by-token (sequential)
            # TODO: Add ReAct support for streaming mode
            debate_rounds, synthesis = asyncio.run(run_debate_streaming(question, rounds))
        elif parallel:
            # Parallel mode - runs models in parallel with progress spinners
            # TODO: Add ReAct support for parallel mode
            debate_rounds, synthesis = asyncio.run(run_debate_parallel(question, rounds))
        else:
            # Batch mode - shows single progress spinner per round
            debate_rounds, synthesis = asyncio.run(
                run_debate_with_progress(question, rounds, skip_synthesis=use_react)
            )

        if debate_rounds is None:
            raise typer.Exit(1)

        # If ReAct enabled, run ReAct synthesis separately
        if use_react and not stream and not parallel:
            from backend.council import build_react_context_debate
            context = build_react_context_debate(question, debate_rounds, len(debate_rounds))

            if not simple and not final_only:
                # Show all debate rounds first
                for round_data in debate_rounds:
                    print_debate_round(round_data, round_data["round_number"])

            # Run ReAct synthesis
            synthesis = asyncio.run(run_react_synthesis(question, context))

            if simple:
                console.print()
                console.print(Markdown(synthesis["response"]))
            else:
                print_debate_synthesis(synthesis)
        elif stream or parallel:
            # Streaming/parallel mode already displayed everything via Live
            pass
        elif simple:
            # Just print the final answer as plain text
            console.print()
            console.print(Markdown(synthesis["response"]))
        elif final_only:
            print_debate_synthesis(synthesis)
        else:
            # Show all debate rounds
            for round_data in debate_rounds:
                print_debate_round(round_data, round_data["round_number"])
            print_debate_synthesis(synthesis)
    else:
        # Run standard council mode
        use_react = not no_react
        stage1, stage2, stage3, metadata = asyncio.run(
            run_council_with_progress(question, skip_synthesis=use_react)
        )

        if stage1 is None:
            raise typer.Exit(1)

        # If ReAct enabled, run ReAct synthesis separately
        if use_react:
            from backend.council import build_react_context_ranking
            context = build_react_context_ranking(question, stage1, stage2)

            if not simple and not final_only:
                # Show Stage 1 and 2 first
                print_stage1(stage1)
                print_stage2(stage2, metadata["label_to_model"], metadata["aggregate_rankings"])

            # Run ReAct synthesis
            stage3 = asyncio.run(run_react_synthesis(question, context))

            if simple:
                console.print()
                console.print(Markdown(stage3["response"]))
            else:
                print_stage3(stage3)
        elif simple:
            # Just print the final answer as plain text
            console.print()
            console.print(Markdown(stage3["response"]))
        elif final_only:
            print_stage3(stage3)
        else:
            print_stage1(stage1)
            print_stage2(stage2, metadata["label_to_model"], metadata["aggregate_rankings"])
            print_stage3(stage3)


@app.command()
def models():
    """Show the current council configuration."""
    console.print()
    table = Table(title="LLM Council Configuration", show_header=True, header_style="bold cyan")
    table.add_column("Role", style="dim", width=10)
    table.add_column("Model", style="green")

    for model in COUNCIL_MODELS:
        table.add_row("Member", model)

    table.add_row(
        "[bold yellow]Chairman[/bold yellow]",
        f"[bold yellow]{CHAIRMAN_MODEL}[/bold yellow]"
    )

    console.print(table)
    console.print()


@app.command()
def interactive(
    question: Optional[str] = typer.Argument(
        None,
        help="Optional initial question to ask",
    ),
):
    """
    Launch interactive TUI mode.

    Examples:
        llm-council interactive
        llm-council interactive "Start with this question"
    """
    from cli.tui import run_tui
    run_tui(query=question)


def main():
    """Entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()
