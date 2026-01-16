"""
LLM Council TUI - Interactive terminal interface using Textual.
"""

import asyncio
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical, ScrollableContainer
from textual.widgets import (
    Header,
    Footer,
    Static,
    Input,
    Button,
    TabbedContent,
    TabPane,
    DataTable,
    Markdown,
    LoadingIndicator,
    Label,
)
from textual.binding import Binding
from textual import work
from textual.worker import Worker, WorkerState

import sys
sys.path.insert(0, str(__file__).rsplit("/", 2)[0])
from backend.council import (
    stage1_collect_responses,
    stage2_collect_rankings,
    stage3_synthesize_final,
    calculate_aggregate_rankings,
)
from backend.config import COUNCIL_MODELS, CHAIRMAN_MODEL


class QueryInput(Static):
    """Query input area with text field and submit button."""

    def compose(self) -> ComposeResult:
        yield Horizontal(
            Input(placeholder="Ask the council a question...", id="query-input"),
            Button("Ask", id="submit-btn", variant="primary"),
            id="input-area",
        )


class StagePanel(Static):
    """A panel for displaying stage content."""

    def __init__(self, title: str, **kwargs):
        super().__init__(**kwargs)
        self.title = title

    def compose(self) -> ComposeResult:
        yield Label(f"Waiting for query...", id=f"{self.id}-content")


class Stage1View(Static):
    """Stage 1: Individual model responses in tabs."""

    def compose(self) -> ComposeResult:
        yield Static("Submit a query to see model responses.", id="stage1-placeholder")

    def update_responses(self, results: list) -> None:
        """Update with model responses."""
        self.query_one("#stage1-placeholder").remove()

        # Create tabbed content for each model
        tabbed = TabbedContent(id="stage1-tabs")
        self.mount(tabbed)

        for result in results:
            model_name = result["model"].split("/")[-1]  # Short name
            response = result["response"]

            pane = TabPane(model_name, id=f"tab-{model_name}")
            tabbed.add_pane(pane)

            # Add markdown content to the pane
            md = Markdown(response, id=f"response-{model_name}")
            pane.mount(ScrollableContainer(md))


class Stage2View(Static):
    """Stage 2: Rankings table and evaluations."""

    def compose(self) -> ComposeResult:
        yield Static("Submit a query to see rankings.", id="stage2-placeholder")

    def update_rankings(self, results: list, label_to_model: dict, aggregate: list) -> None:
        """Update with ranking results."""
        self.query_one("#stage2-placeholder").remove()

        # Create rankings table
        table = DataTable(id="rankings-table")
        table.add_columns("Rank", "Model", "Avg Position", "Votes")

        for i, entry in enumerate(aggregate, 1):
            model_short = entry["model"].split("/")[-1]
            table.add_row(
                str(i),
                model_short,
                f"{entry['average_rank']:.2f}",
                str(entry["rankings_count"]),
            )

        self.mount(table)

        # Add individual evaluations summary
        eval_text = "\n**Individual Rankings:**\n\n"
        for result in results:
            model = result["model"].split("/")[-1]
            parsed = result.get("parsed_ranking", [])
            parsed_display = " → ".join([
                label_to_model.get(label, label).split("/")[-1]
                for label in parsed
            ])
            eval_text += f"**{model}:** {parsed_display}\n\n"

        self.mount(ScrollableContainer(Markdown(eval_text, id="evaluations")))


class Stage3View(Static):
    """Stage 3: Chairman's final synthesis."""

    def compose(self) -> ComposeResult:
        yield Static("Submit a query to see the final answer.", id="stage3-placeholder")

    def update_synthesis(self, result: dict) -> None:
        """Update with chairman's synthesis."""
        self.query_one("#stage3-placeholder").remove()

        chairman = result["model"].split("/")[-1]
        content = f"## Final Answer\n*Chairman: {chairman}*\n\n---\n\n{result['response']}"

        self.mount(ScrollableContainer(Markdown(content, id="synthesis")))


class StatusBar(Static):
    """Status bar showing current operation."""

    def compose(self) -> ComposeResult:
        yield Label("Ready", id="status-label")

    def set_status(self, message: str) -> None:
        self.query_one("#status-label").update(message)


