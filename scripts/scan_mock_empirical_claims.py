#!/usr/bin/env python3
"""Fail CI when mock/fixture artifacts claim empirical evidence.

Scans JSON (and JSON-like) artifacts under nominated roots for forbidden
watermark combinations such as:

  run_mode in {mock, offline_fixture, mock_e2e, dry_run}
  AND evidence_class / metrics_are_empirical claiming empirical status.

Exit codes:
  0 — clean
  1 — violations found
  2 — usage / IO error
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Iterator


_MOCK_RUN_MODES = {
    "mock",
    "offline_fixture",
    "mock_e2e",
    "mock-e2e",
    "dry_run",
    "synthetic_circular_demonstration",
}

_EMPIRICAL_EVIDENCE_CLASSES = {
    "empirical",
    "EMPIRICAL",
    "operational_empirical",
    "real_eeg_empirical",
    "empirical_baseline",
}


def _walk_json_objects(node: Any, path: str = "$") -> Iterator[tuple[str, dict]]:
    if isinstance(node, dict):
        yield path, node
        for key, value in node.items():
            yield from _walk_json_objects(value, f"{path}.{key}")
    elif isinstance(node, list):
        for idx, value in enumerate(node):
            yield from _walk_json_objects(value, f"{path}[{idx}]")


def _is_mock_run_mode(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    return value.strip().lower() in {m.lower() for m in _MOCK_RUN_MODES}


def _claims_empirical(obj: dict) -> list[str]:
    hits: list[str] = []
    evidence = obj.get("evidence_class")
    if isinstance(evidence, str) and evidence.strip() in _EMPIRICAL_EVIDENCE_CLASSES:
        hits.append(f"evidence_class={evidence!r}")
    if obj.get("metrics_are_empirical") is True:
        hits.append("metrics_are_empirical=True")
    if obj.get("scientific_pass") is True and _is_mock_run_mode(obj.get("run_mode")):
        hits.append("scientific_pass=True under mock run_mode")
    return hits


def scan_file(path: Path) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return [f"{path}: read error: {exc}"]
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return []
    violations: list[str] = []
    for loc, obj in _walk_json_objects(payload):
        run_mode = obj.get("run_mode")
        if not _is_mock_run_mode(run_mode):
            # Also catch synthetic_circular evidence without run_mode but claiming empirical.
            evidence = obj.get("evidence_class")
            if (
                isinstance(evidence, str)
                and "synthetic" in evidence.lower()
                and obj.get("metrics_are_empirical") is True
            ):
                violations.append(
                    f"{path}{loc}: synthetic evidence_class with metrics_are_empirical=True"
                )
            continue
        for hit in _claims_empirical(obj):
            violations.append(f"{path}{loc}: mock run_mode={run_mode!r} claims {hit}")
    return violations


def iter_scan_targets(roots: list[Path]) -> Iterator[Path]:
    for root in roots:
        if root.is_file() and root.suffix.lower() == ".json":
            yield root
            continue
        if not root.exists():
            continue
        for path in root.rglob("*.json"):
            if path.is_file():
                yield path


def main(argv: list[str] | Path | list[Path] | None = None) -> int:
    if isinstance(argv, (str, Path)):
        argv = [str(argv)]
    elif argv is not None:
        argv = [str(a) for a in argv]

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "roots",
        nargs="*",
        type=Path,
        default=[
            Path("outputs"),
            Path("artifacts"),
            Path("tests/btc_icft"),
        ],
        help="Files or directories to scan (default: outputs artifacts tests/btc_icft)",
    )
    args = parser.parse_args(argv)

    violations: list[str] = []
    scanned = 0
    for path in iter_scan_targets(list(args.roots)):
        scanned += 1
        violations.extend(scan_file(path))

    if violations:
        print(f"FAIL: {len(violations)} mock-as-empirical claim(s) in {scanned} JSON file(s)")
        for line in violations:
            print(f"  - {line}")
        return 1

    print(f"OK: scanned {scanned} JSON file(s); no mock-as-empirical claims")
    return 0


if __name__ == "__main__":
    sys.exit(main())
