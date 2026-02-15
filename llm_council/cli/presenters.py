"""
Presentation functions for CLI output.

All print_* and display functions for Rich console output.
"""

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.theme import Theme

from llm_council.cli.chat_commands import (
    CHAT_COMMANDS,
    format_chat_mode_line,
    suggest_chat_commands,
)

CHAT_THEME = Theme(
    {
        "chat.accent": "bold #5B8DEF",
        "chat.prompt": "bold #5B8DEF",
        "chat.meta": "dim",
        "chat.command": "#E0B15A",
        "chat.success": "green",
        "chat.error": "bold red",
    }
)

CHAT_BORDER_COLOR = "#5B8DEF"

# Shared console instance with chat theme
console = Console(theme=CHAT_THEME)


def print_chat_banner(
    title: str,
    conversation_id: str,
    resumed: bool,
    debate_enabled: bool,
    debate_rounds: int,
    stream_enabled: bool = False,
    react_enabled: bool = True,
) -> None:
    """Show chat banner with conversation details."""
    short_id = conversation_id[:8]
    status = "Resumed" if resumed else "Started"
    body = (
        f"[chat.meta]{status} conversation[/chat.meta]\n"
        f"[chat.accent]{title}[/chat.accent]\n"
        f"[chat.meta]ID: {short_id}[/chat.meta]\n"
        f"{format_chat_mode_line(debate_enabled, debate_rounds, stream_enabled, react_enabled=react_enabled)}"
    )
    console.print()
    console.print(
        Panel(
            body,
            title="[chat.accent]Council Chat[/chat.accent]",
            border_style=CHAT_BORDER_COLOR,
            padding=(1, 2),
        )
    )
    console.print(
        "[chat.meta]Commands: /help, /history, /use <id>, /new, /debate, /rounds, /stream, /react, /mode, /exit[/chat.meta]"
    )
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
    console.print("[chat.command]/react on|off[/chat.command] Toggle ReAct reasoning")
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
        console.print(
            Panel(
                Markdown(response),
                title=title,
                border_style="blue",
                padding=(1, 2),
            )
        )
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
        parsed_display = " → ".join(
            [
                label_to_model.get(label, label).split("/")[-1]  # Just model name, not provider
                for label in parsed
            ]
        )

        console.print(f"  [bold]{model.split('/')[-1]}[/bold]: {parsed_display}")

    console.print()


def print_stage3(result: dict) -> None:
    """Display Stage 3 results."""
    console.print("\n[bold cyan]━━━ STAGE 3: Chairman's Synthesis ━━━[/bold cyan]\n")
    console.print(
        Panel(
            Markdown(result["response"]),
            title=f"[bold green]Final Answer • {result['model']}[/bold green]",
            border_style="green",
            padding=(1, 2),
        )
    )


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

        console.print(
            Panel(
                Markdown(response),
                title=title,
                border_style="blue",
                padding=(1, 2),
            )
        )
        console.print()


def print_debate_synthesis(synthesis: dict) -> None:
    """Display chairman's debate synthesis."""
    console.print("\n[bold cyan]━━━ CHAIRMAN'S SYNTHESIS ━━━[/bold cyan]\n")
    console.print(
        Panel(
            Markdown(synthesis["response"]),
            title=f"[bold green]Final Answer • {synthesis['model']}[/bold green]",
            border_style="green",
            padding=(1, 2),
        )
    )


def build_model_panel(
    model: str, content: str, color: str = "blue", searched: bool = False
) -> Panel:
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


def print_query_header(
    question: str,
    council_models: list,
    chairman_model: str,
    debate: bool,
    rounds: int,
    stream: bool,
    react: bool,
) -> None:
    """Print the query header with mode information."""
    console.print()
    console.print(
        Panel(
            f"[bold]{question}[/bold]",
            title="Query",
            border_style="white",
        )
    )
    console.print()
    console.print(f"[dim]Council: {', '.join([m.split('/')[-1] for m in council_models])}[/dim]")
    console.print(f"[dim]Chairman: {chairman_model.split('/')[-1]}[/dim]")
    mode_parts = []
    if debate:
        mode_parts.append(f"Debate ({rounds} rounds)")
        if stream:
            mode_parts.append("[streaming]")
    else:
        mode_parts.append("Ranking")
    if react:
        mode_parts.append("[react]")
    console.print(f"[dim]Mode: {' '.join(mode_parts)}[/dim]")
    console.print()


def print_user_question_panel(question: str) -> None:
    """Print a user question panel."""
    console.print()
    console.print(
        Panel(
            f"[bold]{question}[/bold]",
            border_style=CHAT_BORDER_COLOR,
        )
    )
    console.print()


def print_error(message: str) -> None:
    """Print an error message."""
    console.print(f"[chat.error]{message}[/chat.error]")


def print_meta(message: str) -> None:
    """Print a meta message."""
    console.print(f"[chat.meta]{message}[/chat.meta]")


def print_success(message: str) -> None:
    """Print a success message."""
    console.print(f"[green]✓[/green] {message}")
