"""Render optional compact CSV summary tables from a compiled record dict."""
from __future__ import annotations

import csv
import io
from typing import Any


def _write_csv(headers: list[str], rows: list[list[Any]]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(headers)
    for row in rows:
        writer.writerow(["" if v is None else v for v in row])
    return buffer.getvalue()


def render_csv_tables(record: dict[str, Any]) -> dict[str, str]:
    """Return {table_name: csv_text} for each optional compact summary table."""
    tables: dict[str, str] = {}

    prs = record["pr_state"]["pull_requests"]
    tables["pr_state.csv"] = _write_csv(
        ["pr_number", "merge_status", "status_category", "ci_status", "superseded_by_pr", "duplicate_of_pr"],
        [[p["pr_number"], p["merge_status"], p["status_category"], p["ci_status"], p["superseded_by_pr"], p["duplicate_of_pr"]] for p in prs],
    )

    contributions = record["agent_contribution_table"]["contributions"]
    tables["agent_contributions.csv"] = _write_csv(
        ["id", "agent", "pr_number", "merge_status", "claim_class"],
        [[c["id"], c["agent"], c["pr_number"], c["merge_status"], c["research_classification"]["claim_class"]] for c in contributions],
    )

    falsification = record["falsification_semantics"]["results"]
    tables["falsification_results.csv"] = _write_csv(
        ["hypothesis_id", "claim_class", "metric_type", "metric_value", "verdict"],
        [[f["hypothesis_id"], f["claim_class"], f["metric_type"], f["metric_value"], f["verdict"]] for f in falsification],
    )

    topology = record["topology_readiness"]["checks"]
    tables["topology_readiness.csv"] = _write_csv(
        ["name", "metric_family", "data_mode", "metric_value", "verdict"],
        [[c["name"], c["metric_family"], c["data_mode"], c["metric_value"], c["verdict"]] for c in topology],
    )

    cohorts = record["cohort_readiness"]["cohorts"]
    tables["cohort_readiness.csv"] = _write_csv(
        ["cohort_id", "n_subjects", "n_required", "paired", "data_mode", "ready"],
        [[c["cohort_id"], c["n_subjects"], c["n_required"], c["paired"], c["data_mode"], c["ready"]] for c in cohorts],
    )

    return tables
