"""Bounded synthetic adapter for the repository's existing FHN implementation."""
from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path
import sys

from .finite import write_atomic_json

MAX_STEPS = 4096
SOURCE = "sim.pitnn.hodgkin_huxley_ciss.simulate_fhn"
DATASET_ID = "synthetic-fhn-model"
LIMITATIONS = [
    "Synthetic model output, not recorded neural data or biological validation.",
    "The existing solver min-max normalizes its voltage over the complete trajectory.",
    "The voltage output is therefore not a causal online observation or independently calibrated voltage.",
    "Seed is recorded for reproducibility; this deterministic model uses no random draws.",
]


def validate_spec(spec):
    if set(spec) != {"schema", "run_id", "code_commit", "seed", "configuration"} or spec["schema"] != "NTS.FHNWorkload.v1":
        raise ValueError("invalid FHN workload schema")
    if not isinstance(spec["run_id"], str) or not spec["run_id"] or Path(spec["run_id"]).name != spec["run_id"]:
        raise ValueError("run_id must be a path-safe identity")
    if not isinstance(spec["code_commit"], str) or not spec["code_commit"].strip() or spec["code_commit"] == "unknown":
        raise ValueError("explicit code revision required")
    if type(spec["seed"]) is not int:
        raise ValueError("integer seed required")
    config = spec["configuration"]
    expected = {"duration_s", "dt_s", "input_current", "resting_potential_V", "spike_scale_V"}
    if not isinstance(config, dict) or set(config) != expected:
        raise ValueError("all FHN parameters must be explicit")
    if any(type(v) not in (int, float) or not math.isfinite(v) for v in config.values()):
        raise ValueError("FHN parameters must be finite numbers")
    if config["duration_s"] <= 0 or config["dt_s"] <= 0 or config["duration_s"] / config["dt_s"] > MAX_STEPS:
        raise ValueError("FHN workload exceeds step bound or has invalid timestep")


def prepare_spec(path: Path, *, run_id: str, code_commit: str, seed: int, configuration: dict):
    """Write an explicit synthetic spec and return its exact registered workload.

    Preparing the spec never invokes the model. Execution remains a separate
    authorized Orchestrator.run_registered request.
    """
    from awareness_studio.simulation_bridge import RegisteredWorkload
    spec = {"schema": "NTS.FHNWorkload.v1", "run_id": run_id, "code_commit": code_commit,
            "seed": seed, "configuration": configuration}
    validate_spec(spec)
    if path.exists():
        raise FileExistsError("spec already exists; use the existing reviewed spec or a new path")
    write_atomic_json(path, spec)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    script = Path(__file__).resolve().parents[2] / "scripts" / "run_registered_fhn.py"
    workload = RegisteredWorkload("synthetic-fhn", (sys.executable, str(script), str(path.resolve()), digest),
                                  ("unit_manifest.json", "RunRecord.json", "summary.json", "trajectory.json"))
    return workload, digest


def execute_spec(path: Path, expected_sha256: str, output_dir: Path):
    with path.open("rb") as handle:
        raw = handle.read(64 * 1024 + 1)
    if len(raw) > 64 * 1024:
        raise ValueError("spec exceeds 64 KiB")
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError("reviewed specification checksum mismatch")
    spec = json.loads(raw)
    validate_spec(spec)
    import numpy as np
    from sim.pitnn.hodgkin_huxley_ciss import FHNConfig, simulate_fhn
    from runs.run_record import RunRecordV1
    config = FHNConfig(**spec["configuration"])
    times, voltage, recovery = simulate_fhn(config)
    if not all(np.all(np.isfinite(a)) for a in (times, voltage, recovery)):
        raise ValueError("solver produced non-finite output")
    metrics = {"sample_count": int(times.size), "model_voltage_mean_V": float(voltage.mean()),
               "model_voltage_min_V": float(voltage.min()), "model_voltage_max_V": float(voltage.max()),
               "recovery_final": float(recovery[-1])}
    trajectory = {"time_s": times.tolist(), "model_voltage_V": voltage.tolist(), "recovery": recovery.tolist()}
    record = RunRecordV1.make(spec["run_id"], "synthetic_fhn", data_mode="synthetic",
                              dataset_id=DATASET_ID, source=SOURCE, metrics=metrics,
                              artifacts={"summary": "summary.json", "trajectory": "trajectory.json"}).to_dict()
    record.update(git_commit=spec["code_commit"], seed=spec["seed"], input_identity=expected_sha256,
                  synthetic=True, evidence_class="synthetic_demo_only", configuration=asdict(config),
                  scientific_pass=False, formal_bayes_factor=None, limitations=LIMITATIONS)
    write_atomic_json(output_dir / "trajectory.json", trajectory)
    write_atomic_json(output_dir / "summary.json", {"metrics": metrics, "limitations": LIMITATIONS,
                                                   "evidence_class": "synthetic_demo_only"})
    write_atomic_json(output_dir / "RunRecord.json", record)
    write_atomic_json(output_dir / "unit_manifest.json", {"work_unit_id": spec["run_id"], "complete": True})
