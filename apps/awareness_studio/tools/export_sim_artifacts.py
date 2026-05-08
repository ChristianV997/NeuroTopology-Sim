"""Export sim artifacts as Markdown docs for RAG ingestion.

Priority:
  1. Scan artifacts_root/**/RunRecord.json  (RunRecordV1 contract)
  2. Fall back: walk artifacts_root/**/summary.json (legacy)

Output: inputs/sim_artifacts/run_{run_kind}_{run_id}.md  (stable filename)

Usage:
  python -m apps.awareness_studio.tools.export_sim_artifacts \
      --artifacts-root artifacts \
      --out-dir apps/awareness_studio/inputs/sim_artifacts

  # or via the helper:
  python tools/export_sim_artifacts.py --artifacts-root /path/to/artifacts
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

_FRONTMATTER_KEYS = (
    "run_id", "run_kind", "spec_id", "claim_type",
    "layer", "created_at", "verdict",
)


# ── Markdown renderer ─────────────────────────────────────────────────────────

def _render_markdown(record: Dict[str, Any]) -> str:
    """Render a RunRecordV1 dict as a Markdown doc with YAML frontmatter."""
    lines: List[str] = ["---"]
    for key in _FRONTMATTER_KEYS:
        val = record.get(key)
        lines.append(f"{key}: {val!r}")
    lines += ["---", ""]

    run_id = record.get("run_id", "unknown")
    run_kind = record.get("run_kind", "unknown")
    spec_id = record.get("spec_id") or "—"
    verdict = record.get("verdict") or "—"

    lines += [
        f"# Run Report: {run_id}",
        "",
        f"**Kind:** {run_kind}  ",
        f"**Spec:** {spec_id}  ",
        f"**Verdict:** {verdict}  ",
        f"**Created:** {record.get('created_at', '')}  ",
        "",
    ]

    metrics = record.get("metrics", {})
    if metrics:
        lines += [
            "## Metrics",
            "",
            "| Metric | Value |",
            "|--------|-------|",
        ]
        for k, v in metrics.items():
            lines.append(f"| {k} | {v} |")
        lines.append("")

    artifacts = record.get("artifacts", {})
    if artifacts:
        lines += [
            "## Artifacts",
            "",
        ]
        for name, path in artifacts.items():
            lines.append(f"- `{name}`: {path}")
        lines.append("")

    source = record.get("source")
    if source:
        lines += [f"*Source spec: {source}*", ""]

    return "\n".join(lines)


def _out_filename(record: Dict[str, Any]) -> str:
    run_id = record.get("run_id", "unknown")
    run_kind = record.get("run_kind", "unknown").replace(" ", "_")
    return f"run_{run_kind}_{run_id}.md"


# ── Export logic ──────────────────────────────────────────────────────────────

def export(
    artifacts_root: Path,
    out_dir: Path,
) -> List[Path]:
    """Export sim artifacts to Markdown. Returns list of written paths."""
    artifacts_root = Path(artifacts_root)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    written: List[Path] = []

    # ── Primary: RunRecord.json files ─────────────────────────────────────────
    run_records = sorted(artifacts_root.rglob("RunRecord.json"))

    if run_records:
        for rr_path in run_records:
            try:
                record = json.loads(rr_path.read_text(encoding="utf-8"))
            except Exception as exc:
                print(f"[export] skipping {rr_path}: {exc}", file=sys.stderr)
                continue
            md = _render_markdown(record)
            fname = _out_filename(record)
            out_path = out_dir / fname
            out_path.write_text(md, encoding="utf-8")
            written.append(out_path)
            print(f"[export] {rr_path} → {out_path}")
        return written

    # ── Fallback: summary.json files (legacy) ─────────────────────────────────
    summary_files = sorted(artifacts_root.rglob("summary.json"))
    for s_path in summary_files:
        try:
            data = json.loads(s_path.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"[export] skipping {s_path}: {exc}", file=sys.stderr)
            continue
        run_id = data.get("run_id", s_path.parent.name)
        record = {
            "run_id": run_id,
            "run_kind": "hypothesis",
            "spec_id": data.get("spec_id"),
            "claim_type": None,
            "layer": None,
            "created_at": data.get("created_at"),
            "verdict": data.get("verdict"),
            "metrics": data.get("metrics_summary", {}),
            "artifacts": {"summary.json": str(s_path)},
            "source": str(s_path),
        }
        md = _render_markdown(record)
        fname = _out_filename(record)
        out_path = out_dir / fname
        out_path.write_text(md, encoding="utf-8")
        written.append(out_path)
        print(f"[export] {s_path} (fallback) → {out_path}")

    return written


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Export sim artifacts to Markdown")
    parser.add_argument(
        "--artifacts-root",
        default="artifacts",
        help="Root directory to scan for RunRecord.json / summary.json",
    )
    parser.add_argument(
        "--out-dir",
        default="apps/awareness_studio/inputs/sim_artifacts",
        help="Output directory for Markdown docs",
    )
    args = parser.parse_args()
    written = export(Path(args.artifacts_root), Path(args.out_dir))
    print(f"[export] done — {len(written)} file(s) written")


if __name__ == "__main__":
    main()
