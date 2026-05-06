"""
Export simulation run records and hypothesis artifacts as Markdown documents
for ingestion into the Awareness Studio RAG index.

Usage:
    python -m apps.awareness_studio.tools.export_sim_artifacts [OPTIONS]

    Options:
      --db PATH         SQLite database path (default: data/runs.sqlite)
      --artifacts PATH  Artifacts root directory (default: artifacts/)
      --out PATH        Output directory (default: apps/awareness_studio/inputs/sim_artifacts/)
      --specs PATH      Governance specs directory (default: governance/specs/)

For each hypothesis run found in the DB (or artifacts/ directory if no DB),
this tool emits one Markdown document per run that the RAG indexer can ingest.
"""
from __future__ import annotations

import argparse
import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Default paths relative to repo root
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
_DEFAULT_DB = _REPO_ROOT / "data" / "runs.sqlite"
_DEFAULT_ARTIFACTS = _REPO_ROOT / "artifacts"
_DEFAULT_OUT = Path(__file__).resolve().parent.parent / "inputs" / "sim_artifacts"
_DEFAULT_SPECS = _REPO_ROOT / "governance" / "specs"


# ── DB helpers ─────────────────────────────────────────────────────────────────

def _query_runs(db_path: Path) -> List[Dict[str, Any]]:
    """Return all hypothesis runs from SQLite, with metrics and artifacts."""
    if not db_path.exists():
        return []
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        runs = conn.execute(
            "SELECT * FROM runs WHERE kind LIKE 'hypothesis/%' ORDER BY started_at DESC"
        ).fetchall()
        result = []
        for row in runs:
            run = dict(row)
            run_id = run["id"]
            metrics = conn.execute(
                "SELECT name, value, units FROM metrics WHERE run_id=?", (run_id,)
            ).fetchall()
            arts = conn.execute(
                "SELECT path, kind FROM artifacts WHERE run_id=?", (run_id,)
            ).fetchall()
            run["metrics"] = [dict(m) for m in metrics]
            run["artifacts"] = [dict(a) for a in arts]
            try:
                run["params"] = json.loads(run.get("params_json") or "{}")
            except (json.JSONDecodeError, TypeError):
                run["params"] = {}
            result.append(run)
        return result
    finally:
        conn.close()


# ── Markdown emitters ──────────────────────────────────────────────────────────

