#!/usr/bin/env python3
"""Cheap CI scanner: EEG scaffold artifacts must carry evidence watermarks.

Fails closed when a scanned JSON/Markdown artifact claims empirical science
without ``evidence_class`` / ``run_mode``, or when Level M mock reports omit
quarantine watermarks.

Stdlib-only. No network. Safe to run in Required Checks.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Iterable


REQUIRED_JSON_KEYS = ("evidence_class", "run_mode")
FORBIDDEN_UNWATERMARKED_PHRASES = (
    "operational empirical baseline",
    "empirical eeg evidence",
)
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


def _iter_files(roots: Iterable[Path], extensions: tuple[str, ...]) -> list[Path]:
    files: list[Path] = []
    for root in roots:
        if root.is_file():
            if root.suffix.lower() in extensions:
                files.append(root)
            continue
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.is_file() and path.suffix.lower() in extensions:
                files.append(path)
    return sorted(files)


def scan_json(path: Path) -> list[str]:
    errors: list[str] = []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"{path}: unreadable json ({exc})"]

    if not isinstance(payload, dict):
        return errors

    # Only enforce watermarks on EEG scaffold / mock artifacts we own.
    markers = (
        payload.get("event_type"),
        payload.get("signal_provenance"),
        payload.get("evidence_class"),
        payload.get("recipe_id"),
        payload.get("safe_claim"),
    )
    text_blob = " ".join(str(m) for m in markers if m is not None).lower()
    is_eeg_scaffold = any(
        token in text_blob
        for token in (
            "signal_block",
            "level_t_signal",
            "synthetic_circular",
            "fixture_signal",
            "derived_feature_recipe",
            "label_conditioned",
            "level m",
            "eeg_mne_adapter",
            "mock_mne_extract",
            "mne_local_file_extract",
        )
    ) or path.name in {
        "metrics_m.json",
        "omega_event.json",
        "signal_block_inventory.json",
        "mapping.json",
        "summary.json",
        "mne_signal_metadata.json",
        "mne_extraction_report.json",
    }

    if not is_eeg_scaffold:
        return errors

    for key in REQUIRED_JSON_KEYS:
        if key not in payload or payload[key] in (None, ""):
            errors.append(f"{path}: missing required watermark key {key!r}")

    if payload.get("scientific_pass") is True and payload.get("evidence_class") in {
        "synthetic_circular_demonstration",
        "fixture_signal_block_scaffold",
        "level_t_signal_proxy_scaffold",
        "derived_feature_recipe_scaffold",
        "mock_label_conditioned_topology_scaffold",
        "mock_mne_extract_fixture",
    }:
        errors.append(f"{path}: scientific_pass=true incompatible with scaffold evidence_class")

    run_mode = payload.get("run_mode")
    if isinstance(run_mode, str) and run_mode.strip().lower() in {m.lower() for m in _MOCK_RUN_MODES}:
        evidence = payload.get("evidence_class")
        if isinstance(evidence, str) and evidence.strip() in _EMPIRICAL_EVIDENCE_CLASSES:
            errors.append(
                f"{path}: mock run_mode={run_mode!r} claims empirical evidence_class={evidence!r}"
            )
        if payload.get("metrics_are_empirical") is True:
            errors.append(f"{path}: mock run_mode={run_mode!r} claims metrics_are_empirical=True")
        if payload.get("scientific_pass") is True:
            errors.append(f"{path}: mock run_mode={run_mode!r} claims scientific_pass=True")

    evidence = payload.get("evidence_class")
    if (
        isinstance(evidence, str)
        and "synthetic" in evidence.lower()
        and payload.get("metrics_are_empirical") is True
    ):
        errors.append(f"{path}: synthetic evidence_class with metrics_are_empirical=True")

    return errors


def scan_markdown(path: Path) -> list[str]:
    errors: list[str] = []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return [f"{path}: unreadable markdown ({exc})"]

    lower = text.lower()
    looks_like_eeg_report = (
        "level m" in lower
        or "level t" in lower
        or "signal block" in lower
        or "evidence watermark" in lower
        or path.name == "report.md"
    )
    if not looks_like_eeg_report:
        return errors

    for phrase in FORBIDDEN_UNWATERMARKED_PHRASES:
        if phrase in lower and "evidence_class" not in lower:
            errors.append(
                f"{path}: phrase {phrase!r} without evidence_class watermark section"
            )

    if "evidence watermark" in lower or "evidence_class" in lower:
        if "evidence_class" not in lower or "run_mode" not in lower:
            errors.append(f"{path}: incomplete evidence watermark (need evidence_class + run_mode)")

    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "roots",
        nargs="*",
        type=Path,
        default=[Path("outputs")],
        help="Files or directories to scan (default: outputs/)",
    )
    args = parser.parse_args(argv)

    errors: list[str] = []
    for path in _iter_files(args.roots, (".json",)):
        errors.extend(scan_json(path))
    for path in _iter_files(args.roots, (".md",)):
        errors.extend(scan_markdown(path))

    if errors:
        for err in errors:
            print(err, file=sys.stderr)
        print(f"EEG watermark scan failed: {len(errors)} issue(s)", file=sys.stderr)
        return 1

    print("EEG watermark scan passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
