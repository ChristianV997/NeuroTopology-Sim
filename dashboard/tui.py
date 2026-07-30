"""Textual terminal command center for the autonomous orchestrator.

Four panels: running jobs (Obsidian vault Experiments/Running), last 5
completed results (DataTable), Ollama status, and today's AWS spend.
Auto-refreshes every 30 seconds. Run with: python -m dashboard.tui
"""
from datetime import datetime
from pathlib import Path

import httpx
from textual.app import App, ComposeResult
from textual.widgets import DataTable, Footer, Header, Static

from memory.vault_writer import VAULT_ROOT, _parse_frontmatter

try:
    from config.aws_config import REGION, RESULTS_BUCKET
except ImportError:
    REGION, RESULTS_BUCKET = "us-east-1", "neurotopology-results-XXXXX"


class NeuroTopologyDashboard(App):
    CSS = """
    Screen { layout: grid; grid-size: 2; }
    #jobs { height: 50%; border: solid $accent; padding: 1; }
    #results { height: 50%; }
    #ollama { height: 50%; border: solid $accent; padding: 1; }
    #spend { height: 50%; border: solid $accent; padding: 1; }
    """
    BINDINGS = [("q", "quit", "Quit"), ("r", "refresh", "Refresh")]

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(id="jobs")
        yield Static(id="ollama")
        yield DataTable(id="results")
        yield Static(id="spend")
        yield Footer()

    def on_mount(self):
        self.set_interval(30, self.refresh_data)
        self.refresh_data()

    def action_refresh(self):
        self.refresh_data()

    def refresh_data(self):
        self._refresh_jobs()
        self._refresh_results()
        self._refresh_ollama()
        self._refresh_spend()

    def _refresh_jobs(self):
        running_dir = VAULT_ROOT / "Experiments" / "Running"
        running = list(running_dir.glob("*.md")) if running_dir.exists() else []
        self.query_one("#jobs", Static).update(
            "[bold]Running Jobs[/bold]\n"
            + ("\n".join(f"- {f.stem}" for f in running) or "None")
        )

    def _refresh_results(self):
        completed_dir = VAULT_ROOT / "Experiments" / "Completed"
        completed = (
            sorted(completed_dir.glob("*.md"), key=lambda f: f.stat().st_mtime, reverse=True)[:5]
            if completed_dir.exists()
            else []
        )
        table = self.query_one("#results", DataTable)
        table.clear(columns=True)
        table.add_columns("Experiment", "eta_sq", "p", "Date")
        for note in completed:
            lines = note.read_text(encoding="utf-8").splitlines()
            meta = _parse_frontmatter(lines)
            table.add_row(
                str(meta.get("name", note.stem)),
                str(meta.get("eta_sq", "?")),
                str(meta.get("p_value", "?")),
                str(meta.get("date", "?"))[:10],
            )

    def _refresh_ollama(self):
        try:
            httpx.get("http://localhost:11434/api/tags", timeout=2).raise_for_status()
            status = "Online"
        except Exception:
            status = "Offline"
        self.query_one("#ollama", Static).update(f"[bold]Ollama[/bold]\n{status}")

    def _refresh_spend(self):
        try:
            import boto3

            ce = boto3.client("ce", region_name=REGION)
            today = datetime.now().strftime("%Y-%m-%d")
            resp = ce.get_cost_and_usage(
                TimePeriod={"Start": today, "End": today},
                Granularity="DAILY",
                Metrics=["UnblendedCost"],
            )
            spend = resp["ResultsByTime"][0]["Total"]["UnblendedCost"]["Amount"]
            self.query_one("#spend", Static).update(f"[bold]AWS Spend Today[/bold]\n${float(spend):.2f}")
        except Exception:
            self.query_one("#spend", Static).update("[bold]AWS Spend[/bold]\nUnavailable")


if __name__ == "__main__":
    NeuroTopologyDashboard().run()