def _format_timestamp(ts: Optional[float]) -> str:
    if ts is None:
        return "unknown"
    try:
        return datetime.fromtimestamp(float(ts), tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    except (TypeError, ValueError, OSError):
        return str(ts)


def _run_to_markdown(run: Dict[str, Any]) -> str:
    """Convert a DB run record to a Markdown document."""
    params = run.get("params", {})
    spec_id = params.get("spec_id", run.get("name", "unknown"))
    claim_type = params.get("claim_type", "?")
    layer = params.get("layer", "?")
    run_hex = params.get("run_id", str(run.get("id", "?")))

    started = _format_timestamp(run.get("started_at"))
    finished = _format_timestamp(run.get("finished_at"))
    status = run.get("status", "unknown")

    lines = [
        f"# Simulation Run: {spec_id}",
        "",
        f"**Run ID:** `{run_hex}`  ",
        f"**Spec ID:** `{spec_id}`  ",
        f"**Claim type:** {claim_type}  ",
        f"**Layer:** {layer}  ",
        f"**Status:** {status}  ",
        f"**Started:** {started}  ",
        f"**Finished:** {finished}  ",
        "",
    ]

    metrics = run.get("metrics", [])
    if metrics:
        lines += ["## Key Metrics", ""]
        lines += ["| Metric | Value | Units |", "|--------|-------|-------|"]
        for m in metrics:
            lines.append(f"| {m['name']} | {m['value']} | {m.get('units', '')} |")
        lines.append("")

    artifacts = run.get("artifacts", [])
    if artifacts:
        lines += ["## Artifacts", ""]
        for a in artifacts:
            lines.append(f"- `{a['path']}` ({a.get('kind', '')})")
        lines.append("")

    return "\n".join(lines)


def _summary_to_markdown(summary: Dict[str, Any], spec_id: str) -> str:
    """Convert a summary.json to a Markdown document."""
    run_id = summary.get("run_id", "unknown")
    claim_type = summary.get("claim_type", "?")
    layer = summary.get("layer", "?")
    title = summary.get("title", spec_id)
    verdict = summary.get("verdict", "unknown")
    val_status = summary.get("validation_status", "unknown")
    started = summary.get("started_at", "unknown")
    data_mode = summary.get("data_mode", "unknown")

    lines = [
        f"# Hypothesis Run: {spec_id}",
        "",
        f"**Title:** {title}  ",
        f"**Spec ID:** `{spec_id}`  ",
        f"**Run ID:** `{run_id}`  ",
        f"**Claim type:** {claim_type}  ",
        f"**Layer:** {layer}  ",
        f"**Validation status:** {val_status}  ",
        f"**Verdict:** {verdict}  ",
        f"**Data mode:** {data_mode}  ",
        f"**Started:** {started}  ",
        "",
    ]

    metrics = summary.get("metrics_summary", {})
    if metrics:
        lines += ["## Key Metrics", ""]
        lines += ["| Metric | Value |", "|--------|-------|"]
        for k, v in metrics.items():
            lines.append(f"| {k} | {v} |")
        lines.append("")

    arts = summary.get("artifacts", {})
    if arts:
        lines += ["## Artifact Paths", ""]
        for k, v in arts.items():
            lines.append(f"- **{k}:** `{v}`")
        lines.append("")

    return "\n".join(lines)


# ── export logic ───────────────────────────────────────────────────────────────

def export_from_db(
    db_path: Path,
    out_dir: Path,
) -> List[Path]:
    """Export all hypothesis runs from SQLite to Markdown docs."""
    runs = _query_runs(db_path)
    if not runs:
        logger.info("No hypothesis runs found in %s", db_path)
        return []

    out_dir.mkdir(parents=True, exist_ok=True)
    written: List[Path] = []
    for run in runs:
        params = run.get("params", {})
        spec_id = params.get("spec_id", run.get("name", f"run_{run.get('id')}"))
        run_hex = params.get("run_id", str(run.get("id")))
        md = _run_to_markdown(run)
        filename = f"{spec_id}__{run_hex}.md"
        out_path = out_dir / filename
        out_path.write_text(md, encoding="utf-8")
        written.append(out_path)
        logger.info("Wrote %s", out_path)
    return written


def export_from_artifacts(
    artifacts_root: Path,
    out_dir: Path,
) -> List[Path]:
    """Walk artifacts/ directory and export any summary.json files to Markdown."""
    summary_files = list(artifacts_root.glob("**/summary.json"))
    if not summary_files:
        logger.info("No summary.json files found under %s", artifacts_root)
        return []

    out_dir.mkdir(parents=True, exist_ok=True)
    written: List[Path] = []
    for sf in sorted(summary_files):
        try:
            with open(sf, encoding="utf-8") as fh:
                summary = json.load(fh)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Skipping %s: %s", sf, exc)
            continue

        spec_id = summary.get("spec_id", "unknown")
        run_id = summary.get("run_id", sf.parent.name)
        md = _summary_to_markdown(summary, spec_id)
        filename = f"{spec_id}__{run_id}.md"
        out_path = out_dir / filename
        out_path.write_text(md, encoding="utf-8")
        written.append(out_path)
        logger.info("Wrote %s", out_path)
    return written


def run_export(
    db_path: Optional[Path] = None,
    artifacts_root: Optional[Path] = None,
    out_dir: Optional[Path] = None,
) -> List[Path]:
    """Main export entry point — tries DB first, then falls back to artifacts/."""
    db_path = db_path or _DEFAULT_DB
    artifacts_root = artifacts_root or _DEFAULT_ARTIFACTS
    out_dir = out_dir or _DEFAULT_OUT
    out_dir.mkdir(parents=True, exist_ok=True)

    written: List[Path] = []

    # Try DB-backed export
    if db_path.exists():
        written.extend(export_from_db(db_path, out_dir))

    # Always also walk artifacts/ for any summary.json not in DB
    if artifacts_root.exists():
        from_arts = export_from_artifacts(artifacts_root, out_dir)
        # Deduplicate by filename
        existing = {p.name for p in written}
        for p in from_arts:
            if p.name not in existing:
                written.append(p)

    logger.info("Exported %d sim artifact docs → %s", len(written), out_dir)
    return written


# ── CLI ────────────────────────────────────────────────────────────────────────

def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
    parser = argparse.ArgumentParser(
        description="Export sim run records to Markdown for Awareness Studio RAG ingestion."
    )
    parser.add_argument("--db", default=None, help="SQLite DB path (default: data/runs.sqlite)")
    parser.add_argument("--artifacts", default=None, help="Artifacts root dir (default: artifacts/)")
    parser.add_argument(
        "--out", default=None,
        help="Output directory (default: apps/awareness_studio/inputs/sim_artifacts/)",
    )
    args = parser.parse_args()

    db_path = Path(args.db) if args.db else None
    artifacts_root = Path(args.artifacts) if args.artifacts else None
    out_dir = Path(args.out) if args.out else None

    written = run_export(db_path=db_path, artifacts_root=artifacts_root, out_dir=out_dir)
    if written:
        print(f"[OK] Exported {len(written)} document(s):")
        for p in written:
            print(f"  {p}")
    else:
        print("[WARN] No simulation runs found to export.")


if __name__ == "__main__":
    main()
