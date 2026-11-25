"""Export sim artifacts as Markdown docs for RAG ingestion.

Priority:
  1. Scan artifacts_root/**/RunRecord.json  (RunRecordV1 contract)
  2. Fall back: walk artifacts_root/**/summary.json (legacy)

Output: inputs/sim_artifacts/run_{run_kind}_{run_id}.md  (stable filename)

Fail-closed epistemic gate
--------------------------
Engineering ``verdict`` values (PASS/FAIL/…) are never treated as empirical
evidence unless the record explicitly carries complete watermarks:

  - evidence_class
  - run_mode
  - metrics_are_empirical

Missing or conflicting watermarks → NON-EMPIRICAL stamp in frontmatter and
body. ``scientific_pass`` is never inferred true by this exporter.

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
    "run_id",
    "run_kind",
    "spec_id",
    "claim_type",
    "layer",
    "created_at",
    # ``verdict`` retained for promotion-gate adapters; always engineering-only.
    # Prefer engineering_verdict + epistemic_status when reading this export.
    "verdict",
    "engineering_verdict",
    "evidence_class",
    "run_mode",
    "metrics_are_empirical",
    "scientific_pass",
    "metric_kind",
    "epistemic_status",
)

_SYNTHETIC_OR_MOCK_MODES = {
    "synthetic",
    "mock",
    "dry_run",
    "offline_fixture",
    "scaffold",
    "demo",
    "simulation",
}

_NON_EMPIRICAL_EVIDENCE_HINTS = (
    "synthetic",
    "scaffold",
    "demo",
    "mock",
    "engineering",
    "performance",
    "proxy",
    "hypothesis",
    "fixture",
)

_MISSING = "__missing__"


def _truthy_bool(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "yes", "1"}:
            return True
        if lowered in {"false", "no", "0"}:
            return False
    return None


def _lookup_watermark(record: Dict[str, Any], key: str) -> Any:
    """Prefer top-level watermark; fall back to metrics / metrics_summary."""
    if key in record and record[key] not in (None, ""):
        return record[key]
    for nest_key in ("metrics", "metrics_summary"):
        nest = record.get(nest_key)
        if isinstance(nest, dict) and nest.get(key) not in (None, ""):
            return nest[key]
    return _MISSING


def classify_evidence_stamps(record: Dict[str, Any]) -> Dict[str, Any]:
    """Fail-closed evidence classification for RAG Markdown export.

    Empirical treatment requires *all* of:
      evidence_class, run_mode, metrics_are_empirical=True
    plus non-synthetic run_mode and non-synthetic evidence_class hints.

    Anything else → epistemic_status NON_EMPIRICAL (or NON_EMPIRICAL_INCOMPLETE /
    NON_EMPIRICAL_CONFLICT). scientific_pass is never promoted by this helper.
    """
    evidence_class_raw = _lookup_watermark(record, "evidence_class")
    run_mode_raw = _lookup_watermark(record, "run_mode")
    metrics_emp_raw = _lookup_watermark(record, "metrics_are_empirical")
    scientific_pass_raw = _lookup_watermark(record, "scientific_pass")
    metric_kind_raw = _lookup_watermark(record, "metric_kind")

    missing: List[str] = []
    if evidence_class_raw is _MISSING:
        missing.append("evidence_class")
    if run_mode_raw is _MISSING:
        missing.append("run_mode")
    if metrics_emp_raw is _MISSING:
        missing.append("metrics_are_empirical")

    evidence_class = None if evidence_class_raw is _MISSING else str(evidence_class_raw)
    run_mode = None if run_mode_raw is _MISSING else str(run_mode_raw).strip().lower()
    metrics_are_empirical = (
        None if metrics_emp_raw is _MISSING else _truthy_bool(metrics_emp_raw)
    )
    if metrics_emp_raw is not _MISSING and metrics_are_empirical is None:
        # Unparseable → fail closed as not empirical.
        metrics_are_empirical = False
        missing.append("metrics_are_empirical_unparseable")

    scientific_pass_declared = (
        None if scientific_pass_raw is _MISSING else _truthy_bool(scientific_pass_raw)
    )
    metric_kind = None if metric_kind_raw is _MISSING else str(metric_kind_raw)

    reasons: List[str] = []
    conflict = False

    if missing:
        reasons.append("missing_watermarks:" + ",".join(missing))

    if metrics_are_empirical is True and run_mode in _SYNTHETIC_OR_MOCK_MODES:
        conflict = True
        reasons.append("metrics_empirical_with_synthetic_run_mode")

    if metrics_are_empirical is True and evidence_class:
        ec_lower = evidence_class.lower()
        if any(hint in ec_lower for hint in _NON_EMPIRICAL_EVIDENCE_HINTS):
            conflict = True
            reasons.append("metrics_empirical_with_non_empirical_evidence_class")

    if scientific_pass_declared is True and metrics_are_empirical is not True:
        conflict = True
        reasons.append("scientific_pass_without_empirical_metrics")

    treat_as_empirical = (
        not missing
        and not conflict
        and metrics_are_empirical is True
        and run_mode not in _SYNTHETIC_OR_MOCK_MODES
        and bool(evidence_class)
        and bool(run_mode)
    )

    if treat_as_empirical:
        epistemic_status = "DECLARED_EMPIRICAL_METRICS"
        # Exporter never asserts scientific confirmation.
        scientific_pass_out = False
        reasons.append("declared_empirical_metrics_only_not_scientific_confirmation")
    elif conflict:
        epistemic_status = "NON_EMPIRICAL_CONFLICT"
        scientific_pass_out = False
        metrics_are_empirical = False
    elif missing:
        epistemic_status = "NON_EMPIRICAL_INCOMPLETE"
        scientific_pass_out = False
        metrics_are_empirical = False
    else:
        epistemic_status = "NON_EMPIRICAL"
        scientific_pass_out = False
        if metrics_are_empirical is None:
            metrics_are_empirical = False

    engineering_verdict = record.get("verdict")
    return {
        "evidence_class": evidence_class or "undeclared_incomplete_provenance",
        "run_mode": run_mode or "undeclared",
        "metrics_are_empirical": bool(metrics_are_empirical),
        "scientific_pass": scientific_pass_out,
        "metric_kind": metric_kind or "undeclared",
        "epistemic_status": epistemic_status,
        "treat_as_empirical": treat_as_empirical,
        "engineering_verdict": engineering_verdict,
        "reasons": reasons,
    }


# ── Markdown renderer ─────────────────────────────────────────────────────────

def _render_markdown(record: Dict[str, Any]) -> str:
    """Render a RunRecordV1 dict as Markdown with fail-closed evidence stamps."""
    stamps = classify_evidence_stamps(record)
    view = dict(record)
    # Surface engineering verdict under both keys; epistemic_status is authoritative.
    view["verdict"] = stamps["engineering_verdict"]
    view["engineering_verdict"] = stamps["engineering_verdict"]
    view["evidence_class"] = stamps["evidence_class"]
    view["run_mode"] = stamps["run_mode"]
    view["metrics_are_empirical"] = stamps["metrics_are_empirical"]
    view["scientific_pass"] = stamps["scientific_pass"]
    view["metric_kind"] = stamps["metric_kind"]
    view["epistemic_status"] = stamps["epistemic_status"]

    lines: List[str] = ["---"]
    for key in _FRONTMATTER_KEYS:
        val = view.get(key)
        lines.append(f"{key}: {val!r}")
    lines += ["---", ""]

    run_id = record.get("run_id", "unknown")
    run_kind = record.get("run_kind", "unknown")
    spec_id = record.get("spec_id") or "—"
    eng_verdict = stamps["engineering_verdict"]
    eng_disp = "—" if eng_verdict in (None, "") else str(eng_verdict)

    if stamps["treat_as_empirical"]:
        banner = (
            "> **DECLARED EMPIRICAL METRICS (not scientific confirmation).** "
            "Watermarks present; exporter does not assert scientific_pass."
        )
        verdict_line = (
            f"**Engineering verdict:** {eng_disp}  "
            "(declared empirical metrics — not a scientific PASS)"
        )
    else:
        banner = (
            f"> **NON-EMPIRICAL** (`{stamps['epistemic_status']}`). "
            "Engineering verdict must not be read as empirical or scientific evidence. "
            f"Reasons: {', '.join(stamps['reasons']) or 'non_empirical_watermarks'}."
        )
        verdict_line = (
            f"**Engineering verdict:** {eng_disp}  "
            "(engineering only — **not empirical**)"
        )

    lines += [
        f"# Run Report: {run_id}",
        "",
        banner,
        "",
        f"**Kind:** {run_kind}  ",
        f"**Spec:** {spec_id}  ",
        verdict_line,
        f"**Created:** {record.get('created_at', '')}  ",
        "",
        "## Evidence watermark",
        "",
        f"- epistemic_status: `{stamps['epistemic_status']}`",
        f"- evidence_class: `{stamps['evidence_class']}`",
        f"- run_mode: `{stamps['run_mode']}`",
        f"- metrics_are_empirical: `{stamps['metrics_are_empirical']}`",
        f"- scientific_pass: `{stamps['scientific_pass']}`",
        f"- metric_kind: `{stamps['metric_kind']}`",
        f"- engineering_verdict: `{eng_disp}`",
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
            stamps = classify_evidence_stamps(record)
            print(
                f"[export] {rr_path} → {out_path} "
                f"[{stamps['epistemic_status']}]"
            )
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
            "run_kind": data.get("run_kind") or "hypothesis",
            "spec_id": data.get("spec_id"),
            "claim_type": data.get("claim_type"),
            "layer": data.get("layer"),
            "created_at": data.get("created_at"),
            "verdict": data.get("verdict"),
            "metrics": data.get("metrics_summary", data.get("metrics", {})),
            "artifacts": {"summary.json": str(s_path)},
            "source": str(s_path),
            # Propagate watermarks when present on modern summaries.
            "evidence_class": data.get("evidence_class"),
            "run_mode": data.get("run_mode"),
            "metrics_are_empirical": data.get("metrics_are_empirical"),
            "scientific_pass": data.get("scientific_pass"),
            "metric_kind": data.get("metric_kind"),
        }
        md = _render_markdown(record)
        fname = _out_filename(record)
        out_path = out_dir / fname
        out_path.write_text(md, encoding="utf-8")
        written.append(out_path)
        stamps = classify_evidence_stamps(record)
        print(
            f"[export] {s_path} (fallback) → {out_path} "
            f"[{stamps['epistemic_status']}]"
        )

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
