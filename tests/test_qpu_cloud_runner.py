from pathlib import Path
import importlib.util
import numpy as np
import pytest

from physics.exact_dynamics.qpu_cloud_runner import DM1_ARN, QpuCloudConfig, QuantumCloudEvaluator


def test_dm1_is_default_and_density_telemetry_requires_zero_shots() -> None:
    assert QpuCloudConfig().device_arn == DM1_ARN
    with pytest.raises(ValueError): QpuCloudConfig(shots=1)


def test_missing_tddft_input_fails_closed_with_falsification_prefix(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="FALSIFIED: NOISE_DOMINANT"):
        QuantumCloudEvaluator(tmp_path / "missing.npz")


def test_missing_braket_sdk_fails_closed_before_cloud_execution(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "hamiltonian.npz"
    np.savez(path, H_sys_si=np.array([[1e-20, 0], [0, 1.1e-20]], complex), hamiltonian_unit=np.array("J"))
    real_find_spec = importlib.util.find_spec

    def missing_sdk(module: str):
        if module == "braket" or module.startswith("braket."):
            return None
        return real_find_spec(module)

    monkeypatch.setattr(importlib.util, "find_spec", missing_sdk)
    with pytest.raises(RuntimeError, match="FALSIFIED: NOISE_DOMINANT"):
        QuantumCloudEvaluator(path)


def test_two_site_compact_encoding_builds_current_circuit(tmp_path: Path) -> None:
    path = tmp_path / "hamiltonian.npz"
    np.savez(path, H_sys_si=np.array([[1e-20, 2e-22j], [-2e-22j, 1.1e-20]], complex), hamiltonian_unit=np.array("J"))
    evaluator = QuantumCloudEvaluator(path, QpuCloudConfig(max_qubits=1, chiral_pairs=((0, 1),)))
    assert evaluator.build_circuit(1e-10).instructions
