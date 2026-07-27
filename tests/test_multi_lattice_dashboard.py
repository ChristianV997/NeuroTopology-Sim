from pathlib import Path
import numpy as np

from fastapi import FastAPI
from fastapi.testclient import TestClient

from dashboard.adapters.artifact_reader import ArtifactReader
from physics.open_quantum import LatticeConfig, ThermalBathConfig
from physics.open_quantum.multi_lattice import MultiLatticeConfig, coupled_lattice
from server.routes.artifacts import build_artifact_router


def test_coupled_lattice_trace_is_preserved() -> None:
    bath = ThermalBathConfig(radiative_rate_s=1e6, dephasing_rate_s=1e6, metabolic_pump_rate_s=1e6)
    model = coupled_lattice(LatticeConfig(n_layers=1, interaction_cutoff_m=30e-9, bath=bath), MultiLatticeConfig(10e-9))
    rho = np.eye(model.dimension, dtype=complex) / model.dimension
    assert model.dimension == 27
    assert model.trace_residual(rho) < 1e-5


def test_artifact_routes_read_static_files_only(tmp_path: Path) -> None:
    science, neuro = tmp_path / "science", tmp_path / "neuro"
    target = science / "artifacts" / "open_quantum" / "pdb_disorder_benchmark"; target.mkdir(parents=True)
    (target / "decoherence_sweep.json").write_text('{"schema":"OpenQuantumDecoherenceSweep"}', encoding="utf-8")
    app = FastAPI(); app.include_router(build_artifact_router(science, neuro))
    response = TestClient(app).get("/api/artifacts/quantum-sweeps")
    assert response.status_code == 200
    assert response.json()["payload"]["schema"] == "OpenQuantumDecoherenceSweep"
    assert ArtifactReader(science, neuro).read("quantum_sweeps").payload["schema"] == "OpenQuantumDecoherenceSweep"
