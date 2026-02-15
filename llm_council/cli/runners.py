"""
CLI runners for council and debate execution.

Contains run_* functions that wrap backend logic with CLI presentation
(progress indicators, spinners, Rich panels).
"""

import functools
import shutil
import sys

from rich.live import Live
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text

from llm_council.cli.presenters import build_model_panel, console
from llm_council.engine import (
    calculate_aggregate_rankings,
    stage1_collect_responses,
    stage2_collect_rankings,
    synthesize_with_react,
    synthesize_with_reflection,
)
from llm_council.engine.debate import debate_round_parallel as _debate_round_parallel
from llm_council.engine.debate import debate_round_streaming as _debate_round_streaming
from llm_council.engine.debate import run_debate as _run_debate
from llm_council.settings import CHAIRMAN_MODEL, COUNCIL_MODELS


async def run_react_synthesis(
    user_query: str, context: str, header: str = "CHAIRMAN'S REASONING"
) -> dict:
    """
    Run ReAct synthesis with streaming display.

    Shows the reasoning trace (thought/action/observation) without streaming,
    then streams the final synthesis content.

    Args:
        user_query: Original user question
        context: Formatted context from ranking or debate mode
        header: Header text to display

    Returns:
        Dict with 'model' and 'response' keys
    """
    console.print(f"\n[bold cyan]━━━ {header} ━━━[/bold cyan]\n")

    synthesis_result = None
    in_synthesis_streaming = False

    async for event in synthesize_with_react(user_query, context):
        event_type = event["type"]

        if event_type == "token":
            # Only stream tokens during synthesis phase (after empty synthesize())
            if in_synthesis_streaming:
                token = event["content"]
                sys.stdout.write(f"\033[2m{token}\033[0m")
                sys.stdout.flush()

        elif event_type == "thought":
            thought = event["content"]
            console.print(f"[cyan]Thought:[/cyan] {thought}\n")

        elif event_type == "action":
            tool = event["tool"]
            args = event.get("args")
            if tool == "search_web":
                console.print(f'[yellow]Action:[/yellow] search_web("{args}")\n')
            elif tool == "synthesize":
                console.print("[yellow]Action:[/yellow] synthesize()\n")
                # Next tokens will be synthesis content
                in_synthesis_streaming = True

        elif event_type == "observation":
            observation = event["content"]
            # Truncate long observations
            if len(observation) > 500:
                observation = observation[:500] + "..."
            console.print(f"[dim]Observation: {observation}[/dim]\n")

        elif event_type == "synthesis":
            if in_synthesis_streaming:
                # Add newline after streaming
                console.print()
            synthesis_result = {"model": event["model"], "response": event["response"]}

    return synthesis_result


async def run_reflection_synthesis(user_query: str, context: str) -> dict:
    """
    Run Reflection synthesis with streaming display.

    Streams all tokens dimmed, then shows the chairman's analysis and
    final synthesis as rendered panels.

    Args:
        user_query: Original user question
        context: Formatted context from ranking or debate mode

    Returns:
        Dict with 'model' and 'response' keys
    """
    terminal_width = shutil.get_terminal_size().columns
    line_count = 0
    current_col = 0

    def track_output(text: str):
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

    def clear_streaming_output():
        nonlocal line_count, current_col
        if line_count > 0:
            sys.stdout.write(f"\033[{line_count}A\033[J")
            sys.stdout.flush()
            line_count = 0
            current_col = 0

    console.print()
    console.print("[bold green]━━━ CHAIRMAN'S ANALYSIS ━━━[/bold green]")
    console.print()

    short_name = CHAIRMAN_MODEL.split("/")[-1]
    header = f"{short_name}: "
    track_output(header)
    console.print(f"[grey62]{short_name}:[/grey62] ", end="")

    synthesis_result = None

    async for event in synthesize_with_reflection(user_query, context):
        event_type = event["type"]

        if event_type == "token":
            token = event["content"]
            track_output(token)
            console.print(f"[grey62]{token}[/grey62]", end="")

        elif event_type == "reflection":
            # Clear streaming output and show reflection panel
            console.print()
            track_output("\n")
            clear_streaming_output()

            reflection_text = event["content"]
            if reflection_text:
                from rich.markdown import Markdown

                console.print(
                    Panel(
                        Markdown(reflection_text),
                        title=f"[bold cyan]Analysis • {short_name}[/bold cyan]",
                        border_style="cyan",
                        padding=(1, 2),
                    )
                )
                console.print()

        elif event_type == "synthesis":
            synthesis_result = {"model": event["model"], "response": event["response"]}

    # Display the synthesis panel
    if synthesis_result:
        from rich.markdown import Markdown

        console.print(
            Panel(
                Markdown(synthesis_result["response"]),
                title=f"[bold green]Final Answer • {synthesis_result['model']}[/bold green]",
                border_style="green",
                padding=(1, 2),
            )
        )

    return synthesis_result


