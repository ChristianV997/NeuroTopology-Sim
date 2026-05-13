"""Completeness validator for a P18.1 DS005620 end-to-end execution artifact root."""
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


def validate(root: Path) -> tuple[bool, list[str], dict]:
    failures: list[str] = []
    checked_stages: list[str] = []

    if not root.is_dir():
        summary = {
            "ok": False,
            "root": str(root),
            "failures": [f"artifact root does not exist: {root}"],
            "checked_artifacts": _REQUIRED_P18_1_ARTIFACTS,
            "checked_stages": checked_stages,
            "benchmark_completed": False,
        }
        return False, summary["failures"], summary

    for name in _REQUIRED_P18_1_ARTIFACTS:
        if not (root / name).is_file():
            failures.append(f"missing P18.1 artifact: {name}")

    benchmark_completed = False
    if failures:
        summary = {
            "ok": False,
            "root": str(root),
            "failures": failures,
            "checked_artifacts": _REQUIRED_P18_1_ARTIFACTS,
            "checked_stages": checked_stages,
            "benchmark_completed": benchmark_completed,
        }
        return False, failures, summary

    summary_json = json.loads((root / "ds005620_real_benchmark_execution.json").read_text())
    stage_results = json.loads((root / "stage_results.json").read_text())
    omega = json.loads((root / "omega_event.json").read_text())
    report = (root / "report.md").read_text()
    benchmark_completed = bool(summary_json.get("benchmark_completed", False))

    stages = {s["stage_id"]: s for s in stage_results.get("stages", [])}

    if summary_json.get("p12_succeeded"):
        checked_stages.append("P12")
        p12 = stages.get("P12") or {}
        for out in p12.get("expected_outputs", []):
            if not Path(out).exists():
                failures.append(f"P12 expected output missing on disk: {out}")
        if "label_alignment.csv" not in " ".join(p12.get("expected_outputs", [])):
            failures.append("P12 expected outputs missing label_alignment.csv reference")

    if summary_json.get("p13_succeeded"):
        checked_stages.append("P13")
        p13 = stages.get("P13") or {}
        for out in p13.get("expected_outputs", []):
            if not Path(out).exists():
                failures.append(f"P13 expected output missing on disk: {out}")
        if "features_m_signal_labeled.csv" not in " ".join(p13.get("expected_outputs", [])):
            failures.append(
                "P13 expected outputs missing features_m_signal_labeled.csv reference"
            )

    if summary_json.get("p11_succeeded"):
        checked_stages.append("P11")
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

    all_succeeded = (
        summary_json.get("p12_succeeded")
        and summary_json.get("p13_succeeded")
        and summary_json.get("p11_succeeded")
    )
    if benchmark_completed and not all_succeeded:
        failures.append("benchmark_completed is True but not all stages succeeded")

    p11 = stages.get("P11") or {}
    cmd = " ".join(p11.get("command", []))
    if cmd and "features_m_signal_labeled.csv" not in cmd:
        failures.append(
            "P11 command must consume the P13 features_m_signal_labeled.csv "
            "(not raw Level M features_m_signal.csv)"
        )

    summary = {
        "ok": len(failures) == 0,
        "root": str(root),
        "failures": failures,
        "checked_artifacts": _REQUIRED_P18_1_ARTIFACTS,
        "checked_stages": checked_stages,
        "benchmark_completed": benchmark_completed,
    }
    return summary["ok"], failures, summary


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True, help="Path to a P18.1 DS005620 execution artifact directory.")
    ap.add_argument("--json-out", default=None, help="Optional path to write machine-readable validation summary JSON.")
    ap.add_argument("--quiet", action="store_true", default=False, help="Suppress PASS/FAIL console output; still exits 0/1.")
    args = ap.parse_args(argv)

    ok, failures, summary = validate(Path(args.root))

    if args.json_out:
        out_path = Path(args.json_out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    if not args.quiet:
        if ok:
            print(f"[validate-ds005620-e2e] PASS: {args.root}")
        else:
            print(f"[validate-ds005620-e2e] FAIL: {args.root}", file=sys.stderr)
            for f in failures:
                print(f"  - {f}", file=sys.stderr)

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
