#!/usr/bin/env python3
"""Cheap CI scanner: sim run-card ``*.run.json`` artifacts need evidence watermarks.

Fails closed when a scanned psi/meditation run card:
  - omits evidence_class / run_mode / metrics_are_empirical / scientific_pass / metric_kind
  - claims metrics_are_empirical=True or scientific_pass=True under synthetic/mock run_mode
  - (meditation) fabricates topology zeros (Qz/Qabs/f_dress/vort_mean == 0.0) instead of null/n/a

Stdlib-only. No network. Safe for Required Checks / Makefile / smoke.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any, Iterable, List, Optional

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

_TOPOLOGY_KEYS = ("Qz_mean", "Qabs_mean", "f_dress", "vort_mean")

_FORBIDDEN_METRIC_KINDS = {
    "fabricated_topology",
    "fabricated_zero_topology",
    "rng_normal_fabricated",
}


def _iter_run_cards(roots: Iterable[Path]) -> List[Path]:
    files: List[Path] = []
    for root in roots:
        if root.is_file() and root.name.endswith(".run.json"):
            files.append(root)
            continue
        if not root.exists():
            continue
        for path in root.rglob("*.run.json"):
            files.append(path)
    return sorted(set(files))


def _is_missing_topology(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return True
    if isinstance(value, str) and value.strip().lower() in {"", "n/a", "na", "null", "none", "nan"}:
        return True
    return False


def _is_fabricated_zero(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if isinstance(value, float) and not math.isfinite(value):
            return False
        return float(value) == 0.0
    return False


def scan_json(path: Path) -> List[str]:
    errors: List[str] = []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"{path}: unreadable json ({exc})"]

    if not isinstance(payload, dict):
        return errors

    mode = str(payload.get("mode") or payload.get("run_kind") or "").strip().lower()
    if mode not in {"psi", "meditation"}:
        return errors

    for key in REQUIRED_KEYS:
        if key not in payload or payload[key] in (None, ""):
            errors.append(f"{path}: missing required watermark key {key!r}")

    run_mode = str(payload.get("run_mode") or "").strip().lower()
    metrics_emp = payload.get("metrics_are_empirical")
    sci_pass = payload.get("scientific_pass")
    metric_kind = payload.get("metric_kind")

    if run_mode in _SYNTHETIC_OR_MOCK_MODES or run_mode == "":
        if metrics_emp is True:
            errors.append(
                f"{path}: run_mode={run_mode or 'missing'!r} claims metrics_are_empirical=True"
            )
        if sci_pass is True:
            errors.append(
                f"{path}: run_mode={run_mode or 'missing'!r} claims scientific_pass=True"
            )

    if isinstance(metric_kind, str) and metric_kind in _FORBIDDEN_METRIC_KINDS:
        errors.append(f"{path}: forbidden fabricated metric_kind={metric_kind!r}")

    metrics = payload.get("metrics")
    if mode == "meditation" and isinstance(metrics, dict):
        for tkey in _TOPOLOGY_KEYS:
            if tkey not in metrics:
                continue
            val = metrics[tkey]
            if _is_fabricated_zero(val):
                errors.append(
                    f"{path}: meditation fabricates topology zero for {tkey!r} "
                    "(use null/n/a; topology not computed)"
                )
            elif not _is_missing_topology(val):
                # Meditation path must not claim a real topology measurement.
                errors.append(
                    f"{path}: meditation claims topology metric {tkey!r}={val!r} "
                    "without a topology compute path (expected null/n/a)"
                )

    return errors


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "roots",
        nargs="*",
        type=Path,
        default=[Path("outputs/run_cards")],
        help="Files or directories to scan (default: outputs/run_cards)",
    )
    args = parser.parse_args(argv)
    all_errors: List[str] = []
    scanned = 0
    for path in _iter_run_cards(args.roots):
        scanned += 1
        all_errors.extend(scan_json(path))
    if all_errors:
        for err in all_errors:
            print(err, file=sys.stderr)
        print(f"run-card watermark scan failed: {len(all_errors)} issue(s)", file=sys.stderr)
        return 1
    print(
        f"ok: scanned {scanned} run-card watermark(s) under "
        f"{', '.join(str(r) for r in args.roots)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
