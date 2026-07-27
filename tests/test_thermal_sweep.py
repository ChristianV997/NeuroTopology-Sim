"""Offline tests for DM1 thermal orchestration and fail-closed fallback labels."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from physics.exact_dynamics.aws_routing import S3Routing
from scripts.run_thermal_sweep import relaxation_time_s, run_thermal_sweep


def _snapshot(path: Path) -> Path:
    hamiltonian = np.array([[0.0, 2.0e-25j], [-2.0e-25j, 1.0e-24]], complex)
    np.savez(
        path,
        H_sys_si=hamiltonian,
        hamiltonian_unit=np.array("J"),
        site_couplings_si=hamiltonian,
        boundary_configuration=np.array(json.dumps({"periodic": True})),
        active_site_pairs=np.array([[0, 1]]),
    )
    return path


def test_relaxation_time_matches_declared_temperature_anchors() -> None:
    assert relaxation_time_s(10.0) == 1.76e-9
    assert relaxation_time_s(310.0) == 0.95e-9
    assert 0.95e-9 < relaxation_time_s(160.0) < 1.76e-9


def test_thermal_sweep_writes_explicit_local_reference_when_preflight_fails(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("scripts.run_thermal_sweep.resolve_s3_routing", lambda **_: (_ for _ in ()).throw(RuntimeError("no AWS credentials")))
    payload = run_thermal_sweep(_snapshot(tmp_path / "input.npz"), [10.0, 310.0], tmp_path / "telemetry")
    assert (tmp_path / "telemetry" / "thermal_sweep_summary.json").is_file()
    assert [record["telemetry"]["verdict"] for record in payload["records"]] == ["LOCAL_REFERENCE_ONLY", "LOCAL_REFERENCE_ONLY"]
    for record in payload["records"]:
        density = record["telemetry"]["density_matrix_telemetry"][-1]
        assert abs(density["trace"] - 1.0) < 1e-10
        assert density["minimum_eigenvalue"] >= -1e-10


def test_s3_routing_exposes_braket_tuple() -> None:
    routing = S3Routing(bucket="result-bucket", prefix="sciencerd/1/us-east-1/test", region="us-east-1", account_id="1")
    assert routing.destination_folder == ("result-bucket", "sciencerd/1/us-east-1/test")
