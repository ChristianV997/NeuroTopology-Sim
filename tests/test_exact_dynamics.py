from pathlib import Path
import numpy as np
import pytest

from physics.exact_dynamics import load_pdb_ensemble, load_electronic_inputs, build_single_excitation_hamiltonian, FalsificationConfig, evaluate_falsification
from physics.exact_dynamics.dynamics_solver import DynamicsResult, OptionalBackendUnavailable, available_backends, run_oqupy_pt_tempo


def _pdb_line(serial: int, atom: str, residue: int, x: float, y: float, z: float) -> str:
    return f"ATOM  {serial:5d} {atom:<4s} TRP A{residue:4d}    {x:8.3f}{y:8.3f}{z:8.3f}  1.00 20.00           C\n"


def _inputs(tmp_path: Path):
    pdb = tmp_path / "conformer.pdb"
    pdb.write_text("".join([_pdb_line(1, "CG", 1, 0, 0, 0), _pdb_line(2, "CD1", 1, 1, 0, 0), _pdb_line(3, "CE2", 1, 0, 1, 0), _pdb_line(4, "CG", 2, 10, 0, 0), _pdb_line(5, "CD1", 2, 11, 0, 0), _pdb_line(6, "CE2", 2, 10, 1, 0)]), encoding="utf-8")
    ensemble = load_pdb_ensemble([pdb])
    npz = tmp_path / "electronic.npz"
    np.savez(npz, site_ids=np.array(["A:1:_", "A:2:_"]), site_energies_eV=np.array([4.4, 4.5]), transition_dipoles_debye=np.array([[1., 0., 0.], [0., 1., 0.]]))
    return ensemble, load_electronic_inputs(npz)


def test_local_qm_inputs_build_deterministic_hermitian_hamiltonian(tmp_path: Path) -> None:
    ensemble, electronic = _inputs(tmp_path); _, sites = ensemble.sample(1)
    model = build_single_excitation_hamiltonian(sites, electronic, dielectric_constant=4.0, cutoff_m=2e-9)
    assert np.allclose(model.hamiltonian_J, model.hamiltonian_J.conj().T)
    assert len(model.checksum_sha256) == 64


def test_missing_exact_backend_never_silently_falls_back(tmp_path: Path) -> None:
    ensemble, electronic = _inputs(tmp_path); _, sites = ensemble.sample(1); model = build_single_excitation_hamiltonian(sites, electronic, dielectric_constant=4., cutoff_m=2e-9)
    if not available_backends()["oqupy_pt_tempo"]:
        with pytest.raises(OptionalBackendUnavailable): run_oqupy_pt_tempo(model, np.diag([1., 0.]), np.array([0., 1e-15]), None)  # type: ignore[arg-type]


def test_only_converged_ab_initio_noise_dominance_can_falsify() -> None:
    states = np.array([[[1., .5], [.5, 0.]], [[1., 0.01], [0.01, 0.]]], complex)
    result = DynamicsResult(np.array([0., 0.5e-12]), states, "oqupy_pt_tempo", True, 0., 0., "test")
    verdict = evaluate_falsification(result, ab_initio_inputs=True, config=FalsificationConfig())
    assert verdict["verdict"] == "FALSIFIED: NOISE_DOMINANT"
