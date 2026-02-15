#!/usr/bin/env python3
"""
LLM Council CLI - Query multiple LLMs and synthesize their responses.

Usage:
    llm-council "Your question here"
    llm-council --simple "Quick question"
    llm-council models
"""

import asyncio

import typer
from rich.markdown import Markdown
from rich.table import Table

from llm_council.cli.constants import DEFAULT_CONTEXT_TURNS
from llm_council.cli.presenters import (
    console,
    print_debate_round,
    print_query_header,
    print_stage1,
    print_stage2,
)
from llm_council.cli.runners import (
    run_council_with_progress,
    run_debate_parallel,
    run_debate_streaming,
    run_reflection_synthesis,
)
from llm_council.settings import CHAIRMAN_MODEL, COUNCIL_MODELS

app = typer.Typer(
    name="llm-council",
    help="Query multiple LLMs and get a synthesized council response.",
    add_completion=False,
    no_args_is_help=True,
)


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
    from llm_council.cli.chat_session import run_chat_session

    asyncio.run(run_chat_session(max_turns=max_turns, start_new=new))


@app.command()
def query(
    question: str | None = typer.Argument(
        None,
        help="The question to ask the council",
    ),
    simple: bool = typer.Option(
        False,
        "--simple",
        "-s",
        help="Simple output mode (just the final answer)",
    ),
    final_only: bool = typer.Option(
        False,
        "--final-only",
        "-f",
        help="Show only the final answer (skip stages 1 & 2)",
    ),
    debate: bool = typer.Option(
        False,
        "--debate",
        "-d",
        help="Enable debate mode (models critique and defend positions)",
    ),
    rounds: int = typer.Option(
        1,
        "--rounds",
        "-r",
        help="Number of critique-defense cycles (default: 1 = initial + critique + defense)",
    ),
    stream: bool = typer.Option(
        False,
        "--stream",
        help="Stream token-by-token (sequential, debate mode only)",
    ),
    no_react: bool = typer.Option(
        False,
        "--no-react",
        help="Disable ReAct reasoning for council members (use native function calling)",
    ),
):
    """
    Query the LLM Council with a question.

    The chairman always uses Reflection to deeply analyse responses.
    Council members use ReAct reasoning by default (--no-react disables it).

    Examples:
        llm-council "What is the best programming language?"
        llm-council -s "Quick question"
        llm-council -f "Just give me the answer"
        llm-council --debate "Complex question"
        llm-council --debate --rounds 3 "Very complex question"
        llm-council --no-react "Use native function calling for council"
        llm-council --debate --stream "Watch responses stream token-by-token"
    """
    if not question:
        question = typer.prompt("Enter your question")

    use_react = not no_react

    print_query_header(question, COUNCIL_MODELS, CHAIRMAN_MODEL, debate, rounds, stream, use_react)

    if debate:
        # Run debate mode (rounds only — synthesis always via Reflection)
        if stream:
            debate_rounds, _ = asyncio.run(run_debate_streaming(question, rounds))
        else:
            debate_rounds, _ = asyncio.run(run_debate_parallel(question, rounds))

        if debate_rounds is None:
            raise typer.Exit(1)

        # Show debate rounds (unless simple/final-only)
        if not simple and not final_only:
            for round_data in debate_rounds:
                print_debate_round(round_data, round_data["round_number"])

        # Always run Reflection synthesis for chairman
        from llm_council.engine import build_react_context_debate

        context = build_react_context_debate(question, debate_rounds, len(debate_rounds))
        synthesis = asyncio.run(run_reflection_synthesis(question, context))

        if simple:
            console.print()
            console.print(Markdown(synthesis["response"]))

    else:
        # Run standard council mode (Stages 1-2 only — synthesis always via Reflection)
        stage1, stage2, metadata = asyncio.run(run_council_with_progress(question))

        if stage1 is None:
            raise typer.Exit(1)

        # Show Stage 1 and 2 (unless simple/final-only)
        if not simple and not final_only:
            print_stage1(stage1)
            print_stage2(stage2, metadata["label_to_model"], metadata["aggregate_rankings"])

        # Always run Reflection synthesis for chairman
        from llm_council.engine import build_react_context_ranking

        context = build_react_context_ranking(question, stage1, stage2)
        stage3 = asyncio.run(run_reflection_synthesis(question, context))

        if simple:
            console.print()
            console.print(Markdown(stage3["response"]))


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
        "[bold yellow]Chairman[/bold yellow]", f"[bold yellow]{CHAIRMAN_MODEL}[/bold yellow]"
    )

    console.print(table)
    console.print()


def main():
    """Entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()
