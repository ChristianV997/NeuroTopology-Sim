"""Completeness validator for a P18.1 DS005620 end-to-end execution artifact root.

Checks:
  - all six P18.1 artifacts exist
  - P12 label_alignment.csv exists after successful run
  - P13 features_m_signal_labeled.csv exists after successful run
  - P11 metrics_signal_mt.json exists after successful run
  - omega invariants remain False for forbidden actions
  - report.md contains no banned phrases
  - benchmark_completed is True only when all stages succeeded

Usage:
  python tools/validate_ds005620_e2e_execution.py --root <artifact_root>

Exits non-zero on any failure.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REQUIRED_P18_1_ARTIFACTS = [
    "ds005620_real_benchmark_execution.json",
    "stage_execution_plan.json",
    "stage_results.json",
    "execution_blockers.json",
    "omega_event.json",
    "report.md",
]

_OMEGA_INVARIANTS_FALSE = [
    "labels_inferred",
    "targets_fabricated",
    "source_contracts_modified",
    "legacy_mt_real_modified",
    "contracts_activated_by_executor",
    "p11_promotion_gate_modified",
    "consciousness_claims_made",
]

_BANNED_PHRASES = (
    "proves consciousness",
    "consciousness proven",
    "soul proven",
    "afterlife proven",
    "liberation detected",
    "ontology solved",
    "ultimate reality",
    "q equals self",
    "q equals soul",
    "q_abs equals suffering",
    "f_dress equals karma",
    "sedated implies no_experience",
    "unresponsive implies unconscious",
    "topology proves liberation",
    "eeg proves consciousness",
)


def validate(root: Path) -> tuple[bool, list[str]]:
    failures: list[str] = []

    if not root.is_dir():
        return False, [f"artifact root does not exist: {root}"]

    for name in _REQUIRED_P18_1_ARTIFACTS:
        if not (root / name).is_file():
            failures.append(f"missing P18.1 artifact: {name}")

    if failures:
        return False, failures

    summary = json.loads((root / "ds005620_real_benchmark_execution.json").read_text())
    stage_results = json.loads((root / "stage_results.json").read_text())
    omega = json.loads((root / "omega_event.json").read_text())
    report = (root / "report.md").read_text()

    stages = {s["stage_id"]: s for s in stage_results.get("stages", [])}

    if summary.get("p12_succeeded"):
        p12 = stages.get("P12") or {}
        for out in p12.get("expected_outputs", []):
            if not Path(out).exists():
                failures.append(f"P12 expected output missing on disk: {out}")
        if "label_alignment.csv" not in " ".join(p12.get("expected_outputs", [])):
            failures.append("P12 expected outputs missing label_alignment.csv reference")

    if summary.get("p13_succeeded"):
        p13 = stages.get("P13") or {}
        for out in p13.get("expected_outputs", []):
            if not Path(out).exists():
                failures.append(f"P13 expected output missing on disk: {out}")
        if "features_m_signal_labeled.csv" not in " ".join(p13.get("expected_outputs", [])):
            failures.append(
                "P13 expected outputs missing features_m_signal_labeled.csv reference"
            )

    if summary.get("p11_succeeded"):
        p11 = stages.get("P11") or {}
        for out in p11.get("expected_outputs", []):
            if not Path(out).exists():
                failures.append(f"P11 expected output missing on disk: {out}")
        if "metrics_signal_mt.json" not in " ".join(p11.get("expected_outputs", [])):
            failures.append("P11 expected outputs missing metrics_signal_mt.json reference")

    for inv in _OMEGA_INVARIANTS_FALSE:
        if omega.get(inv) is not False:
            failures.append(f"omega invariant {inv!r} must be False, got {omega.get(inv)!r}")

    lower_report = report.lower()
    for phrase in _BANNED_PHRASES:
        if phrase in lower_report:
            failures.append(f"banned phrase in report.md: {phrase!r}")

    benchmark_completed = summary.get("benchmark_completed", False)
    all_succeeded = (
        summary.get("p12_succeeded")
        and summary.get("p13_succeeded")
        and summary.get("p11_succeeded")
    )
    if benchmark_completed and not all_succeeded:
        failures.append(
            "benchmark_completed is True but not all stages succeeded"
        )

    # P11 must consume P13 labeled features (not raw Level M)
    p11 = stages.get("P11") or {}
    cmd = " ".join(p11.get("command", []))
    if cmd and "features_m_signal_labeled.csv" not in cmd:
        failures.append(
            "P11 command must consume the P13 features_m_signal_labeled.csv "
            "(not raw Level M features_m_signal.csv)"
        )

    return len(failures) == 0, failures


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--root",
        required=True,
        help="Path to a P18.1 DS005620 execution artifact directory.",
    )
    args = ap.parse_args(argv)

    ok, failures = validate(Path(args.root))
    if ok:
        print(f"[validate-ds005620-e2e] PASS: {args.root}")
        return 0
    print(f"[validate-ds005620-e2e] FAIL: {args.root}", file=sys.stderr)
    for f in failures:
        print(f"  - {f}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
