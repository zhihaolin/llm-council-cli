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
    print_debate_synthesis,
    print_query_header,
    print_stage1,
    print_stage2,
    print_stage3,
)
from llm_council.cli.runners import (
    run_council_with_progress,
    run_debate_parallel,
    run_debate_streaming,
    run_debate_with_progress,
    run_react_synthesis,
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
        2,
        "--rounds",
        "-r",
        help="Number of debate rounds (default: 2 = initial + critique + defense)",
    ),
    stream: bool = typer.Option(
        False,
        "--stream",
        help="Stream token-by-token (sequential, debate mode only)",
    ),
    parallel: bool = typer.Option(
        False,
        "--parallel",
        "-p",
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

    print_query_header(
        question, COUNCIL_MODELS, CHAIRMAN_MODEL, debate, rounds, stream, parallel, not no_react
    )

    if debate:
        # Run debate mode
        use_react = not no_react

        if stream:
            # Streaming mode - shows responses token-by-token (sequential)
            debate_rounds, synthesis = asyncio.run(run_debate_streaming(question, rounds))
        elif parallel:
            # Parallel mode - runs models in parallel with progress spinners
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
            from llm_council.engine import build_react_context_debate

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
            from llm_council.engine import build_react_context_ranking

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
        "[bold yellow]Chairman[/bold yellow]", f"[bold yellow]{CHAIRMAN_MODEL}[/bold yellow]"
    )

    console.print(table)
    console.print()


@app.command()
def interactive(
    question: str | None = typer.Argument(
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
    from llm_council.cli.tui import run_tui

    run_tui(query=question)


def main():
    """Entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()
