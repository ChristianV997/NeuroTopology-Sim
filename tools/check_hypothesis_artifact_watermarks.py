#!/usr/bin/env python3
"""Cheap CI scanner: hypothesis RunRecord/summary artifacts need evidence watermarks.

Fails closed when a scanned hypothesis artifact:
  - omits evidence_class / run_mode / metrics_are_empirical / scientific_pass
  - claims metrics_are_empirical=True with synthetic/mock run_mode
  - claims scientific_pass=True with scaffold/synthetic evidence_class
  - uses fabricated metric_kind (rng scaffold) or missing metric_kind

Stdlib-only. No network. Safe for Required Checks.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Iterable, List

REQUIRED_KEYS = (
    "evidence_class",
    "run_mode",
    "metrics_are_empirical",
    "scientific_pass",
    "metric_kind",
)

_SYNTHETIC_OR_MOCK_MODES = {
    "synthetic",
    "mock",
    "dry_run",
    "offline_fixture",
    "scaffold",
}

_SCAFFOLD_EVIDENCE = {
    "synthetic_hypothesis_demonstration",
    "governance_hypothesis_scaffold",
}

_FORBIDDEN_METRIC_KINDS = {
    "rng_normal_fabricated",
    "fabricated_topology",
    "scaffold_random_topology",
}


def _iter_files(roots: Iterable[Path]) -> List[Path]:
    files: List[Path] = []
    for root in roots:
        if root.is_file() and root.suffix.lower() == ".json":
            files.append(root)
            continue
        if not root.exists():
            continue
        for path in root.rglob("*.json"):
            if path.name in {"RunRecord.json", "summary.json"} or "hypothesis" in path.name.lower():
                files.append(path)
    return sorted(set(files))


def _is_hypothesis_artifact(payload: dict, path: Path) -> bool:
    if path.name == "RunRecord.json" and payload.get("run_kind") == "hypothesis":
        return True
    if path.name == "summary.json" and (
        "metrics_summary" in payload or payload.get("claim_type") in {"M", "K", "C"}
    ):
        # Hypothesis summaries always carry metrics_summary after this slice.
        if "evidence_class" in payload or "spec_id" in payload or "verdict" in payload:
            # Narrow to hypothesis when run_kind/metric_kind/data_mode markers present
            # or when metric_kind is set / path under a hypothesis-ish tree.
            if payload.get("metric_kind") or payload.get("run_kind") == "hypothesis":
                return True
            if "hypothesis" in str(path).lower():
                return True
            # YAML pipeline summary always has metrics_summary + verdict + spec_id.
            if "metrics_summary" in payload and "verdict" in payload and "spec_id" in payload:
                return True
    return False


def scan_json(path: Path) -> List[str]:
    errors: List[str] = []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"{path}: unreadable json ({exc})"]

    if not isinstance(payload, dict) or not _is_hypothesis_artifact(payload, path):
        return errors

    for key in REQUIRED_KEYS:
        if key not in payload or payload[key] in (None, ""):
            # metric_kind may live inside metrics for RunRecord
            if key == "metric_kind":
                metrics = payload.get("metrics") or payload.get("metrics_summary") or {}
                if isinstance(metrics, dict) and metrics.get("metric_kind"):
                    continue
            errors.append(f"{path}: missing required watermark key {key!r}")

    run_mode = str(payload.get("run_mode") or "").strip().lower()
    evidence = str(payload.get("evidence_class") or "").strip()
    metrics_emp = payload.get("metrics_are_empirical")
    sci_pass = payload.get("scientific_pass")
    metric_kind = payload.get("metric_kind")
    if not metric_kind:
        metrics = payload.get("metrics") or payload.get("metrics_summary") or {}
        if isinstance(metrics, dict):
            metric_kind = metrics.get("metric_kind")

    if run_mode in _SYNTHETIC_OR_MOCK_MODES:
        if metrics_emp is True:
            errors.append(
                f"{path}: run_mode={run_mode!r} claims metrics_are_empirical=True"
            )
        if sci_pass is True:
            errors.append(f"{path}: run_mode={run_mode!r} claims scientific_pass=True")

    if evidence in _SCAFFOLD_EVIDENCE and sci_pass is True:
        errors.append(
            f"{path}: scientific_pass=true incompatible with evidence_class={evidence!r}"
        )

    if isinstance(metric_kind, str) and metric_kind in _FORBIDDEN_METRIC_KINDS:
        errors.append(f"{path}: forbidden fabricated metric_kind={metric_kind!r}")

    return errors


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "roots",
        nargs="*",
        type=Path,
        default=[Path("artifacts")],
        help="Files or directories to scan (default: artifacts/)",
    )
    args = parser.parse_args(argv)
    all_errors: List[str] = []
    for path in _iter_files(args.roots):
        all_errors.extend(scan_json(path))
    if all_errors:
        for err in all_errors:
            print(err, file=sys.stderr)
        return 1
    print(f"ok: scanned hypothesis watermarks under {', '.join(str(r) for r in args.roots)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
