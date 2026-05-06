"""
Hypothesis pipeline — governance-gated simulation runs.

Loads a HypothesisSpec from a YAML/JSON file, validates it against
the governance rules, executes a synthetic simulation run, and produces
a summary.json artifact.

Usage:
    python -m pipelines.hypothesis --spec governance/specs/HYP-20260506-001.yaml
    python -m pipelines.hypothesis --spec governance/specs/HYP-20260506-002.yaml --output artifacts/
"""
from __future__ import annotations

import argparse
import json
import logging
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

from governance.io import load_spec
from governance.spec import HypothesisSpec
from governance.validate import ValidationError, validate_spec

logger = logging.getLogger(__name__)

# Optional database integration — gracefully degraded if DB not requested
_DB_AVAILABLE = True
try:
    from database.database import add_artifact, add_metric, connect, finish_run, start_run
except ImportError:  # pragma: no cover
    _DB_AVAILABLE = False


# ── helpers ────────────────────────────────────────────────────────────────────

def _run_id() -> str:
    return uuid.uuid4().hex[:12]


def _now_iso() -> str:
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def _synthetic_metrics(spec: HypothesisSpec) -> Dict[str, Any]:
    """Produce a lightweight synthetic metrics dict for offline testing."""
    import numpy as np
    rng = np.random.default_rng(seed=42)
    n = 20
    q = float(rng.normal(0.0, 1.0, n).mean())
    qabs = float(abs(rng.normal(0.5, 0.2, n)).mean())
    f_dress = float(abs(rng.normal(1.0, 0.3, n)).mean())
    return {
        "Q_mean": round(q, 4),
        "Qabs_mean": round(qabs, 4),
        "f_dress_mean": round(f_dress, 4),
        "n_samples": n,
    }


def _evaluate_pass_fail(
    spec: HypothesisSpec,
    metrics: Dict[str, Any],
) -> str:
    """Return 'pass', 'fail', or 'ambiguous' based on thresholds."""
    thresholds = spec.pass_fail.thresholds
    if not thresholds:
        return "ambiguous"

    results = []
    for key, min_val in thresholds.items():
        # Support simple {"metric_name": min_value} threshold format
        metric_key = f"{key}_mean" if f"{key}_mean" in metrics else key
        if metric_key in metrics:
            results.append(metrics[metric_key] >= min_val)
    if not results:
        return "ambiguous"
    return "pass" if all(results) else "fail"


# ── public API ─────────────────────────────────────────────────────────────────

def run_hypothesis(
    spec: HypothesisSpec,
    output_dir: Optional[Path] = None,
    db_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Execute a validated hypothesis run and produce a summary.

    Args:
        spec: A fully validated HypothesisSpec.
        output_dir: Directory to write artifacts/{run_id}/ into.
                    Defaults to ./artifacts/.
        db_path: Optional SQLite DB path. If provided, run is logged.

    Returns:
        summary dict (also written to summary.json).

    Raises:
        ValidationError: if the spec fails governance rules.
    """
    # Hard governance gate — always re-validate before running
    validate_spec(spec)

    run_id = _run_id()
    output_dir = Path(output_dir or "artifacts") / run_id
    output_dir.mkdir(parents=True, exist_ok=True)

    started_at = time.time()

    # Optional DB registration
    db_run_id: Optional[int] = None
    db_conn = None
    if db_path and _DB_AVAILABLE:
        db_conn = connect(db_path)
        db_run_id = start_run(
            db_conn,
            name=spec.id,
            kind=f"hypothesis/{spec.claim_type}",
            params={
                "spec_id": spec.id,
                "claim_type": spec.claim_type,
                "layer": spec.layer,
                "run_id": run_id,
            },
        )

    # Execute metrics (synthetic stand-in; real pipelines called via data.mode)
    data_mode = spec.data.mode if spec.data else "synthetic"
    metrics: Dict[str, Any] = {}
    if data_mode == "synthetic":
        metrics = _synthetic_metrics(spec)
    else:
        logger.warning(
            "data.mode='%s' is not yet wired to live data in this prototype; "
            "using synthetic metrics stand-in.",
            data_mode,
        )
        metrics = _synthetic_metrics(spec)

    verdict = _evaluate_pass_fail(spec, metrics)

    # Write metrics.csv
    import csv
    metrics_csv = output_dir / "metrics.csv"
    with open(metrics_csv, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["metric", "value"])
        writer.writeheader()
        for k, v in metrics.items():
            writer.writerow({"metric": k, "value": v})

    # Build summary
    summary: Dict[str, Any] = {
        "spec_id": spec.id,
        "title": spec.title,
        "claim_type": spec.claim_type,
        "layer": spec.layer,
        "validation_status": "valid",
        "run_id": run_id,
        "run_ids": [run_id],
        "started_at": _now_iso(),
        "data_mode": data_mode,
        "metrics_summary": metrics,
        "verdict": verdict,
        "artifacts": {
            "metrics_csv": str(metrics_csv),
            "summary_json": str(output_dir / "summary.json"),
        },
    }

    # Write summary.json
    summary_json = output_dir / "summary.json"
    with open(summary_json, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2, ensure_ascii=False)

    # Persist metrics to DB if available
    if db_conn and db_run_id is not None:
        for name, value in metrics.items():
            if isinstance(value, (int, float)):
                add_metric(db_conn, db_run_id, name, float(value), source=spec.id)
        add_artifact(db_conn, db_run_id, str(summary_json), kind="summary_json")
        add_artifact(db_conn, db_run_id, str(metrics_csv), kind="metrics_csv")
        finish_run(db_conn, db_run_id, status="finished")
        db_conn.close()

    elapsed = round(time.time() - started_at, 3)
    logger.info(
        "Hypothesis run complete: spec=%s  run_id=%s  verdict=%s  elapsed=%.3fs",
        spec.id, run_id, verdict, elapsed,
    )
    return summary


# ── CLI ────────────────────────────────────────────────────────────────────────

def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")

    parser = argparse.ArgumentParser(
        description="Run a governance-gated hypothesis from a YAML/JSON spec file."
    )
    parser.add_argument(
        "--spec", required=True,
        help="Path to HypothesisSpec YAML or JSON file",
    )
    parser.add_argument(
        "--output", default="artifacts",
        help="Root output directory (default: artifacts/)",
    )
    parser.add_argument(
        "--db", default=None,
        help="SQLite DB path for run logging (optional)",
    )
    args = parser.parse_args()

    spec_path = Path(args.spec)
    output_dir = Path(args.output)
    db_path = Path(args.db) if args.db else None

    # Load spec
    try:
        spec = load_spec(spec_path)
    except FileNotFoundError as exc:
        logger.error("Spec file not found: %s", exc)
        raise SystemExit(1) from exc

    # Validate — refuse to run if invalid
    try:
        validate_spec(spec)
    except ValidationError as exc:
        logger.error("Governance gate REJECTED spec:\n%s", exc)
        # Write a refusal record so the caller has a machine-readable signal
        refusal = {
            "spec_id": spec.id,
            "validation_status": "invalid",
            "errors": exc.errors,
        }
        output_dir.mkdir(parents=True, exist_ok=True)
        refusal_path = output_dir / f"{spec.id}_refusal.json"
        with open(refusal_path, "w", encoding="utf-8") as fh:
            json.dump(refusal, fh, indent=2)
        logger.error("Refusal record written to %s", refusal_path)
        raise SystemExit(2) from exc

    # Execute
    summary = run_hypothesis(spec, output_dir=output_dir, db_path=db_path)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