async def run_council_with_progress(query: str) -> tuple:
    """Run the council with progress indicators (Stages 1-2 only).

    Synthesis is always handled separately via Reflection.

    Args:
        query: The user's question

    Returns:
        Tuple of (stage1_results, stage2_results, metadata)
    """
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        # Stage 1
        task1 = progress.add_task(
            f"[cyan]Stage 1: Querying {len(COUNCIL_MODELS)} models...", total=None
        )
        stage1_results = await stage1_collect_responses(query)
        progress.remove_task(task1)

        if not stage1_results:
            console.print("[red]Error: All models failed to respond.[/red]")
            return None, None, None

        console.print(f"[green]✓[/green] Stage 1 complete: {len(stage1_results)} responses")

        # Stage 2
        task2 = progress.add_task("[cyan]Stage 2: Collecting peer rankings...", total=None)
        stage2_results, label_to_model = await stage2_collect_rankings(query, stage1_results)
        aggregate_rankings = calculate_aggregate_rankings(stage2_results, label_to_model)
        progress.remove_task(task2)

        console.print(f"[green]✓[/green] Stage 2 complete: {len(stage2_results)} rankings")

    return (
        stage1_results,
        stage2_results,
        {
            "label_to_model": label_to_model,
            "aggregate_rankings": aggregate_rankings,
        },
    )


async def run_debate_streaming(query: str, cycles: int = 1, react_enabled: bool = False) -> tuple:
    """
    Run debate with token-by-token streaming (rounds only, no synthesis).

    Streams raw text while generating, then shows rendered markdown panel when complete.
    Synthesis is always handled separately via Reflection.

    Args:
        query: The user's question
        cycles: Number of critique-defense cycles
        react_enabled: Whether council members use text-based ReAct reasoning

    Returns:
        Tuple of (rounds list, None)
    """
    type_styles = {
        "initial": ("cyan", "Initial Responses"),
        "critique": ("yellow", "Critiques"),
        "defense": ("magenta", "Defense & Revision"),
    }

    rounds_data = []
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

    # Build executor with react_enabled bound
    executor = functools.partial(_debate_round_streaming, react_enabled=react_enabled)

    # Run debate rounds (no synthesis — handled separately)
    async for event in _run_debate(query, executor, cycles):
        event_type = event["type"]

        if event_type == "round_start":
            round_num = event["round_number"]
            current_round_type = event["round_type"]
            color, label = type_styles.get(
                current_round_type, ("white", current_round_type.title())
            )
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
            # Clear current streaming output and show search indicator
            console.print()
            track_output("\n")
            clear_streaming_output()
            console.print(
                f"[grey62]{current_model.split('/')[-1]}: [italic]searching...[/italic][/grey62]",
                end="",
            )
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
            console.print(
                Panel(
                    f"[bold red]Error: {event.get('error', 'Unknown')}[/bold red]",
                    title=f"[bold red]{current_model.split('/')[-1]}[/bold red]",
                    border_style="red",
                )
            )
            console.print()

        elif event_type == "round_complete":
            rounds_data.append(
                {
                    "round_number": event["round_number"],
                    "round_type": event["round_type"],
                    "responses": event["responses"],
                }
            )

        elif event_type == "error":
            console.print(f"[red]Error: {event['message']}[/red]")
            return rounds_data, None

        elif event_type == "debate_complete":
            rounds_data = event["rounds"]

    return rounds_data, None


async def run_debate_parallel(query: str, cycles: int = 1, react_enabled: bool = False) -> tuple:
    """
    Run debate with parallel execution and progress spinners (rounds only, no synthesis).

    Shows all models querying simultaneously with spinners,
    then displays panels as each model completes.
    Synthesis is always handled separately via Reflection.

    Args:
        query: The user's question
        cycles: Number of critique-defense cycles
        react_enabled: Whether council members use text-based ReAct reasoning
    """
    rounds_data = []
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
                spinner = Spinner("dots", text="thinking...", style="yellow")
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
        console.print(
            f"[bold {color}]━━━ ROUND {round_num}: {round_type.upper()} ━━━[/bold {color}]"
        )
        console.print()

    # Build executor with react_enabled bound
    executor = functools.partial(_debate_round_parallel, react_enabled=react_enabled)

    # Run debate rounds (no synthesis — handled separately)
    async for event in _run_debate(query, executor, cycles):
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
                live_display = Live(
                    build_status_table(), console=console, refresh_per_second=10, transient=True
                )
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
            rounds_data.append(
                {
                    "round_number": current_round_num,
                    "round_type": current_round_type,
                    "responses": responses,
                }
            )

        elif event_type == "error":
            if live_display:
                live_display.stop()
                live_display = None
            console.print(f"[red]Error: {event['message']}[/red]")
            return rounds_data, None

        elif event_type == "debate_complete":
            rounds_data = event.get("rounds", rounds_data)

    return rounds_data, None
