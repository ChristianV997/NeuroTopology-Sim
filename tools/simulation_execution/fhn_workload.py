"""Registered, bounded adapter for the repository's existing FHN solver.

This module is an execution workload, not a new solver.  It validates a small
local specification, invokes the existing deterministic implementation in a
child process, and writes only finite engineering artifacts.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sys
from typing import Any, Mapping

from .finite import write_atomic_json

MAX_STEPS = 4096
MAX_SPEC_BYTES = 64 * 1024
SOURCE = "sim.pitnn.hodgkin_huxley_ciss.simulate_fhn"
DATASET_ID = "synthetic-fhn-model"
EVIDENCE_CLASS = "synthetic_demo_only"
CREATED_AT = "1970-01-01T00:00:00+00:00"
LIMITATIONS = [
    "Synthetic model output, not recorded neural data or biological validation.",
    "The existing solver min-max normalizes its voltage over the complete trajectory.",
    "The voltage output is therefore not a causal online observation or independently calibrated voltage.",
    "Seed is recorded for reproducibility; this deterministic model uses no random draws.",
]

_CONFIG_KEYS = frozenset(
    {"duration_s", "dt_s", "input_current", "resting_potential_V", "spike_scale_V"}
)


def validate_spec(spec: Mapping[str, Any]) -> None:
    """Reject malformed, non-finite, or unbounded workload specifications."""
    if set(spec) != {"schema", "run_id", "code_commit", "seed", "configuration"}:
        raise ValueError("invalid FHN workload schema")
    if spec.get("schema") != "NTS.FHNWorkload.v1":
        raise ValueError("invalid FHN workload schema")

    run_id = spec.get("run_id")
    if not isinstance(run_id, str) or not run_id or Path(run_id).name != run_id:
        raise ValueError("run_id must be a path-safe identity")
    code_commit = spec.get("code_commit")
    if not isinstance(code_commit, str) or not code_commit.strip() or code_commit.lower() in {"unknown", "null", "none"}:
        raise ValueError("explicit code revision required")
    if type(spec.get("seed")) is not int:
        raise ValueError("integer seed required")

    configuration = spec.get("configuration")
    if not isinstance(configuration, dict) or set(configuration) != _CONFIG_KEYS:
        raise ValueError("all FHN parameters must be explicit")
    if any(type(value) not in (int, float) or not math.isfinite(float(value)) for value in configuration.values()):
        raise ValueError("FHN parameters must be finite numbers")
    if configuration["duration_s"] <= 0 or configuration["dt_s"] <= 0:
        raise ValueError("FHN duration and timestep must be positive")
    if configuration["duration_s"] / configuration["dt_s"] > MAX_STEPS:
        raise ValueError("FHN workload exceeds step bound")


def _read_reviewed_spec(path: Path, expected_sha256: str) -> dict[str, Any]:
    raw = path.read_bytes()
    if len(raw) > MAX_SPEC_BYTES:
        raise ValueError("spec exceeds 64 KiB")
    actual_sha256 = hashlib.sha256(raw).hexdigest()
    if actual_sha256 != expected_sha256:
        raise ValueError("reviewed specification checksum mismatch")
    try:
        spec = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid FHN specification JSON: {exc}") from exc
    if not isinstance(spec, dict):
        raise ValueError("FHN specification must be a JSON object")
    validate_spec(spec)
    return spec


def prepare_spec(
    path: Path,
    *,
    run_id: str,
    code_commit: str,
    seed: int,
    configuration: dict[str, Any],
):
    """Write an explicit spec and return the exact registered workload.

    Preparation never imports or invokes the solver.  A reviewed spec is
    immutable: callers must choose a new path to change it.
    """
    spec = {
        "schema": "NTS.FHNWorkload.v1",
        "run_id": run_id,
        "code_commit": code_commit,
        "seed": seed,
        "configuration": dict(configuration),
    }
    validate_spec(spec)
    from awareness_studio.simulation_bridge import RegisteredWorkload

    path = Path(path)
    if path.exists():
        raise FileExistsError("spec already exists; use the existing reviewed spec or a new path")
    write_atomic_json(path, spec)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    script = Path(__file__).resolve().parents[2] / "scripts" / "run_registered_fhn.py"
    workload = RegisteredWorkload(
        "synthetic-fhn",
        (
            sys.executable,
            str(script),
            str(path.resolve()),
            digest,
        ),
        ("unit_manifest.json", "RunRecord.json", "summary.json", "trajectory.json"),
    )
    return workload, digest


def execute_spec(path: Path, expected_sha256: str, output_dir: Path) -> None:
    """Execute a reviewed spec and write the finite artifact set."""
    spec = _read_reviewed_spec(Path(path), expected_sha256)

    # These imports deliberately occur in the registered child workload, after
    # the canonical runner has applied its process/resource/network controls.
    import numpy as np

    from runs.run_record import RunRecordV1
    from sim.pitnn.hodgkin_huxley_ciss import FHNConfig, simulate_fhn

    config = FHNConfig(**spec["configuration"])
    times, voltage, recovery = simulate_fhn(config)
    if not all(np.all(np.isfinite(array)) for array in (times, voltage, recovery)):
        raise ValueError("solver produced non-finite output")

    metrics = {
        "sample_count": int(times.size),
        "model_voltage_mean_V": float(voltage.mean()),
        "model_voltage_min_V": float(voltage.min()),
        "model_voltage_max_V": float(voltage.max()),
        "recovery_final": float(recovery[-1]),
    }
    trajectory = {
        "time_s": times.tolist(),
        "model_voltage_V": voltage.tolist(),
        "recovery": recovery.tolist(),
    }
    run_id = spec["run_id"]
    input_identity = expected_sha256
    record = RunRecordV1.make(
        run_id,
        "synthetic_fhn",
        data_mode="synthetic",
        dataset_id=DATASET_ID,
        source=SOURCE,
        metrics=metrics,
        artifacts={"summary": "summary.json", "trajectory": "trajectory.json"},
        _now=datetime.fromisoformat(CREATED_AT),
    ).to_dict()
    record.update(
        {
            "git_commit": spec["code_commit"],
            "seed": spec["seed"],
            "input_identity": input_identity,
            "input": {
                "identity": input_identity,
                "configuration": dict(spec["configuration"]),
                "seed": spec["seed"],
            },
            "configuration": asdict(config),
            "synthetic": True,
            "evidence_class": EVIDENCE_CLASS,
            "scientific_pass": False,
            "formal_bayes_factor": None,
            "limitations": list(LIMITATIONS),
        }
    )
    summary = {
        "schema": "NTS.FHNSummary.v1",
        "run_id": run_id,
        "metrics": metrics,
        "evidence_class": EVIDENCE_CLASS,
        "scientific_pass": False,
        "formal_bayes_factor": None,
        "limitations": list(LIMITATIONS),
    }
    unit_manifest = {
        "schema": "NTS.FHNUnitManifest.v1",
        "work_unit_id": run_id,
        "run_id": run_id,
        "complete": True,
        "expected_outputs": ["unit_manifest.json", "RunRecord.json", "summary.json", "trajectory.json"],
        "evidence_class": EVIDENCE_CLASS,
    }

    output_dir = Path(output_dir)
    write_atomic_json(output_dir / "trajectory.json", trajectory)
    write_atomic_json(output_dir / "summary.json", summary)
    write_atomic_json(output_dir / "RunRecord.json", record)
    # Completion is written last so a missing/incomplete manifest cannot be
    # mistaken for a completed bounded work unit.
    write_atomic_json(output_dir / "unit_manifest.json", unit_manifest)
