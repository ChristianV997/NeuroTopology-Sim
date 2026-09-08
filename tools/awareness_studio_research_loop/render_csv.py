"""Optional compact CSV summary tables."""
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
    tables: dict[str, str] = {}

    ledger = report["artifact_ledger"]
    tables["artifact_ledger.csv"] = _write_csv(
        ["experiment_id", "hypothesis_id", "scientific_status", "reviewer_status", "dependency_state"],
        [[r["experiment_id"], r["hypothesis_id"], r["scientific_status"], r["reviewer_status"], r["dependency_state"]] for r in ledger],
    )

    states = report["cycle_states"]
    tables["cycle_states.csv"] = _write_csv(
        ["hypothesis_id", "state"],
        [[hyp_id, entry["state"]] for hyp_id, entry in sorted(states.items())],
    )

    return tables
