"""Render optional CSV summary tables from a compiled report dict."""
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


def render_csv_tables(report: dict[str, Any]) -> dict[str, str]:
    """Return {table_name: csv_text} for each optional summary table."""
    tables: dict[str, str] = {}

    prs = report["pull_requests"]["pull_requests"]
    tables["pull_requests.csv"] = _write_csv(
        ["pr_number", "branch", "base_branch", "state", "mergeable", "ci_status", "superseded_by_pr"],
        [[p["pr_number"], p["branch"], p["base_branch"], p["state"], p["mergeable"], p["ci_status"], p["superseded_by_pr"]] for p in prs],
    )

    benchmarks = report["performance_evidence"]["benchmarks"]
    tables["performance_benchmarks.csv"] = _write_csv(
        ["name", "metric", "value", "unit", "baseline_value", "regression_pct", "status"],
        [[b["name"], b["metric"], b["value"], b["unit"], b["baseline_value"], b["regression_pct"], b["status"]] for b in benchmarks],
    )

    memory = report["memory_evidence"]["benchmarks"]
    tables["memory_evidence.csv"] = _write_csv(
        ["name", "metric", "value", "unit", "baseline_value", "regression_pct", "status"],
        [[b["name"], b["metric"], b["value"], b["unit"], b["baseline_value"], b["regression_pct"], b["status"]] for b in memory],
    )

    falsification = report["falsification_status"]["results"]
    tables["falsification_results.csv"] = _write_csv(
        ["hypothesis_id", "data_mode", "metric_type", "metric_value", "unit", "verdict", "is_formal_bayes_factor"],
        [
            [f["hypothesis_id"], f["data_mode"], f["metric_type"], f["metric_value"], f["unit"], f["verdict"], f["is_formal_bayes_factor"]]
            for f in falsification
        ],
    )

    topology = report["topology_validation_status"]["checks"]
    tables["topology_validation.csv"] = _write_csv(
        ["name", "data_mode", "Qabs", "I_mean", "verdict"],
        [[c["name"], c["data_mode"], c["Qabs"], c["I_mean"], c["verdict"]] for c in topology],
    )

    datasets = report["dataset_provenance"]["datasets"]
    tables["dataset_provenance.csv"] = _write_csv(
        ["dataset_id", "data_mode", "source", "license", "n_subjects"],
        [[d["dataset_id"], d["data_mode"], d["source"], d["license"], d["n_subjects"]] for d in datasets],
    )

    return tables
