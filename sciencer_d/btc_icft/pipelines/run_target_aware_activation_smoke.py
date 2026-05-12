"""P15 — Target-aware activation smoke pipeline.

Orchestrates the full explicit-label path:
  P14 readiness → P12 active mock alignment → P10 topology →
  P13 target injection + P11 smoke → artifact validation → activation report.

This is a controlled smoke test only. It must not claim empirical validity.

Only explicit, declared, mock/human-reviewed binary mappings may produce y targets.
Does not activate real dataset contracts, infer labels, fabricate targets,
modify P11 promotion criteria, or touch legacy mt_real semantics.

Usage:
    python -m sciencer_d.btc_icft.pipelines.run_target_aware_activation_smoke \\
        --dataset-id DS005620 \\
        --root outputs/btc_icft \\
        --out outputs/btc_icft/target_aware_activation/DS005620 \\
        --mock-fixture \\
        --validate-artifacts
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

_BANNED_PHRASES: tuple[str, ...] = (
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
)

_SAFE_CLAIM = (
    "An explicit mock label contract was carried through P12 alignment, "
    "P13 target injection, and P11 target-aware signal benchmarking as a "
    "controlled activation smoke test."
)

_FORBIDDEN_CLAIMS = [
    "No empirical validation claim.",
    "No consciousness proof.",
    "No self or soul claim.",
    "No liberation or enlightenment claim.",
    "No afterlife claim.",
    "No ontology proof.",
    "No label inference.",
    "No target fabrication.",
]

_REAL_ACTIVATION_BLOCKED_MSG = (
    "P15 currently supports only explicit mock activation. "
    "Real dataset activation requires a separate human-reviewed contract PR "
    "with declared explicit_label_column, positive_values, negative_values, "
    "label_scope, and join_keys."
)


def _build_stage_commands(
    dataset_id: str,
    root: str,
    out_dir: str,
) -> list[tuple[str, list[str], str]]:
    """Return (stage_name, cmd_list, output_dir) for each stage."""
    t_features = f"{root}/eeg_level_t/{dataset_id}/features_t_signal.csv"
    return [
        (
            "p14_adapter_readiness",
            [
                sys.executable, "-m",
                "sciencer_d.btc_icft.pipelines.plan_dataset_label_adapters",
                "--mock-fixture",
                "--out", f"{root}/label_adapter_readiness",
            ],
            f"{root}/label_adapter_readiness",
        ),
        (
            "p12_explicit_label_alignment",
            [
                sys.executable, "-m",
                "sciencer_d.btc_icft.pipelines.align_eeg_labels",
                "--dataset-id", dataset_id,
                "--out", f"{root}/eeg_labels/{dataset_id}_active",
                "--mock-fixture",
                "--activate-mock-contract",
            ],
            f"{root}/eeg_labels/{dataset_id}_active",
        ),
        (
            "p10_level_t_signal_topology",
            [
                sys.executable, "-m",
                "sciencer_d.btc_icft.pipelines.run_eeg_level_t_signal",
                "--dataset-id", dataset_id,
                "--out", f"{root}/eeg_level_t/{dataset_id}",
                "--mock-fixture",
            ],
            f"{root}/eeg_level_t/{dataset_id}",
        ),
        (
            "p13_target_injection",
            [
                sys.executable, "-m",
                "sciencer_d.btc_icft.pipelines.inject_eeg_targets",
                "--dataset-id", dataset_id,
                "--out", f"{root}/eeg_targets/{dataset_id}_binary",
                "--mock-fixture",
                "--mock-binary-targets",
                "--run-p11-smoke",
                "--t-features", t_features,
                "--p11-out", f"{root}/eeg_signal_mt_targeted/{dataset_id}",
            ],
            f"{root}/eeg_targets/{dataset_id}_binary",
        ),
    ]


def _run_stage(
    stage: str,
    cmd: list[str],
    output_dir: str,
) -> dict:
    """Run one pipeline stage and return a stage result dict."""
    cp = subprocess.run(cmd, capture_output=True, text=True)
    stdout_lines = cp.stdout.strip().splitlines()
    stderr_lines = cp.stderr.strip().splitlines()
    return {
        "stage": stage,
        "command": cmd,
        "exit_code": cp.returncode,
        "stdout_tail": stdout_lines[-10:] if stdout_lines else [],
        "stderr_tail": stderr_lines[-5:] if stderr_lines else [],
        "output_dir": output_dir,
        "passed": cp.returncode == 0,
    }


def _read_metrics_snapshot(root: str, dataset_id: str) -> dict | None:
    """Read metrics_signal_mt.json from the target-aware P11 output."""
    metrics_path = (
        Path(root) / "eeg_signal_mt_targeted" / dataset_id / "metrics_signal_mt.json"
    )
    if not metrics_path.is_file():
        return None
    try:
        return json.loads(metrics_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _scan_banned_phrases(out_dir: str) -> list[str]:
    """Scan all JSON/MD/CSV artifacts in out_dir for banned phrases."""
    hits: list[str] = []
    out = Path(out_dir)
    if not out.is_dir():
        return hits
    for path in out.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in {".json", ".md", ".csv"}:
            continue
        try:
            text = path.read_text(encoding="utf-8").lower()
        except (OSError, UnicodeDecodeError):
            continue
        for phrase in _BANNED_PHRASES:
            if phrase in text:
                hits.append(f"{path.name}: '{phrase}'")
    return hits


def _build_guardrail_report(banned_hits: list[str]) -> dict:
    return {
        "no_label_inference": True,
        "no_target_fabrication": True,
        "no_real_contract_activation": True,
        "no_p11_gate_modification": True,
        "no_legacy_mt_real_change": True,
        "banned_phrase_scan_passed": len(banned_hits) == 0,
        "banned_phrases_found": banned_hits,
    }


def _build_omega_event(
    dataset_id: str,
    activation_smoke_passed: bool,
) -> dict:
    payload = f"{dataset_id}:{activation_smoke_passed}:{_SAFE_CLAIM}"
    return {
        "event_id": hashlib.sha256(payload.encode()).hexdigest()[:16],
        "event_type": "target_aware_activation_smoke",
        "dataset_id": dataset_id,
        "activation_smoke_passed": activation_smoke_passed,
        "safe_claim": _SAFE_CLAIM,
        "forbidden_claims": _FORBIDDEN_CLAIMS,
    }


def _build_report(
    dataset_id: str,
    summary: dict,
    metrics_snapshot: dict | None,
    guardrail_report: dict,
) -> str:
    lines = [
        "# Target-Aware EEG Signal Benchmark Activation Smoke",
        "",
        "## Stage",
        "",
        "P15 — Target-aware activation smoke pipeline. "
        "Controlled smoke test only; no empirical conclusion.",
        "",
        "## Dataset",
        "",
        f"`{dataset_id}`",
        "",
        "## Pipeline sequence",
        "",
        "1. P14 — Dataset label adapter readiness planning",
        "2. P12 — Active mock label contract alignment",
        "3. P10 — Level T signal topology extraction",
        "4. P13 — Target injection with explicit mock binary targets",
        "5. P11 — Target-aware signal M+T residual benchmark (smoke)",
        "",
        "## Target-aware metrics snapshot",
        "",
    ]
    if metrics_snapshot:
        lines += [
            f"- predictive_metrics_available: {metrics_snapshot.get('predictive_metrics_available')}",
            f"- explicit_targets_available: {metrics_snapshot.get('explicit_targets_available')}",
            f"- auc_m: {metrics_snapshot.get('auc_m')}",
            f"- auc_mt: {metrics_snapshot.get('auc_mt')}",
            f"- delta_auc: {metrics_snapshot.get('delta_auc')}",
            f"- brier_m: {metrics_snapshot.get('brier_m')}",
            f"- brier_mt: {metrics_snapshot.get('brier_mt')}",
            f"- ece_m: {metrics_snapshot.get('ece_m')}",
            f"- ece_mt: {metrics_snapshot.get('ece_mt')}",
            f"- delta_ece: {metrics_snapshot.get('delta_ece')}",
        ]
    else:
        lines.append("Metrics not available — target-aware P11 output missing.")
    lines += [
        "",
        "## Promotion decision",
        "",
    ]
    if metrics_snapshot:
        lines += [
            f"- promoted: {metrics_snapshot.get('promoted')}",
            f"- promotion_reason: {metrics_snapshot.get('promotion_reason', '(none)')}",
            "",
            "Note: Promotion is determined solely by existing P11 gates. "
            "P15 does not force or modify the promotion decision.",
        ]
    else:
        lines.append("Promotion status unavailable — metrics not loaded.")
    lines += [
        "",
        "## Activation smoke result",
        "",
        f"- activation_smoke_passed: {summary.get('activation_smoke_passed')}",
        "",
        "## Guardrails",
        "",
        "- No labels inferred from metadata, filenames, or free text.",
        "- No targets fabricated outside of declared explicit mock contract.",
        "- No real dataset contract activated.",
        "- No P11 promotion criteria modified.",
        "- No legacy DS005620 mt_real semantics modified.",
        "- No data downloaded.",
        "- No consciousness/self/soul/liberation/afterlife/ontology proof claims.",
        "",
        "## Safe claim",
        "",
        _SAFE_CLAIM,
        "",
        "## Forbidden claims",
        "",
    ]
    for fc in _FORBIDDEN_CLAIMS:
        lines.append(f"- {fc}")
    lines += [
        "",
        "## Next required step",
        "",
        "Activate a real dataset contract only through a separate human-reviewed PR "
        "with declared `explicit_label_column`, `positive_values`, `negative_values`, "
        "`label_scope`, and `join_keys`.",
        "",
    ]
    return "\n".join(lines)


def run(
    dataset_id: str = "DS005620",
    root: str = "outputs/btc_icft",
    out_dir: str = "outputs/btc_icft/target_aware_activation/DS005620",
    mock_fixture: bool = False,
    validate_artifacts: bool = False,
    keep_intermediate: bool = True,
) -> int:
    """Run the target-aware activation smoke pipeline.

    Returns:
        0 on success, 1 on failure.
    """
    if not mock_fixture:
        print(_REAL_ACTIVATION_BLOCKED_MSG, file=sys.stderr)
        return 1

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    stage_commands = _build_stage_commands(dataset_id, root, out_dir)
    stage_results: list[dict] = []
    warnings: list[str] = []
    all_stages_passed = True

    for stage, cmd, sout_dir in stage_commands:
        print(f"  [{stage}] running ...", flush=True)
        result = _run_stage(stage, cmd, sout_dir)
        stage_results.append(result)
        status = "OK" if result["passed"] else "FAIL"
        print(f"  [{stage}] {status} (exit={result['exit_code']})")
        if not result["passed"]:
            all_stages_passed = False
            for line in result["stderr_tail"]:
                print(f"    stderr: {line}", file=sys.stderr)
            warnings.append(f"Stage '{stage}' failed with exit code {result['exit_code']}.")

    # Optional validation step
    artifact_validation_ran = False
    if validate_artifacts and all_stages_passed:
        validate_cmd = [
            sys.executable,
            "tools/validate_eeg_signal_artifacts.py",
            "--root", root,
            "--dataset-id", dataset_id,
            "--allow-missing",
        ]
        validate_result = _run_stage(
            "artifact_validation", validate_cmd,
            f"{root}/eeg_signal_mt/{dataset_id}",
        )
        stage_results.append(validate_result)
        artifact_validation_ran = True
        if not validate_result["passed"]:
            warnings.append("Artifact validation failed.")

    # Read metrics snapshot
    metrics_snapshot = _read_metrics_snapshot(root, dataset_id)
    p11_out_dir = Path(root) / "eeg_signal_mt_targeted" / dataset_id
    target_aware_outputs_present = (
        p11_out_dir.is_dir() and (p11_out_dir / "metrics_signal_mt.json").is_file()
    )

    predictive_metrics_available = False
    promoted = None
    promotion_reason = None
    if metrics_snapshot:
        predictive_metrics_available = bool(
            metrics_snapshot.get("predictive_metrics_available")
        )
        promoted = metrics_snapshot.get("promoted")
        promotion_reason = metrics_snapshot.get("promotion_reason", "")

    # Activation smoke passed iff all stages OK + metrics propagated
    activation_smoke_passed = (
        all_stages_passed
        and target_aware_outputs_present
        and predictive_metrics_available
    )

    if not target_aware_outputs_present:
        warnings.append("Target-aware P11 output directory or metrics_signal_mt.json missing.")
    if not predictive_metrics_available:
        warnings.append(
            "predictive_metrics_available is false — explicit targets did not propagate."
        )

    # Build target_aware_metrics_snapshot.json
    if metrics_snapshot is not None:
        snapshot_keys = [
            "predictive_metrics_available",
            "explicit_targets_available",
            "auc_m", "auc_mt", "delta_auc",
            "brier_m", "brier_mt",
            "ece_m", "ece_mt", "delta_ece",
            "promoted", "promotion_reason",
        ]
        metrics_out = {k: metrics_snapshot.get(k) for k in snapshot_keys}
    else:
        metrics_out = {
            "predictive_metrics_available": False,
            "explicit_targets_available": False,
            "auc_m": None, "auc_mt": None, "delta_auc": None,
            "brier_m": None, "brier_mt": None,
            "ece_m": None, "ece_mt": None, "delta_ece": None,
            "promoted": None,
            "promotion_reason": "metrics_signal_mt.json not found",
        }

    # Scan P15 outputs for banned phrases (after writing so we check the written content)
    # We'll write first, then scan and update guardrail report
    summary = {
        "dataset_id": dataset_id,
        "mock_fixture": mock_fixture,
        "p14_readiness_ran": any(r["stage"] == "p14_adapter_readiness" for r in stage_results),
        "p12_alignment_ran": any(r["stage"] == "p12_explicit_label_alignment" for r in stage_results),
        "p13_target_injection_ran": any(r["stage"] == "p13_target_injection" for r in stage_results),
        "p11_target_aware_ran": target_aware_outputs_present,
        "artifact_validation_ran": artifact_validation_ran,
        "target_aware_outputs_present": target_aware_outputs_present,
        "predictive_metrics_available": predictive_metrics_available,
        "promoted": promoted,
        "promotion_reason": promotion_reason,
        "activation_smoke_passed": activation_smoke_passed,
        "warnings": warnings,
    }

    # Write stage results (serialize commands as strings for JSON)
    stage_results_out = []
    for r in stage_results:
        sr = dict(r)
        sr["command"] = [str(x) for x in sr["command"]]
        stage_results_out.append(sr)

    # Write all artifacts
    (out / "activation_smoke_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    (out / "activation_stage_results.json").write_text(
        json.dumps(stage_results_out, indent=2), encoding="utf-8"
    )
    (out / "target_aware_metrics_snapshot.json").write_text(
        json.dumps(metrics_out, indent=2), encoding="utf-8"
    )

    # Scan after writing to catch any stray content
    banned_hits = _scan_banned_phrases(out_dir)
    guardrail_report = _build_guardrail_report(banned_hits)
    if banned_hits:
        activation_smoke_passed = False
        summary["activation_smoke_passed"] = False
        warnings.extend([f"Banned phrase found: {h}" for h in banned_hits])
        summary["warnings"] = warnings
        # Rewrite summary with updated status
        (out / "activation_smoke_summary.json").write_text(
            json.dumps(summary, indent=2), encoding="utf-8"
        )

    (out / "activation_guardrail_report.json").write_text(
        json.dumps(guardrail_report, indent=2), encoding="utf-8"
    )

    omega = _build_omega_event(dataset_id, activation_smoke_passed)
    (out / "omega_event.json").write_text(
        json.dumps(omega, indent=2), encoding="utf-8"
    )

    report = _build_report(dataset_id, summary, metrics_snapshot, guardrail_report)
    (out / "report.md").write_text(report, encoding="utf-8")

    # Print summary
    print()
    print(f"Activation smoke summary:")
    print(f"  predictive_metrics_available: {predictive_metrics_available}")
    print(f"  promoted: {promoted}")
    print(f"  promotion_reason: {promotion_reason}")
    print(f"  activation_smoke_passed: {activation_smoke_passed}")
    if warnings:
        for w in warnings:
            print(f"  WARNING: {w}")

    artifacts = [
        "activation_smoke_summary.json",
        "activation_stage_results.json",
        "target_aware_metrics_snapshot.json",
        "activation_guardrail_report.json",
        "omega_event.json",
        "report.md",
    ]
    print(f"\nWrote {len(artifacts)} output artifacts to: {out_dir}")

    return 0 if activation_smoke_passed else 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="P15 — Target-aware activation smoke pipeline."
    )
    parser.add_argument("--dataset-id", default="DS005620")
    parser.add_argument("--root", default="outputs/btc_icft")
    parser.add_argument(
        "--out", default="outputs/btc_icft/target_aware_activation/DS005620"
    )
    parser.add_argument("--mock-fixture", action="store_true")
    parser.add_argument("--validate-artifacts", action="store_true")
    parser.add_argument(
        "--keep-intermediate", action="store_true", default=True
    )
    args = parser.parse_args()
    return run(
        dataset_id=args.dataset_id,
        root=args.root,
        out_dir=args.out,
        mock_fixture=args.mock_fixture,
        validate_artifacts=args.validate_artifacts,
        keep_intermediate=args.keep_intermediate,
    )


if __name__ == "__main__":
    sys.exit(main())