class CouncilApp(App):
    """LLM Council TUI Application."""

    CSS = """
    #input-area {
        height: 3;
        padding: 0 1;
        background: $surface;
    }

    #query-input {
        width: 1fr;
    }

    #submit-btn {
        width: 12;
        margin-left: 1;
    }

    #main-content {
        height: 1fr;
    }

    #status-bar {
        height: 1;
        background: $primary;
        color: $text;
        padding: 0 1;
    }

    .stage-view {
        padding: 1;
    }

    #rankings-table {
        height: auto;
        max-height: 10;
        margin-bottom: 1;
    }

    DataTable {
        height: auto;
    }

    ScrollableContainer {
        height: 1fr;
    }

    LoadingIndicator {
        height: 3;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("ctrl+n", "new_query", "New Query"),
        Binding("1", "show_stage('stage1')", "Stage 1"),
        Binding("2", "show_stage('stage2')", "Stage 2"),
        Binding("3", "show_stage('stage3')", "Stage 3"),
    ]

    def __init__(self, initial_query: str = None):
        super().__init__()
        self.initial_query = initial_query

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield QueryInput(id="query-section")
        yield Container(
            TabbedContent(
                TabPane("Stage 1: Responses", Stage1View(classes="stage-view"), id="stage1"),
                TabPane("Stage 2: Rankings", Stage2View(classes="stage-view"), id="stage2"),
                TabPane("Stage 3: Final", Stage3View(classes="stage-view"), id="stage3"),
                id="stages",
            ),
            id="main-content",
        )
        yield StatusBar(id="status-bar")
        yield Footer()

    def on_mount(self) -> None:
        """Called when app is mounted."""
        self.title = "LLM Council"
        self.sub_title = f"Council: {', '.join(m.split('/')[-1] for m in COUNCIL_MODELS)}"

        # Focus the input
        self.query_one("#query-input").focus()

        # Run initial query if provided
        if self.initial_query:
            self.query_one("#query-input").value = self.initial_query
            self.run_council_query(self.initial_query)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "submit-btn":
            self.submit_query()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter key in input."""
        if event.input.id == "query-input":
            self.submit_query()

    def submit_query(self) -> None:
        """Submit the current query."""
        input_widget = self.query_one("#query-input", Input)
        query = input_widget.value.strip()

        if not query:
            return

        self.run_council_query(query)

    @work(exclusive=True)
    async def run_council_query(self, query: str) -> None:
        """Run the council query in background."""
        status_bar = self.query_one(StatusBar)
        stages = self.query_one("#stages", TabbedContent)

        # Reset views
        stage1_view = self.query_one(Stage1View)
        stage2_view = self.query_one(Stage2View)
        stage3_view = self.query_one(Stage3View)

        # Stage 1
        status_bar.set_status(f"Stage 1: Querying {len(COUNCIL_MODELS)} models...")
        stage1_results = await stage1_collect_responses(query)

        if not stage1_results:
            status_bar.set_status("Error: All models failed to respond")
            return

        stage1_view.update_responses(stage1_results)
        stages.active = "stage1"
        status_bar.set_status(f"Stage 1 complete: {len(stage1_results)} responses")

        # Brief pause to show update
        await asyncio.sleep(0.5)

        # Stage 2
        status_bar.set_status("Stage 2: Collecting peer rankings...")
        stage2_results, label_to_model = await stage2_collect_rankings(query, stage1_results)
        aggregate_rankings = calculate_aggregate_rankings(stage2_results, label_to_model)

        stage2_view.update_rankings(stage2_results, label_to_model, aggregate_rankings)
        stages.active = "stage2"
        status_bar.set_status(f"Stage 2 complete: {len(stage2_results)} rankings")

        await asyncio.sleep(0.5)

        # Stage 3
        status_bar.set_status(f"Stage 3: Chairman ({CHAIRMAN_MODEL.split('/')[-1]}) synthesizing...")
        stage3_result = await stage3_synthesize_final(query, stage1_results, stage2_results)

        stage3_view.update_synthesis(stage3_result)
        stages.active = "stage3"
        status_bar.set_status("Complete! Press Ctrl+N for new query, Q to quit")

    def action_new_query(self) -> None:
        """Focus input for new query."""
        input_widget = self.query_one("#query-input", Input)
        input_widget.value = ""
        input_widget.focus()

    def action_show_stage(self, stage: str) -> None:
        """Switch to a specific stage tab."""
        stages = self.query_one("#stages", TabbedContent)
        stages.active = stage


def run_tui(query: str = None) -> None:
    """Run the TUI application."""
    app = CouncilApp(initial_query=query)
    app.run()


if __name__ == "__main__":
    run_tui()
