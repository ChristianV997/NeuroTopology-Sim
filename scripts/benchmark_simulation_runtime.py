#!/usr/bin/env python
"""Fresh-process benchmark for the production PITNN/LLG simulation path.

The benchmark compares the pre-optimization topology audit (the existing
tracker method) with the production call-site using the bounded density-reuse
helper.  Both modes execute ``sim.pitnn.vampire_os_llg.simulate_os_llg``; the
baseline mode only swaps the audit callback inside its isolated child so the
comparison does not use a synthetic stand-in.

Every result is performance-only evidence.  The deterministic simulation input
is labeled as a local simulation/benchmark surrogate and is never empirical
evidence.  Each configuration is isolated with the repository process runner,
which records hard timeout state, child/parent RSS, tracemalloc, exit status,
and checksum telemetry.  A timeout is never converted to PASS.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools.performance.evidence_normalizer import compare_evidence, normalize_record
from tools.streaming.memory_telemetry import dumps as telemetry_dumps
from tools.streaming.memory_telemetry import measure_workload
from tools.streaming.performance_policy import compare_records
from tools.streaming.process_runner import (
    Outcome,
    build_python_command,
    run_matrix,
    write_atomic_json,
)


def _git_value(args: List[str]) -> Optional[str]:
    try:
        result = subprocess.run(
            ["git", *args], cwd=_REPO_ROOT, check=True,
            capture_output=True, text=True, timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    value = result.stdout.strip()
    return value or None


def _reference_audit(tracker: Any, spins: np.ndarray) -> dict[str, Any]:
    """The unmodified audit callback used only by the isolated baseline child."""
    return tracker.audit_snapshot(spins)


def _result_checksum(result: Dict[str, Any]) -> tuple[float, str]:
    """Return a numeric policy checksum and a full finite-output SHA-256."""
    trace = [float(value) for value in result["trace_magnetization"]]
    topology = result["topology_trace"]
    numeric = float(sum(trace) + sum(float(row["topological_charge"]) for row in topology))
    payload = {
        "tau_eff_s": float(result["tau_eff_s"]),
        "final_magnetization": float(result["final_magnetization"]),
        "mean_magnetization": float(result["mean_magnetization"]),
        "max_spin_norm_error": float(result["max_spin_norm_error"]),
        "trace_magnetization": trace,
        "topology_trace": topology,
        "topology_final": result["topology_final"],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return numeric, hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _child_main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(prog="benchmark_simulation_runtime.py child")
    ap.add_argument("--mode", choices=("baseline", "optimized"), required=True)
    ap.add_argument("--n-spins", type=int, required=True)
    ap.add_argument("--steps", type=int, required=True)
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--backend", choices=("fast", "numpy"), default="fast")
    ap.add_argument("--repetitions", type=int, default=3)
    ap.add_argument("--inject-sleep", type=float, default=0.0)
    args = ap.parse_args(argv)

    if args.inject_sleep > 0:
        time.sleep(args.inject_sleep)

    import sim.pitnn.vampire_os_llg as llg
    from sim.pitnn.vampire_os_llg import LLGConfig

    original_callback = llg.audit_snapshot_reuse
    if args.mode == "baseline":
        llg.audit_snapshot_reuse = _reference_audit

    config = LLGConfig(n_spins=args.n_spins, steps=args.steps, seed=args.seed)
    last_result: Dict[str, Any] = {}

    def workload() -> float:
        nonlocal last_result
        last_result = llg.simulate_os_llg(config, backend=args.backend)
        checksum, _ = _result_checksum(last_result)
        return checksum

    try:
        telemetry = measure_workload(
            workload,
            label=f"pitnn_llg_topology_{args.mode}",
            repetitions=args.repetitions,
            backend=args.backend,
            input_dims={
                "samples": args.steps,
                "channels": args.n_spins,
                "dtype": "float64",
            },
        ).to_dict()
    finally:
        llg.audit_snapshot_reuse = original_callback

    checksum, digest = _result_checksum(last_result)
    finite = bool(
        np.isfinite(checksum)
        and np.isfinite(last_result["final_magnetization"])
        and np.isfinite(last_result["mean_magnetization"])
        and np.isfinite(last_result["max_spin_norm_error"])
        and last_result["max_spin_norm_error"] < 1e-12
    )
    telemetry.update({
        "benchmark_id": f"pitnn-llg-topology-{args.mode}",
        "mode": args.mode,
        "seed": args.seed,
        "simulation_shape": {"n_spins": args.n_spins, "steps": args.steps},
        "checksum": checksum,
        "checksum_sha256": digest,
        "correctness_ok": finite,
        "timed_out": False,
        "evidence_class": "performance_only",
        "synthetic": True,
        "provenance_label": "local_deterministic_simulation_performance_only",
        "simulation_path": "sim.pitnn.vampire_os_llg.simulate_os_llg",
        "notes": [
            "Real production PITNN/LLG simulation path; deterministic local simulation input.",
            "Performance evidence only; not empirical evidence or scientific evidence.",
            "Topology charge and beta1 proxy retain their existing definitions and units.",
        ],
    })
    # Explicit finite serialization makes non-finite telemetry an infrastructure
    # failure instead of an apparently valid performance result.
    sys.stdout.write(telemetry_dumps(telemetry, indent=None) + "\n")
    return 0 if finite else 2


def _command_builder(script: str):
    def builder(config: Dict[str, Any]) -> List[str]:
        return build_python_command(
            script,
            [
                "child",
                "--mode", str(config["mode"]),
                "--n-spins", str(config["n_spins"]),
                "--steps", str(config["steps"]),
                "--seed", str(config["seed"]),
                "--backend", str(config["backend"]),
                "--repetitions", str(config["repetitions"]),
            ],
        )
    return builder


def _raw_record(child: Dict[str, Any], *, source_commit: Optional[str], branch: Optional[str]) -> Dict[str, Any]:
    telemetry = child.get("telemetry") if isinstance(child.get("telemetry"), dict) else {}
    record = dict(telemetry)
    record.update({
        "outcome": child.get("outcome"),
        "timed_out": bool(child.get("timed_out", False)),
        "process_exit_status": child.get("exit_code"),
        "process_elapsed_s": child.get("elapsed_s"),
        "parent_sampled_peak_rss_bytes": child.get("parent_sampled_peak_rss_bytes"),
        "source_commit": source_commit,
        "branch": branch,
        "host": platform.node() or None,
        "platform": sys.platform,
        "python_version": platform.python_version(),
    })
    return record


def run_benchmark(args: argparse.Namespace) -> Dict[str, Any]:
    configs = [
        {
            "mode": mode,
            "n_spins": args.n_spins,
            "steps": args.steps,
            "seed": args.seed,
            "backend": args.backend,
            "repetitions": args.repetitions,
        }
        for mode in args.modes
    ]
    runner_report = run_matrix(
        _command_builder(str(Path(__file__).resolve())),
        configs,
        timeout_s=args.timeout_s,
        sequential=True,
        required_metrics=("checksum", "tracemalloc_peak_bytes"),
        sample_rss=True,
    )
    commit = _git_value(["rev-parse", "HEAD"])
    branch = _git_value(["branch", "--show-current"])
    records = [_raw_record(child, source_commit=commit, branch=branch)
               for child in runner_report["results"]]

    normalized = [normalize_record(record).to_dict() for record in records]
    normalization_decision: Optional[Dict[str, Any]] = None
    policy_decision: Optional[Dict[str, Any]] = None
    if len(records) == 2:
        normalization_decision = compare_evidence(records[0], records[1]).to_dict()
        if any(bool(record.get("timed_out")) for record in records):
            policy_decision = {
                "verdict": "inconclusive",
                "valid_comparison": False,
                "timeout_status": True,
                "evidence_class": "performance_only",
                "notes": ["Timeout is an operational outcome and can never become PASS."],
            }
        else:
            policy_decision = compare_records(records[0], records[1]).to_dict()

    successful = bool(runner_report["all_passed"])
    normalized_pass = normalization_decision is not None and normalization_decision["decision"] == "pass"
    policy_pass = policy_decision is not None and policy_decision.get("verdict") == "pass"
    report = {
        "schema": "simulation_runtime_benchmark/v1",
        "evidence_class": "performance_only",
        "synthetic": True,
        "benchmark_surrogate": True,
        "simulation_path": "sim.pitnn.vampire_os_llg.simulate_os_llg",
        "config": {
            "modes": list(args.modes),
            "n_spins": args.n_spins,
            "steps": args.steps,
            "seed": args.seed,
            "backend": args.backend,
            "repetitions": args.repetitions,
            "timeout_s": args.timeout_s,
        },
        "runner": runner_report["runner"],
        "summary": runner_report["summary"],
        "all_children_passed": successful,
        "records": records,
        "normalized_records": normalized,
        "normalization_decision": normalization_decision,
        "performance_policy_decision": policy_decision,
        "all_passed": bool(successful and normalized_pass and policy_pass),
        "notes": [
            "Fresh child process per mode; timeout/crash/missing telemetry are not PASS.",
            "Child RSS and parent-sampled RSS are best-effort and process-lifetime measurements.",
            "Checkpoint contracts are unchanged: this per-snapshot optimization has no resumable state.",
            "Performance evidence is never scientific evidence and does not support empirical claims.",
        ],
    }
    return report


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--modes", nargs="+", choices=("baseline", "optimized"),
                    default=["baseline", "optimized"])
    ap.add_argument("--n-spins", type=int, default=512)
    ap.add_argument("--steps", type=int, default=150)
    ap.add_argument("--seed", type=int, default=17)
    ap.add_argument("--backend", choices=("fast", "numpy"), default="fast")
    ap.add_argument("--repetitions", type=int, default=3)
    ap.add_argument("--timeout-s", type=float, default=60.0)
    ap.add_argument("--output", default=None)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    if args.n_spins < 3 or args.steps < 1 or args.repetitions < 1:
        ap.error("n-spins >= 3, steps >= 1, repetitions >= 1 are required")

    if args.modes and args.modes[0] == "child":
        return _child_main(args.modes[1:])
    report = run_benchmark(args)
    if args.output:
        write_atomic_json(args.output, report)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True, allow_nan=False))
    else:
        print(
            f"path={report['simulation_path']} shape={report['config']['n_spins']}x"
            f"{report['config']['steps']} backend={report['config']['backend']} "
            f"all_passed={report['all_passed']}"
        )
        for record in report["records"]:
            print(
                f"  mode={record.get('mode')} outcome={record.get('outcome')} "
                f"runtime={record.get('wall_best_s')}s "
                f"tracemalloc={record.get('tracemalloc_peak_bytes')} "
                f"rss={record.get('peak_rss_bytes')} "
                f"timeout={record.get('timed_out')} checksum={record.get('checksum')}"
            )
        print(f"normalization_decision={report['normalization_decision']}")
        print(f"performance_policy_decision={report['performance_policy_decision']}")
    return 0 if report["all_passed"] else 1


if __name__ == "__main__":
    # The child mode is intentionally parsed separately so its required mode
    # arguments are not confused with the parent matrix's --modes option.
    if len(sys.argv) > 1 and sys.argv[1] == "child":
        raise SystemExit(_child_main(sys.argv[2:]))
    raise SystemExit(main())
