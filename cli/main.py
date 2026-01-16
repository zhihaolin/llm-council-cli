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
        console.print(Panel(
            Markdown(response),
            title=f"[bold blue]{model}[/bold blue]",
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
):
    """
    Query the LLM Council with a question.

    Examples:
        llm-council "What is the best programming language?"
        llm-council -s "Quick question"
        llm-council -f "Just give me the answer"
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
    console.print()

    # Run the council
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


def main():
    """Entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()
