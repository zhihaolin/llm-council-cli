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
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich.markdown import Markdown

# Import council logic from backend
sys.path.insert(0, str(__file__).rsplit("/", 2)[0])  # Add project root to path
from backend.council import (
    stage1_collect_responses,
    stage2_collect_rankings,
    stage3_synthesize_final,
    calculate_aggregate_rankings,
    run_debate_council,
)
from backend.config import COUNCIL_MODELS, CHAIRMAN_MODEL

app = typer.Typer(
    name="llm-council",
    help="Query multiple LLMs and get a synthesized council response.",
    add_completion=False,
    no_args_is_help=True,
)
console = Console()


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
    console.print("\n[bold cyan]━━━ CHAIRMAN'S DEBATE SYNTHESIS ━━━[/bold cyan]\n")
    console.print(Panel(
        Markdown(synthesis["response"]),
        title=f"[bold green]Final Answer • {synthesis['model']}[/bold green]",
        border_style="green",
        padding=(1, 2),
    ))


async def run_council_with_progress(query: str) -> tuple:
    """Run the council with progress indicators."""
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

        # Stage 3
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


async def run_debate_with_progress(query: str, max_rounds: int = 2) -> tuple:
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

        # Chairman synthesis
        task = progress.add_task(
            "[green]Chairman synthesizing debate...",
            total=None
        )
        synthesis = await synthesize_debate(query, rounds, len(rounds))
        progress.remove_task(task)

        console.print(f"[green]✓[/green] Chairman synthesis complete")

    return rounds, synthesis


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
):
    """
    Query the LLM Council with a question.

    Examples:
        llm-council "What is the best programming language?"
        llm-council -s "Quick question"
        llm-council -f "Just give me the answer"
        llm-council --debate "Complex question"
        llm-council --debate --rounds 3 "Very complex question"
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
    if debate:
        console.print(f"[dim]Mode: Debate ({rounds} rounds)[/dim]")
    console.print()

    if debate:
        # Run debate mode
        debate_rounds, synthesis = asyncio.run(run_debate_with_progress(question, rounds))

        if debate_rounds is None:
            raise typer.Exit(1)

        if simple:
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
        stage1, stage2, stage3, metadata = asyncio.run(run_council_with_progress(question))

        if stage1 is None:
            raise typer.Exit(1)

        if simple:
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
