"""Assemble one ecosystem-integration run: discover -> preflight -> ingest ->
analyze -> validate -> package.

Owned by claude/ecosystem-integration (tools/integration_bridge/**,
configs/integration/**). This script never re-implements a scientific
computation: every numeric result comes from an existing public adapter
already on `main` (see configs/integration/dependency_matrix.yaml's
`consumed_public_adapters`), and every stage boundary here is a thin,
inspectable wrapper around those calls.

Hard guardrails enforced by this script (see docs/integration_acceptance.md
for the full list and why each one lives where it does):
  - RunRecordV1 remains canonical: `package` writes exactly one RunRecordV1
    per run, using `runs.run_record.RunRecordV1.make`/`build_run_id`
    unmodified.
  - HypothesisSpec remains the governance input: an optional `--spec` path
    is validated via `governance.validate.validate_spec` before anything
    else runs.
  - No hidden network / no automatic downloads: `preflight` refuses live
    mode unless both `--allow-network` and the
    `NTS_INTEGRATION_ALLOW_NETWORK` environment variable are set; ingestion
    only ever reads local files.
  - No dashboard-side solver execution: this script is never imported by
    `apps/awareness_studio` (enforced by
    tests/integration/test_no_solver_import_from_dashboard.py).
  - Synthetic data cannot produce an empirical PASS: enforced by
    `tools.integration_bridge.quality_gate.classify_status`.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from governance.io import load_spec  # noqa: E402
from governance.validate import ValidationError, validate_spec  # noqa: E402
from runs.run_record import RunRecordV1, build_run_id  # noqa: E402

from tools.integration_bridge import (  # noqa: E402
    artifact_manifest,
    capabilities,
    preflight,
    quality_gate,
    reporting,
    run_plan,
)

STAGES = ("discover", "preflight", "ingest", "analyze", "validate", "package")


def _load_signal(*, data_mode: str, input_path: Optional[Path], seed: int, n_samples: int):
    """Isolated ingestion helper -- the one function a future streaming
    adapter (antigravity/mne-scipy-streaming-eeg, currently unavailable;
    see configs/integration/dependency_matrix.yaml) replaces. Everything
    else in this script is agnostic to how the signal array was produced.
    """
    import numpy as np

    from sim.pitnn.ingest_empirical import empirical_to_macro_signal, ingest_empirical
    from sim.pitnn.mumax3_macro_tda import synthetic_signal

    if data_mode == "synthetic":
        return synthetic_signal(n_samples, seed), "synthetic_demo"
    if input_path is None:
        raise ValueError(f"data_mode={data_mode!r} requires --input-path")
    empirical_signal = ingest_empirical(input_path, sample_rate_hz=250.0)
    return empirical_to_macro_signal(empirical_signal), data_mode


def _run_analysis(signal, sample_rate_hz: float, plan: run_plan.RunPlan) -> Dict[str, Any]:
    """Invoke each planned step through its public adapter. Returns a dict
    namespaced exactly per quality_gate.TOPOLOGY_NAMESPACES plus a
    top-level 'bayesian_falsification' key -- never a flattened merge."""
    import numpy as np

    result: Dict[str, Any] = {}
    step_names = {step.name for step in plan.steps}

    if "spatial_winding_and_charge" in step_names:
        from core.topology import compute_f_dress, compute_Qz

        # Reuse the same deterministic phase-field construction pattern
        # documented in sim.pitnn.bayesian_falsification's _rg_condition
        # (map a real scalar signal to a unit-phase field) rather than
        # inventing a new one; kept 1-slice deep since this stage's job is
        # to expose core.topology's adapter, not to explore field shapes.
        phase = np.angle(np.exp(1j * signal))
        field3d = np.exp(1j * phase).reshape(1, -1, 1)
        if field3d.shape[1] >= 2:
            qz, qabs = compute_Qz(field3d.repeat(2, axis=2))
            result["spatial_topology"] = {
                "Qz_mean": float(np.mean(qz)),
                "Qabs_mean": float(np.mean(qabs)),
                "f_dress": compute_f_dress(qz, qabs),
            }

    if "graph_beta1" in step_names:
        from analysis.connectivity_topology import compute_beta1

        n = signal.size
        if n >= 3:
            # A minimal synthetic PLV-like similarity matrix derived from
            # the same signal, purely to exercise the public adapter
            # end-to-end; a real multi-channel PLV matrix is the caller's
            # responsibility upstream of this integration.
            phase = np.angle(np.exp(1j * signal))
            plv = np.abs(np.cos(phase[:, None] - phase[None, :]))
            result["graph_topology"] = {"beta1": int(compute_beta1(plv))}

    if "scalar_chirality_and_beta1_proxy" in step_names:
        from sim.pitnn.topological_invariants import TopologicalInvariantTracker

        n = max(3, min(signal.size, 64))
        spins = np.zeros((n, 3))
        angles = np.angle(np.exp(1j * signal[:n])) if signal.size >= n else np.linspace(0, 2 * np.pi, n)
        spins[:, 0] = np.cos(angles)
        spins[:, 1] = np.sin(angles)
        spins[:, 2] = 0.0
        tracker = TopologicalInvariantTracker(n)
        result["scalar_chirality"] = tracker.audit_snapshot(spins)

    if "bayesian_falsification" in step_names:
        from sim.pitnn.bayesian_falsification import compare_models
        from sim.pitnn.mumax3_macro_tda import invert_macro_signal

        inversion = invert_macro_signal(signal, sample_rate_hz)
        result["bayesian_falsification"] = {
            "inversion": inversion,
            "comparison": compare_models(signal, inversion),
        }

    return result


def _numeric_fields_for_check(analysis_result: Dict[str, Any]) -> list[float]:
    values: list[float] = []
    for namespace in quality_gate.TOPOLOGY_NAMESPACES:
        payload = analysis_result.get(namespace)
        if isinstance(payload, dict):
            values.extend(v for v in payload.values() if isinstance(v, (int, float)))
    bayes = analysis_result.get("bayesian_falsification")
    if isinstance(bayes, dict):
        comparison = bayes.get("comparison", {})
        if isinstance(comparison, dict):
            for key in ("bayes_factor", "log_bayes_factor"):
                if key in comparison:
                    values.append(comparison[key])
    return values


def assemble(
    *,
    data_mode: str,
    input_path: Optional[Path],
    output_dir: Path,
    seed: int = 0,
    n_samples: int = 256,
    dataset_id: str = "unspecified",
    spec_path: Optional[Path] = None,
    live: bool = False,
    allow_network: bool = False,
    requested_steps: Optional[tuple[str, ...]] = None,
) -> Dict[str, Any]:
    durations: Dict[str, float] = {}

    # ---- discover ----
    stage_start = time.monotonic()
    env_info = capabilities.collect_environment_info()
    durations["discover"] = time.monotonic() - stage_start

    if spec_path is not None:
        spec = load_spec(spec_path)
        try:
            validate_spec(spec)
        except ValidationError as exc:
            raise ValidationError(exc.spec_id, exc.errors) from exc

    # ---- preflight ----
    stage_start = time.monotonic()
    metadata = {"data_mode": data_mode, "dataset_id": dataset_id, "seed": seed}
    plan = run_plan.build_plan(env_info.adapters, requested_steps)
    # Only steps the caller *explicitly* named (via requested_steps) are a
    # hard preflight requirement -- if any of those specific steps is
    # unavailable, that is a real refusal-worthy gap. Steps run_plan
    # skipped on its own (the default "run everything available" mode)
    # are an intentional graceful degradation, not a preflight failure;
    # they are still visible in the plan and the final report.
    if requested_steps is not None:
        requested_adapter_names = tuple(
            step.adapter for step in plan.steps + plan.skipped if step.name in set(requested_steps)
        )
    else:
        requested_adapter_names = ()
    preflight_report = preflight.run_preflight(
        input_path=input_path,
        output_dir=output_dir,
        metadata=metadata,
        requested_adapters=requested_adapter_names,
        adapters_available=env_info.adapters,
        live_requested=live,
        allow_network_flag=allow_network,
    )
    durations["preflight"] = time.monotonic() - stage_start
    if not preflight_report.ok:
        return {
            "run_id": None,
            "status": "ERROR",
            "preflight": preflight_report.to_dict(),
            "stage_durations_s": durations,
        }

    # ---- ingest ----
    stage_start = time.monotonic()
    exception_occurred = False
    insufficient_data = False
    analysis_result: Dict[str, Any] = {}
    raw_status: Optional[str] = None
    try:
        signal, resolved_source_kind = _load_signal(
            data_mode=data_mode, input_path=input_path, seed=seed, n_samples=n_samples
        )
    except ValueError:
        insufficient_data = True
        signal, resolved_source_kind = None, data_mode
    durations["ingest"] = time.monotonic() - stage_start

    # ---- analyze ----
    stage_start = time.monotonic()
    if signal is not None:
        try:
            analysis_result = _run_analysis(signal, sample_rate_hz=250.0, plan=plan)
            bayes = analysis_result.get("bayesian_falsification", {})
            comparison = bayes.get("comparison", {}) if isinstance(bayes, dict) else {}
            raw_status = comparison.get("verdict")
        except (ValueError, ImportError):
            exception_occurred = True
    durations["analyze"] = time.monotonic() - stage_start

    # ---- validate ----
    stage_start = time.monotonic()
    provenance = {
        "data_mode": data_mode,
        "dataset_id": dataset_id,
        "source_kind": resolved_source_kind,
        "seed": seed,
    }
    status, quality_report = quality_gate.evaluate(
        analysis_result=analysis_result,
        provenance=provenance,
        raw_status=raw_status,
        exception_occurred=exception_occurred,
        insufficient_data=insufficient_data,
        numeric_fields=_numeric_fields_for_check(analysis_result),
    )
    durations["validate"] = time.monotonic() - stage_start

    # ---- package ----
    stage_start = time.monotonic()
    output_dir.mkdir(parents=True, exist_ok=True)
    inputs_for_id = {"data_mode": data_mode, "dataset_id": dataset_id, "seed": seed, "n_samples": n_samples}
    run_id = build_run_id(
        "ecosystem_integration", "NeuroTopology-Sim", "working-tree",
        ["scripts/assemble_ecosystem_run.py"], inputs_for_id, {},
    )
    record = RunRecordV1.make(
        run_id, "ecosystem_integration",
        elapsed_s=sum(durations.values()),
        data_mode=data_mode, dataset_id=dataset_id, verdict=status,
        metrics={"analysis": analysis_result, "quality": quality_report.to_dict()},
        source="scripts/assemble_ecosystem_run.py",
    )
    record.input = inputs_for_id
    record.notes = (
        "Ecosystem-integration assembly run. Scientific computation is "
        "delegated entirely to existing public adapters; see "
        "configs/integration/dependency_matrix.yaml."
    )
    record.artifacts = {
        "quality_report": "quality_report.json",
        "summary": "summary.md",
        "manifest": "manifest.json",
    }
    record_path = record.write_json(output_dir / "RunRecord.json")

    quality_path = output_dir / "quality_report.json"
    quality_path.write_text(json.dumps(quality_report.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")

    summary_path = output_dir / "summary.md"
    summary_path.write_text(
        reporting.render_markdown_summary(
            run_id=run_id, status=status, provenance=provenance,
            quality_report=quality_report.to_dict(), plan=plan.to_dict(),
            stage_durations_s=durations,
        ),
        encoding="utf-8",
    )

    manifest = artifact_manifest.build_manifest(
        run_id=run_id, output_dir=output_dir,
        artifact_relative_paths=["RunRecord.json", "quality_report.json", "summary.md"],
        metadata={"data_mode": data_mode, "dataset_id": dataset_id, "environment": env_info.to_dict()},
    )
    manifest_path = artifact_manifest.write_manifest(manifest, output_dir / "manifest.json")
    durations["package"] = time.monotonic() - stage_start

    return {
        "run_id": run_id,
        "status": status,
        "artifacts": {
            "run_record": str(record_path),
            "quality_report": str(quality_path),
            "summary": str(summary_path),
            "manifest": str(manifest_path),
        },
        "stage_durations_s": durations,
        "environment": env_info.to_dict(),
    }


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-mode", choices=("synthetic", "empirical_local", "empirical_csv"), default="synthetic")
    parser.add_argument("--input-path", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/ecosystem_integration"))
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--n-samples", type=int, default=256)
    parser.add_argument("--dataset-id", default="unspecified")
    parser.add_argument("--spec", type=Path, default=None, help="optional HypothesisSpec YAML/JSON")
    parser.add_argument("--live", action="store_true", help="request network/live mode (refused by default)")
    parser.add_argument("--allow-network", action="store_true", help="explicit opt-in required alongside --live")
    args = parser.parse_args(argv)

    result = assemble(
        data_mode=args.data_mode, input_path=args.input_path, output_dir=args.output_dir,
        seed=args.seed, n_samples=args.n_samples, dataset_id=args.dataset_id,
        spec_path=args.spec, live=args.live, allow_network=args.allow_network,
    )
    print(json.dumps({"run_id": result["run_id"], "status": result["status"]}, sort_keys=True))
    return 0 if result["status"] != "ERROR" else 1


if __name__ == "__main__":
    raise SystemExit(main())
