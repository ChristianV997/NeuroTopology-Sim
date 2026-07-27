from pathlib import Path
import json
import numpy as np
import pytest

from physics.exact_dynamics.cloud_snapshot import load_cloud_snapshot
from physics.exact_dynamics.cross_validation import compare_density_trajectories, second_order_local_error
from physics.exact_dynamics.lindblad_reference import LindbladReferenceConfig, propagate_lindblad, validate_density_trajectory
from scripts.run_cloud_payload import run


def _snapshot(path: Path, *, pairs: np.ndarray | None = None) -> Path:
    hamiltonian = np.array([[1.0e-20, 2.0e-22j], [-2.0e-22j, 1.1e-20]], complex)
    np.savez(path, H_sys_si=hamiltonian, hamiltonian_unit=np.array("J"), site_couplings_si=hamiltonian - np.diag(np.diag(hamiltonian)),
             boundary_configuration=np.array(json.dumps({"periodic": True})), active_site_pairs=np.array([[0, 1]] if pairs is None else pairs))
    return path


def test_snapshot_contract_loads_current_pairs_and_rejects_bad_shapes(tmp_path: Path) -> None:
    snapshot = load_cloud_snapshot(_snapshot(tmp_path / "valid.npz"))
    assert snapshot.active_site_pairs == ((0, 1),)
    invalid = tmp_path / "invalid.npz"; np.savez(invalid, H_sys_si=np.eye(2), hamiltonian_unit=np.array("J"))
    with pytest.raises(ValueError): load_cloud_snapshot(invalid)


@pytest.mark.parametrize("tau_s", [1.76e-9, 0.95e-9])
def test_lindblad_amplitude_decay_matches_target_relaxation_limits(tau_s: float) -> None:
    hamiltonian = np.zeros((2, 2), complex); initial = np.diag([0.0, 1.0])
    states = propagate_lindblad(hamiltonian, initial, np.array([0.0, tau_s]), LindbladReferenceConfig(tau_s))
    validate_density_trajectory(states)
    assert abs(states[-1, 1, 1].real - np.exp(-1.0)) < 1e-4


def test_second_order_suzuki_local_error_has_cubic_scaling() -> None:
    x = np.array([[0., 1.], [1., 0.]])
    z = np.array([[1., 0.], [0., -1.]])
    coarse = second_order_local_error((x, z), 1e-2, 1.0)
    fine = second_order_local_error((x, z), 5e-3, 1.0)
    assert coarse > fine > 0
    assert 6.0 < coarse / fine < 10.0


def test_cloud_telemetry_comparison_rejects_unphysical_state() -> None:
    valid = np.array([np.diag([1.0, 0.0]), np.diag([0.9, 0.1])], complex)
    result = compare_density_trajectories(valid, valid.copy())
    assert result.valid and result.max_frobenius_error == 0.0
    broken = valid.copy(); broken[-1, 0, 0] = 1.1
    with pytest.raises(ValueError): compare_density_trajectories(valid, broken)


def test_payload_runner_records_failure_for_invalid_snapshot(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid.npz"; np.savez(invalid, H_sys_si=np.eye(2))
    with pytest.raises(ValueError): run(invalid, np.array([0.0]), tmp_path / "telemetry")
    assert (tmp_path / "telemetry" / "cloud_failure.json").is_file()
