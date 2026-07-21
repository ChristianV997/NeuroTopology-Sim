from __future__ import annotations
import numpy as np
import pytest
from core.defects import detect_defects
from core.topology import compute_Qz
from validation.synthetic import (
    single_vortex, double_vortex, perturbed_vortex, validate_vortex_charges,
    cgl_step, cgl_defect_field, kuramoto_vortex_field, validate_dynamical_ground_truth,
)


def test_single_vortex_shape():
    psi = single_vortex(N=32)
    assert psi.shape == (32, 32, 32)


def test_double_vortex_shape():
    psi = double_vortex(N=32)
    assert psi.shape == (32, 32, 32)


def test_single_vortex_dtype():
    psi = single_vortex(N=8)
    assert np.issubdtype(psi.dtype, np.complexfloating)


def test_single_vortex_unit_amplitude():
    psi = single_vortex(N=8)
    np.testing.assert_allclose(np.abs(psi), 1.0, atol=1e-10)


def test_double_vortex_unit_amplitude():
    psi = double_vortex(N=8)
    np.testing.assert_allclose(np.abs(psi), 1.0, atol=1e-10)


def test_validate_vortex_charges_both_pass():
    result = validate_vortex_charges()
    assert result["single_vortex_pass"], (
        f"single-vortex failed: Q_mean={result['single_vortex_Q_mean']}"
    )
    assert result["double_vortex_pass"], (
        f"double-vortex failed: Q_mean={result['double_vortex_Q_mean']}"
    )


def test_validate_vortex_charges_values():
    result = validate_vortex_charges()
    assert result["single_vortex_Q_mean"] == pytest.approx(1.0, abs=0.25)
    assert result["double_vortex_Q_mean"] == pytest.approx(2.0, abs=0.25)


def test_validate_vortex_charges_keys():
    result = validate_vortex_charges()
    for key in (
        "single_vortex_Q_mean",
        "double_vortex_Q_mean",
        "single_vortex_pass",
        "double_vortex_pass",
    ):
        assert key in result


# ── perturbed_vortex (Phase 9: active-inference search target) ───────────────

def test_perturbed_vortex_zero_amplitude_matches_single_vortex_exactly():
    psi = perturbed_vortex(N=16, noise_amplitude=0.0, seed=0)
    reference = single_vortex(N=16)
    np.testing.assert_array_equal(psi, reference)


def test_perturbed_vortex_nonzero_amplitude_differs_from_single_vortex():
    psi = perturbed_vortex(N=16, noise_amplitude=1.0, seed=0)
    reference = single_vortex(N=16)
    assert not np.allclose(psi, reference)


def test_perturbed_vortex_stays_unit_amplitude():
    psi = perturbed_vortex(N=16, noise_amplitude=1.0, seed=0)
    np.testing.assert_allclose(np.abs(psi), 1.0, atol=1e-8)


def test_perturbed_vortex_deterministic_given_seed():
    psi1 = perturbed_vortex(N=16, noise_amplitude=0.7, seed=5)
    psi2 = perturbed_vortex(N=16, noise_amplitude=0.7, seed=5)
    np.testing.assert_array_equal(psi1, psi2)


def test_perturbed_vortex_different_seeds_differ():
    psi1 = perturbed_vortex(N=16, noise_amplitude=0.7, seed=1)
    psi2 = perturbed_vortex(N=16, noise_amplitude=0.7, seed=2)
    assert not np.allclose(psi1, psi2)


def test_perturbed_vortex_charge_degrades_with_increasing_noise():
    """Winding charge must trend downward (toward 0) as noise_amplitude
    increases -- the whole premise `sim/active_inference.py`'s search relies
    on. Averaged over several seeds per amplitude to avoid single-draw noise."""
    def mean_qz(amplitude: float) -> float:
        vals = [
            float(np.mean(compute_Qz(perturbed_vortex(N=16, noise_amplitude=amplitude, seed=s))[0]))
            for s in range(8)
        ]
        return float(np.mean(vals))

    low = mean_qz(0.0)
    high = mean_qz(2.0)
    assert low > high
    assert low == pytest.approx(1.0, abs=0.05)


# ── Dynamical ground-truth generators ─────────────────────────────────────────

def test_cgl_step_shape_and_dtype():
    psi = 0.1 * (np.random.default_rng(0).standard_normal((16, 16)) * (1 + 1j))
    out = cgl_step(psi)
    assert out.shape == psi.shape
    assert np.issubdtype(out.dtype, np.complexfloating)


def test_cgl_defect_field_shape_and_finite():
    psi = cgl_defect_field(N=32, n_steps=20, seed=0)
    assert psi.shape == (32, 32)
    assert np.all(np.isfinite(psi))


