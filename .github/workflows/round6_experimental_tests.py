"""Run changed Round 6 candidate suites against their checked-in implementations.

This helper is invoked only from the Required Checks workflow. It uses explicit
file mappings so a test-only PR cannot pass by skipping an import that is not
present on main. Every selected file runs in a fresh bounded pytest process.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any


COMPONENTS: dict[str, dict[str, Any]] = {
    "planar_geometry": {
        "triggers": (
            "neurotopology_sim/experimental/geometry/",
            "tests/neurotopology_sim/experimental/geometry/",
            "tests/experimental/test_planar_triangulation.py",
        ),
        "implementation": "neurotopology_sim/experimental/geometry/planar_triangulation.py",
        "tests": (
            "tests/neurotopology_sim/experimental/geometry/test_planar_triangulation.py",
            "tests/experimental/test_planar_triangulation.py",
        ),
    },
    "hodge_2d": {
        "triggers": (
            "neurotopology_sim/experimental/topology/hodge_2d.py",
            "tests/neurotopology_sim/experimental/topology/test_hodge_2d.py",
            "tools/hodge_decomposition_audit/",
            "tests/tools/hodge_decomposition_audit/",
            "experimental/phase_cochain_reference/",
            "tests/experimental/phase_cochain_reference/",
        ),
        "implementation_any": (
            "neurotopology_sim/experimental/topology/hodge_2d.py",
            "tools/hodge_decomposition_audit/audit.py",
            "experimental/phase_cochain_reference/hodge.py",
        ),
        "tests": (
            "tests/neurotopology_sim/experimental/topology/test_hodge_2d.py",
            "tests/tools/hodge_decomposition_audit/test_hodge_audit.py",
            "tests/experimental/phase_cochain_reference/test_weighted_hodge_decomposition.py",
        ),
    },
    "spherical_csd": {
        "triggers": (
            "neurotopology_sim/experimental/preprocessing/",
            "tests/neurotopology_sim/experimental/preprocessing/",
            "tests/experimental/test_spherical_csd_parity.py",
            "tools/mne_csd_reference_audit/",
            "tests/mne_csd_reference_audit/",
        ),
        "implementation_any": (
            "neurotopology_sim/experimental/preprocessing/spherical_csd.py",
            "tools/mne_csd_reference_audit/kkt.py",
        ),
        "tests": (
            "tests/neurotopology_sim/experimental/preprocessing/test_spherical_csd.py",
            "tests/experimental/test_spherical_csd_parity.py",
            "tests/mne_csd_reference_audit/test_kkt_operator.py",
            "tests/mne_csd_reference_audit/test_legendre_constants.py",
        ),
    },
    "four_sphere": {
        "triggers": (
            "physics/eeg_forward/",
            "tests/physics/eeg_forward/",
            "tools/experimental_audits/four_shell_bvp_oracle.py",
            "tests/experimental_audits/test_four_shell_bvp_oracle.py",
        ),
        "implementation_any": (
            "physics/eeg_forward/four_sphere.py",
            "tools/experimental_audits/four_shell_bvp_oracle.py",
        ),
        "tests": (
            "tests/physics/eeg_forward/test_four_sphere.py",
            "tests/experimental_audits/test_four_shell_bvp_oracle.py",
        ),
    },
    "phase_winding": {
        "triggers": (
            "neurotopology_sim/experimental/topology/winding.py",
            "tests/neurotopology_sim/experimental/topology/test_phase_winding.py",
        ),
        "implementation": "neurotopology_sim/experimental/topology/winding.py",
        "tests": ("tests/neurotopology_sim/experimental/topology/test_phase_winding.py",),
    },
    "surrogate_nulls": {
        "triggers": ("tools/surrogate_nulls/", "tests/surrogate_nulls/"),
        "implementation_any": (
            "tools/surrogate_nulls/nulls.py",
            "tools/surrogate_nulls/spectral.py",
            "tools/surrogate_nulls/csd.py",
        ),
        "tests": (
            "tests/surrogate_nulls/test_phase_nulls.py",
            "tests/surrogate_nulls/test_mv_iaaft.py",
            "tests/surrogate_nulls/test_csd_estimators.py",
            "tests/surrogate_nulls/test_cholesky_csd.py",
            "tests/surrogate_nulls/test_edge_cases.py",
        ),
    },
    "phase_uncertainty": {
        "triggers": ("tools/phase_uncertainty/", "tests/phase_uncertainty/"),
        "implementation": "tools/phase_uncertainty/candidate_estimator.py",
        "tests": (
            "tests/phase_uncertainty/test_candidate_contract.py",
            "tests/phase_uncertainty/test_calibration_coverage.py",
            "tests/phase_uncertainty/test_synthetic_fixtures.py",
        ),
    },
    "surrogate_audit": {
        "triggers": ("tools/surrogate_audit/", "tests/surrogate_audit/"),
        "implementation_any": (
            "tools/surrogate_audit/mv_fpr.py",
            "tools/surrogate_audit/mv_iaaft.py",
        ),
        "tests": (
            "tests/surrogate_audit/test_mv_fpr.py",
            "tests/surrogate_audit/test_mv_iaaft.py",
            "tests/surrogate_audit/test_invalid_inputs.py",
        ),
    },
    "synthetic_roc": {
        "triggers": (
            "neurotopology_sim/experimental/benchmarks/",
            "tests/neurotopology_sim/experimental/benchmarks/",
            "tests/experimental/test_synthetic_roc_calibration_split.py",
        ),
        "implementation": "neurotopology_sim/experimental/benchmarks/synthetic_forward_roc.py",
        "tests": (
            "tests/neurotopology_sim/experimental/benchmarks/test_synthetic_forward_roc.py",
            "tests/experimental/test_synthetic_roc_calibration_split.py",
        ),
    },
}


def select_components(changed_paths: set[str]) -> list[str]:
    """Return deterministic component names touched by source or test changes."""
    selected = []
    for name, spec in COMPONENTS.items():
        if any(
            path == trigger or path.startswith(trigger)
            for path in changed_paths
            for trigger in spec["triggers"]
        ):
            selected.append(name)
    return selected


def inspect_component(name: str, root: Path) -> dict[str, Any]:
    """Resolve required implementation and test files without guessing absent files."""
    spec = COMPONENTS[name]
    source_options = spec.get("implementation_any") or (spec["implementation"],)
    sources = [path for path in source_options if (root / path).is_file()]
    tests = [path for path in spec["tests"] if (root / path).is_file()]
    if not sources:
        return {"component": name, "status": "BLOCKED", "reason": "candidate implementation absent", "implementation_candidates": list(source_options), "tests": tests}
    if not tests:
        return {"component": name, "status": "BLOCKED", "reason": "candidate tests absent", "implementations": sources, "test_candidates": list(spec["tests"])}
    return {"component": name, "status": "READY_TO_RUN", "implementations": sources, "tests": tests}


def junit_counts(path: Path) -> tuple[int, int, int, int]:
    """Return collected, skipped, failed, and errored testcase counts."""
    root = ET.parse(path).getroot()
    cases = list(root.iter("testcase"))
    skipped = sum(case.find("skipped") is not None for case in cases)
    failed = sum(case.find("failure") is not None for case in cases)
    errors = sum(case.find("error") is not None for case in cases)
    return len(cases), skipped, failed, errors


def junit_status(counts: tuple[int, int, int, int]) -> str:
    """A candidate suite passes only when it collected real tests and skipped none."""
    collected, skipped, failed, errors = counts
    return "PASS" if collected > 0 and skipped == 0 and failed == 0 and errors == 0 else "FAIL"


def collect_changed_paths(base: str, head: str, root: Path) -> set[str]:
    if not re.fullmatch(r"[0-9a-f]{40}", base) or not re.fullmatch(r"[0-9a-f]{40}", head):
        raise ValueError("base and head must be full commit SHAs")
    result = subprocess.run(
        ["git", "diff", "--name-only", f"{base}...{head}"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return {line.replace("\\", "/") for line in result.stdout.splitlines() if line.strip()}


def run(root: Path, base: str, head: str, report_path: Path) -> int:
    root = root.resolve()
    changed = collect_changed_paths(base, head, root)
    selected = select_components(changed)
    report: dict[str, Any] = {
        "schema_version": "round6-experimental-ci-report-v1",
        "base_sha": base,
        "head_sha": head,
        "status": "NOT_APPLICABLE" if not selected else "INCONCLUSIVE",
        "changed_paths": sorted(changed),
        "components": [],
        "statement": "No scientific or empirical validity is assessed by this CI report.",
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    if not selected:
        report_path.write_text(json.dumps(report, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        print("No mapped Round 6 candidate files changed; this does not certify any experimental lane.")
        return 0

    report["status"] = "PASS"
    with tempfile.TemporaryDirectory(prefix="round6-ci-") as tmp:
        temp = Path(tmp)
        for index, name in enumerate(selected, start=1):
            entry = inspect_component(name, root)
            report["components"].append(entry)
            if entry["status"] != "READY_TO_RUN":
                if report["status"] == "PASS":
                    report["status"] = "BLOCKED"
                continue
            for test_index, test_file in enumerate(entry["tests"], start=1):
                junit = temp / f"{index:02d}-{name}-{test_index:02d}.xml"
                telemetry = temp / f"{index:02d}-{name}-{test_index:02d}.json"
                logs = temp / f"{index:02d}-{name}-{test_index:02d}-logs"
                cmd = [
                    sys.executable,
                    "scripts/run_tests_isolated.py",
                    "--root", ".",
                    "--batch-size", "1",
                    "--timeout-s", "120",
                    "--report", str(telemetry),
                    "--report-dir", str(logs),
                    f"--pytest-arg=--junitxml={junit}",
                    test_file,
                ]
                try:
                    completed = subprocess.run(cmd, cwd=root, timeout=130, check=False)
                except subprocess.TimeoutExpired:
                    report["status"] = "FAIL"
                    entry.setdefault("executions", []).append({"test_file": test_file, "status": "TIMEOUT"})
                    continue
                execution: dict[str, Any] = {"test_file": test_file, "runner_exit_code": completed.returncode}
                telemetry_ok = False
                if telemetry.is_file():
                    batch_report = json.loads(telemetry.read_text(encoding="utf-8"))
                    batches = batch_report.get("batches", [])
                    execution["runner_batches"] = [b.get("status", "unknown") for b in batches]
                    summary = batch_report.get("summary", {})
                    telemetry_ok = (
                        batch_report.get("exit_code") == 0
                        and bool(batches)
                        and all(batch.get("status") == "passed" for batch in batches)
                        and summary.get("skipped_batches") == 0
                        and summary.get("failed_batches") == 0
                        and summary.get("timeout_batches") == 0
                    )
                    execution["tests_collected"] = 0
                    execution["skipped"] = None
                execution["isolated_runner_telemetry_valid"] = telemetry_ok
                if junit.is_file():
                    collected, skipped, failed, errors = junit_counts(junit)
                    execution.update({"tests_collected": collected, "skipped": skipped, "failed": failed, "errors": errors})
                entry.setdefault("executions", []).append(execution)
                if completed.returncode or not telemetry_ok or not junit.is_file():
                    report["status"] = "FAIL"
                    continue
                try:
                    counts = junit_counts(junit)
                except (ET.ParseError, OSError) as exc:
                    execution["junit_error"] = str(exc)
                    report["status"] = "FAIL"
                    continue
                if junit_status(counts) != "PASS":
                    report["status"] = "FAIL"
                execution.update({"tests_collected": counts[0], "skipped": counts[1], "failed": counts[2], "errors": counts[3]})

    report_path.write_text(json.dumps(report, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "components": report["components"]}, sort_keys=True))
    return 0 if report["status"] in {"PASS", "NOT_APPLICABLE"} else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", required=True)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        return run(args.root, args.base, args.head, args.report)
    except (OSError, ValueError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        print(f"Round 6 candidate test discovery failed closed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