def test_cgl_defect_field_trajectory_shape():
    traj = cgl_defect_field(N=16, n_steps=5, return_trajectory=True, seed=0)
    assert traj.shape == (6, 16, 16)


def test_cgl_defect_field_rejects_invalid_size():
    with pytest.raises(ValueError):
        cgl_defect_field(N=2)


def test_cgl_defect_field_produces_nonzero_winding():
    """CGL (not diffusion) genuinely nucleates defects: Qabs should be
    substantially nonzero at short integration time, unlike the diffusion
    stub this generator replaces (which always relaxed to a trivial field)."""
    psi = cgl_defect_field(N=64, n_steps=100, seed=0)
    _, qabs = compute_Qz(psi[:, :, np.newaxis])
    assert float(qabs[0]) > 1.0


def test_cgl_defect_field_amplitude_dips_at_cores():
    """Real vortex cores have |psi| -> 0, unlike the static single_vortex/
    double_vortex fields (|psi|=1 everywhere) which detect_defects can never
    fire on at its default amp_threshold=0.2."""
    psi = cgl_defect_field(N=64, n_steps=100, seed=0)
    assert float(np.abs(psi).min()) < 0.2


def test_detect_defects_fires_on_cgl_field():
    """Closes the generator/detector amplitude mismatch: detect_defects finds
    zero defects on single_vortex/double_vortex (|psi|=1 everywhere) but must
    find a nonzero count on a field with genuine amplitude-dipping cores."""
    psi = cgl_defect_field(N=64, n_steps=100, seed=0)
    defects = detect_defects(psi[:, :, np.newaxis], amp_threshold=0.2)
    assert defects.shape[0] > 0
    assert defects.shape[1] == 4  # [x, y, z, sign]


def test_detect_defects_finds_nothing_on_static_single_vortex():
    """Documents the mismatch this module fixes: the ORIGINAL static field
    still yields zero defects at the default threshold (unit amplitude
    everywhere) -- this is expected, not a regression; cgl_defect_field is the
    generator that actually exercises detect_defects."""
    psi = single_vortex(N=32)
    defects = detect_defects(psi, amp_threshold=0.2)
    assert defects.shape[0] == 0


def test_kuramoto_vortex_field_shape_and_unit_amplitude():
    psi = kuramoto_vortex_field(N=32, n_steps=20, seed=0)
    assert psi.shape == (32, 32)
    np.testing.assert_allclose(np.abs(psi), 1.0, atol=1e-10)


def test_kuramoto_vortex_field_trajectory_shape():
    traj = kuramoto_vortex_field(N=16, n_steps=5, return_trajectory=True, seed=0)
    assert traj.shape == (6, 16, 16)


def test_kuramoto_vortex_field_rejects_invalid_size():
    with pytest.raises(ValueError):
        kuramoto_vortex_field(N=2)


def test_kuramoto_vortex_field_retains_planted_charge_under_strong_coupling():
    """The dial-a-defect-density property: strong coupling + zero disorder
    should reliably retain the planted topological charge (it is not merely
    relabeled -- the dynamics have to genuinely preserve it under evolution)."""
    psi = kuramoto_vortex_field(N=48, n_steps=150, K=8.0, sigma_omega=0.0, planted_charge=1, seed=1)
    q, _ = compute_Qz(psi[:, :, np.newaxis])
    assert int(q[0]) == 1


def test_kuramoto_weak_coupling_high_disorder_can_lose_planted_charge():
    """The other end of the dial: across several seeds, strong disorder should
    lose the planted charge at least once (demonstrates the field is a real,
    non-trivial dynamical system, not a fixed relabeling of the seed)."""
    outcomes = []
    for seed in range(6):
        psi = kuramoto_vortex_field(N=48, n_steps=150, K=0.5, sigma_omega=2.0, planted_charge=1, seed=seed)
        q, _ = compute_Qz(psi[:, :, np.newaxis])
        outcomes.append(int(q[0]))
    assert any(o != 1 for o in outcomes)


def test_validate_dynamical_ground_truth_keys_and_pass():
    result = validate_dynamical_ground_truth(seed=0)
    for key in (
        "cgl_qabs", "cgl_qabs_nonzero", "cgl_n_defects_detected",
        "cgl_defects_detected_pass", "kuramoto_recovered_Q",
        "kuramoto_charge_retained_pass",
    ):
        assert key in result
    assert result["cgl_qabs_nonzero"] is True
    assert result["cgl_defects_detected_pass"] is True
    assert result["kuramoto_charge_retained_pass"] is True
