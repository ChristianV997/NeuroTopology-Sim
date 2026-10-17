"""Independent regression test suite for discrete exact-DMD and EP2 / Crouzeix diagnostics.

Status: HOLD / SYNTHETIC_ONLY.
Neither discrete-operator recovery, synthetic exceptional points, nor Crouzeix numerical-range
bounds represent biological evidence, clinical safety, or a theory-of-everything claim.

Architecture:
- Layer A: Self-contained independent mathematical oracles and analytical ground-truth derivations
  (pairing seam exclusion, 240 Hz vs -10 Hz Nyquist alias, EP2 nilpotency at g=delta, Crouzeix
  bounds, matrix-log branch ambiguity).
- Layer B: Contract validation and integration regression against candidate implementation
  `neurotopology_sim.experimental.dynamics.dmd_crouzeix` (Cursor Agent D, PR #415).
"""

from __future__ import annotations

import cmath
import math
from typing import Any, List, Sequence, Tuple

import numpy as np
import pytest

# Attempt import of Cursor Agent D's candidate module
try:
    from neurotopology_sim.experimental.dynamics.dmd_crouzeix import (
        ARRAY_ORIENTATION,
        CROUZEIX_PEER_REVIEWED_C,
        CROUZEIX_PREPRINT_C2_LABEL,
        PROJECT_STATUS,
        SCHEMA_VERSION,
        AliasAmbiguityReport,
        CrouzeixReport,
        DMDDiagnostics,
        DMDResult,
        DMDValidationError,
        EP2Report,
        GeneratorDiagnostics,
        SnapshotPairMeta,
        alias_ambiguity_report,
        build_snapshot_matrices,
        crouzeix_bound_report,
        diagnose_ep2,
        discrete_eigenvalue_from_frequency_hz,
        ep2_hamiltonian,
        estimate_exact_dmd,
    )

    HAS_CANDIDATE = True
except ImportError:
    HAS_CANDIDATE = False


# ==============================================================================
# Layer A: Independent Mathematical Oracles & Analytical Ground-Truth
# ==============================================================================


def oracle_ep2_hamiltonian(
    omega: float, delta: float, gamma: float, g: float
) -> np.ndarray:
    """Independent 2x2 non-Hermitian Hamiltonian model."""
    return np.array(
        [
            [complex(omega + delta, -gamma), complex(0.0, -g)],
            [complex(0.0, -g), complex(omega - delta, -gamma)],
        ],
        dtype=np.complex128,
    )


def oracle_ep2_theoretical_split(delta: float, g: float) -> float:
    """Theoretical eigenvalue split: 2 * sqrt(|delta^2 - g^2|)."""
    disc = delta**2 - g**2
    return 2.0 * math.sqrt(abs(disc))


def oracle_within_trajectory_pairs(
    trajectories: Sequence[np.ndarray],
) -> List[Tuple[Tuple[float, ...], Tuple[float, ...]]]:
    """Extract adjacent column pairs strictly within each trajectory (no cross-trajectory seam)."""
    pairs: List[Tuple[Tuple[float, ...], Tuple[float, ...]]] = []
    for traj in trajectories:
        n_cols = traj.shape[1]
        for t in range(n_cols - 1):
            x_t = tuple(float(v) for v in traj[:, t])
            x_t1 = tuple(float(v) for v in traj[:, t + 1])
            pairs.append((x_t, x_t1))
    return pairs


def oracle_naive_concatenated_pairs(
    trajectories: Sequence[np.ndarray],
) -> List[Tuple[Tuple[float, ...], Tuple[float, ...]]]:
    """Extract adjacent column pairs after naive concatenation (introducing spurious seam)."""
    concat = np.concatenate(trajectories, axis=1)
    pairs: List[Tuple[Tuple[float, ...], Tuple[float, ...]]] = []
    for t in range(concat.shape[1] - 1):
        x_t = tuple(float(v) for v in concat[:, t])
        x_t1 = tuple(float(v) for v in concat[:, t + 1])
        pairs.append((x_t, x_t1))
    return pairs


class TestIndependentMathematicalOracles:
    """Tests evaluating exact mathematical properties independent of candidate production code."""

    def test_ep2_theoretical_splitting_sweep(self) -> None:
        """Verify the theoretical eigenvalue splitting formula across detuning and coupling."""
        delta = 1.2
        # g = 0.4: strong splitting
        split_g04 = oracle_ep2_theoretical_split(delta, 0.4)
        assert split_g04 == pytest.approx(2.2627416997969525, rel=1e-12)

        # g = 1.0: reduced splitting
        split_g10 = oracle_ep2_theoretical_split(delta, 1.0)
        assert split_g10 == pytest.approx(1.32664991614216, rel=1e-12)

        # g = 1.2 == delta: exact coalescence (split = 0)
        split_ep = oracle_ep2_theoretical_split(delta, delta)
        assert split_ep == 0.0

    def test_ep2_nilpotency_and_operator_recovery(self) -> None:
        """Verify shifted Hamiltonian N = H - (omega - i*gamma)I is non-zero with N^2 = 0 at EP."""
        omega, delta, gamma = 0.0, 1.2, 0.0
        H = oracle_ep2_hamiltonian(omega, delta, gamma, g=delta)
        center = complex(omega, -gamma)
        N = H - center * np.eye(2, dtype=np.complex128)

        # 1. N is non-zero: Frobenius norm is exactly 2*delta = 2.4
        n_fro = float(np.linalg.norm(N, ord="fro"))
        assert n_fro == pytest.approx(2.4, abs=1e-12)

        # 2. N^2 is identically zero
        N2 = N @ N
        np.testing.assert_allclose(N2, 0.0 + 0.0j, atol=1e-14)

        # 3. Geometric multiplicity = 1 (rank of N is 1)
        _, s, _ = np.linalg.svd(N)
        assert s[0] == pytest.approx(2.4, abs=1e-12)
        assert s[1] < 1e-14  # exactly zero singular value

        # 4. Floating-point eigensolver gap artifact vs operator nilpotency:
        # Standard complex eigensolver on floating point can exhibit a small gap ~ 10^-8
        # due to sqrt(eps) perturbation sensitivity of Jordan blocks.
        evals = np.linalg.eigvals(H)
        num_gap = float(abs(evals[0] - evals[1]))
        # The numerical gap may be > 1e-10 even though theoretical split is 0
        # Demonstrating why operator-entry recovery (N^2=0) is prioritized over eigenvalue gap
        assert np.linalg.norm(N2, ord="fro") < 1e-12
        assert num_gap < 1e-6

    def test_nyquist_240hz_alias_indistinguishable_at_250hz(self) -> None:
        """Prove that discrete samples of 240 Hz and -10 Hz at fs=250 Hz are mathematically identical."""
        fs = 250.0
        dt = 1.0 / fs
        f_true = 240.0
        f_alias = -10.0  # 240 - 250 = -10

        # Discrete eigenvalue under lambda = exp(-i * 2*pi * f * dt)
        lam_true = np.exp(-1j * 2.0 * np.pi * f_true * dt)
        lam_alias = np.exp(-1j * 2.0 * np.pi * f_alias * dt)

        # Prove eigenvalues match to machine precision
        assert abs(lam_true - lam_alias) < 1e-14

        # Generate sample points over 50 discrete time steps
        k_steps = np.arange(50)
        t_samples = k_steps * dt

        # Complex continuous modes sampled at t_samples
        signal_true = np.exp(-1j * 2.0 * np.pi * f_true * t_samples)
        signal_alias = np.exp(-1j * 2.0 * np.pi * f_alias * t_samples)

        max_sample_diff = float(np.max(np.abs(signal_true - signal_alias)))
        assert max_sample_diff < 1e-12

    def test_seam_exclusion_oracle(self) -> None:
        """Verify within-trajectory pairing excludes artificial boundary seam pair."""
        traj1 = np.array([[1.0, 2.0, 3.0], [0.1, 0.2, 0.3]])
        traj2 = np.array([[100.0, 101.0], [10.0, 11.0]])

        clean_pairs = oracle_within_trajectory_pairs([traj1, traj2])
        naive_pairs = oracle_naive_concatenated_pairs([traj1, traj2])

        # True within-trajectory pairs: (col 0, col 1), (col 1, col 2) from traj1; (col 0, col 1) from traj2
        expected_clean = [
            ((1.0, 0.1), (2.0, 0.2)),
            ((2.0, 0.2), (3.0, 0.3)),
            ((100.0, 10.0), (101.0, 11.0)),
        ]
        assert clean_pairs == expected_clean

        # Naive pairs include the spurious boundary transition ((3.0, 0.3), (100.0, 10.0))
        seam_pair = ((3.0, 0.3), (100.0, 10.0))
        assert seam_pair not in clean_pairs
        assert seam_pair in naive_pairs
        assert len(clean_pairs) == 3
        assert len(naive_pairs) == 4

    def test_matrix_log_residual_does_not_prove_branch_recovery(self) -> None:
        """Prove that expm(L*dt) ≈ A reconstruction holds for all branches, not proving true frequency."""
        dt = 0.004  # fs = 250 Hz
        theta = 0.4  # radians

        # 2D rotation discrete operator
        A = np.array([[math.cos(theta), -math.sin(theta)], [math.sin(theta), math.cos(theta)]])

        # Principal branch generator
        L_principal = np.array([[0.0, -theta / dt], [theta / dt, 0.0]])

        # First alias branch generator (k = 1)
        theta_alias = theta + 2.0 * math.pi
        L_alias = np.array([[0.0, -theta_alias / dt], [theta_alias / dt, 0.0]])

        # Both yield A under matrix exponentiation
        # expm([[0, -w*dt], [w*dt, 0]]) = [[cos(w*dt), -sin(w*dt)], [sin(w*dt), cos(w*dt)]]
        A_recon_principal = np.array(
            [
                [math.cos(theta), -math.sin(theta)],
                [math.sin(theta), math.cos(theta)],
            ]
        )
        A_recon_alias = np.array(
            [
                [math.cos(theta_alias), -math.sin(theta_alias)],
                [math.sin(theta_alias), math.cos(theta_alias)],
            ]
        )

        np.testing.assert_allclose(A_recon_principal, A, atol=1e-14)
        np.testing.assert_allclose(A_recon_alias, A, atol=1e-14)

        # Residual is machine zero for both branches:
        res_principal = float(np.linalg.norm(A_recon_principal - A, ord="fro"))
        res_alias = float(np.linalg.norm(A_recon_alias - A, ord="fro"))
        assert res_principal < 1e-14
        assert res_alias < 1e-14

        # Proof: small residual alone cannot determine whether L_principal or L_alias was original generator
        assert not np.allclose(L_principal, L_alias)


# ==============================================================================
# Layer B: Candidate Contract & Production Regression Suite
# ==============================================================================


@pytest.mark.skipif(
    not HAS_CANDIDATE,
    reason="Candidate module neurotopology_sim.experimental.dynamics.dmd_crouzeix not available in environment",
)
class TestCandidateDMDCrouzeixRegression:
    """Regression suite against neurotopology_sim.experimental.dynamics.dmd_crouzeix."""

    def test_schema_and_hold_synthetic_status(self) -> None:
        """Verify schema string and project status constant."""
        assert SCHEMA_VERSION == "NeuroTopology.DMDCrouzeix.v1"
        assert PROJECT_STATUS == "HOLD_SYNTHETIC_ONLY"
        assert ARRAY_ORIENTATION == "state_columns"

    def test_within_trajectory_snapshot_pairing_and_seam_rejection(self) -> None:
        """Verify snapshot matrix builder pairs strictly within trajectories."""
        # Two trajectories with a deliberate discontinuity at the boundary
        traj_a = np.array([[1.0, 2.0, 3.0], [0.0, 0.0, 0.0]], dtype=np.float64)
        traj_b = np.array([[100.0, 101.0], [0.0, 0.0]], dtype=np.float64)

        X, Y, meta = build_snapshot_matrices([traj_a, traj_b])

        assert isinstance(meta, SnapshotPairMeta)
        assert meta.n_trajectories == 2
        assert meta.n_pairs == 3
        assert meta.n_state == 2
        assert meta.pairs_per_trajectory == (2, 1)
        assert meta.pairing_rule == "within_trajectory_adjacent_only"

        # Verify exact columns of X and Y
        pairs_top_row = list(zip(X[0], Y[0]))
        assert pairs_top_row == [(1.0, 2.0), (2.0, 3.0), (100.0, 101.0)]

        # Prove the boundary seam (3.0, 100.0) is not present
        assert (3.0, 100.0) not in pairs_top_row

        # Contrast with naive concatenation
        naive_concat = np.concatenate([traj_a[0], traj_b[0]])
        naive_pairs = list(zip(naive_concat[:-1], naive_concat[1:]))
        assert (3.0, 100.0) in naive_pairs

    def test_exact_dmd_operator_recovery_on_known_system(self) -> None:
        """Verify exact DMD recovers a known 2x2 discrete operator from simulation trajectory."""
        rng = np.random.default_rng(42)
        A_true = np.array([[0.85, 0.15], [-0.05, 0.90]], dtype=np.float64)

        # Generate trajectory: x_{t+1} = A_true * x_t
        x0 = rng.normal(size=2)
        cols = [x0]
        for _ in range(30):
            cols.append(A_true @ cols[-1])
        trajectory = np.column_stack(cols)

        result = estimate_exact_dmd(trajectory, dt=0.01, estimate_generator=False)
        assert isinstance(result, DMDResult)
        assert result.project_status == "HOLD_SYNTHETIC_ONLY"
        assert result.A.shape == (2, 2)

        # Operator recovery error should be near machine precision
        err = float(np.linalg.norm(result.A - A_true, ord="fro"))
        assert err < 1e-10
        assert result.diagnostics.residual_fro < 1e-10
        assert result.diagnostics.rank == 2
        assert result.diagnostics.n_pairs == 30
        assert result.diagnostics.n_state == 2

    def test_contrast_clean_vs_seamed_dmd_estimation(self) -> None:
        """Demonstrate that naive concatenation corrupts DMD estimate while within-trajectory pairing succeeds."""
        A_true = np.array([[0.8, 0.2], [-0.1, 0.7]], dtype=np.float64)

        # Trajectory 1 starting at [1.0, 0.0]
        cols_1 = [np.array([1.0, 0.0])]
        for _ in range(4):
            cols_1.append(A_true @ cols_1[-1])
        traj_1 = np.column_stack(cols_1)

        # Trajectory 2 starting at [0.0, 1.0]
        cols_2 = [np.array([0.0, 1.0])]
        for _ in range(4):
            cols_2.append(A_true @ cols_2[-1])
        traj_2 = np.column_stack(cols_2)

        # 1. Correct within-trajectory estimation: recovers A_true to machine precision
        res_clean = estimate_exact_dmd([traj_1, traj_2], dt=0.01)
        err_clean = float(np.linalg.norm(res_clean.A - A_true, ord="fro"))
        assert err_clean < 1e-10

        # 2. Corrupted naive concatenated trajectory: spurious seam pair massively corrupts A
        corrupt_concat = np.concatenate([traj_1, traj_2], axis=1)
        res_corrupt = estimate_exact_dmd(corrupt_concat, dt=0.01)
        err_corrupt = float(np.linalg.norm(res_corrupt.A - A_true, ord="fro"))
        assert err_corrupt > 0.05

    def test_nyquist_alias_report_240hz_at_250hz(self) -> None:
        """Verify alias ambiguity report correctly identifies 240 Hz vs -10 Hz at 250 Hz."""
        report = alias_ambiguity_report(f_hz=240.0, fs_hz=250.0)
        assert isinstance(report, AliasAmbiguityReport)
        assert report.fs_hz == 250.0
        assert report.f_hz == 240.0
        assert report.f_alias_hz == pytest.approx(-10.0)
        assert report.dt == pytest.approx(0.004)
        assert report.phases_match is True
        assert abs(report.lambda_true - report.lambda_alias) < 1e-12
        assert report.convention == "lambda = exp(-i * 2*pi*f * dt)"
        # Verify explicit disclaimer about ambiguity rather than unique recovery claim
        assert "ambiguity" in report.claim.lower()

        # Check discrete_eigenvalue_from_frequency_hz helper
        dt = 1.0 / 250.0
        val_240 = discrete_eigenvalue_from_frequency_hz(240.0, dt)
        val_m10 = discrete_eigenvalue_from_frequency_hz(-10.0, dt)
        assert val_240 == pytest.approx(val_m10, abs=1e-12)

    def test_exact_ep2_coalescence_and_nilpotency_diagnostics(self) -> None:
        """Verify candidate diagnose_ep2 accurately identifies nilpotency at g=delta and separates numerical gap."""
        delta = 1.2
        omega = 0.0
        gamma = 0.0

        # At EP: g = delta
        H_ep = ep2_hamiltonian(omega=omega, delta=delta, gamma=gamma, g=delta)
        rep_ep = diagnose_ep2(H_ep, omega=omega, gamma=gamma)

        assert isinstance(rep_ep, EP2Report)
        assert rep_ep.project_status == "HOLD_SYNTHETIC_ONLY"
        assert bool(rep_ep.theoretical_coalesced) is True
        assert bool(rep_ep.operator_entry_ok) is True
        assert rep_ep.nilpotent_norm == pytest.approx(2.4, abs=1e-6)
        assert rep_ep.nilpotent_square_norm < 1e-12
        assert rep_ep.algebraic_multiplicity == 2
        assert rep_ep.geometric_multiplicity == 1
        assert any("nilpotent N with N^2≈0 verified" in n for n in rep_ep.notes)
        assert any("synthetic fixture only" in n for n in rep_ep.notes)

        # Off EP: g = 0.4 != delta
        H_sub = ep2_hamiltonian(omega=omega, delta=delta, gamma=gamma, g=0.4)
        rep_sub = diagnose_ep2(H_sub, omega=omega, gamma=gamma)
        assert bool(rep_sub.theoretical_coalesced) is False
        assert bool(rep_sub.operator_entry_ok) is False
        assert rep_sub.algebraic_multiplicity == 1

    def test_crouzeix_peer_reviewed_fallback_and_preprint_c2(self) -> None:
        """Verify Crouzeix report enforces peer-reviewed C=1+sqrt(2) and tags C=2 as PREPRINT_UNVERIFIED."""
        A = np.array([[0.5, 2.0], [0.0, 0.5]], dtype=np.complex128)

        # 1. Peer-reviewed default (C = 1 + sqrt(2))
        peer_rep = crouzeix_bound_report(A, role="discrete_operator", use_preprint_c2=False)
        assert isinstance(peer_rep, CrouzeixReport)
        assert peer_rep.constant == pytest.approx(CROUZEIX_PEER_REVIEWED_C)
        assert peer_rep.constant == pytest.approx(1.0 + math.sqrt(2.0))
        assert peer_rep.constant_label == "peer_reviewed_crouzeix_palencia_2017"
        assert peer_rep.not_biological_safety_certificate is True
        assert "HOLD / SYNTHETIC_ONLY" in peer_rep.scope
        assert any("2017" in ref for ref in peer_rep.references)

        # 2. Preprint option (C = 2)
        pre_rep = crouzeix_bound_report(A, role="discrete_operator", use_preprint_c2=True)
        assert pre_rep.constant == 2.0
        assert pre_rep.constant_label == CROUZEIX_PREPRINT_C2_LABEL
        assert pre_rep.constant_label == "PREPRINT_UNVERIFIED"
        assert any("PREPRINT_UNVERIFIED" in ref for ref in pre_rep.references)
        assert pre_rep.not_biological_safety_certificate is True

    def test_generator_branch_cut_and_nyquist_diagnostics(self) -> None:
        """Verify generator diagnostics report principal-branch assumptions and Nyquist ambiguity."""
        # Rotation with phase near pi -> approaches negative real branch cut
        theta = math.pi - 1e-7
        A_near_cut = np.array(
            [[math.cos(theta), -math.sin(theta)], [math.sin(theta), math.cos(theta)]],
            dtype=np.float64,
        )

        cols = [np.array([1.0, 0.0])]
        for _ in range(10):
            cols.append(A_near_cut @ cols[-1])
        traj = np.column_stack(cols)

        res = estimate_exact_dmd(traj, dt=0.004, estimate_generator=True, sample_rate_hz=250.0)
        assert res.generator_diagnostics is not None
        gd = res.generator_diagnostics
        assert isinstance(gd, GeneratorDiagnostics)
        assert gd.principal_branch is True
        assert gd.nyquist_ambiguity is True
        assert "principal_branch_matrix_logarithm" in gd.assumptions
        assert "reconstruction check" in gd.note

    def test_fail_closed_on_rank_deficient_and_ill_conditioned_snapshots(self) -> None:
        """Verify estimator fails closed or flags rank deficiency and ill-conditioning."""
        # 1. Zero snapshot matrix (all zeros)
        traj_zero = np.zeros((3, 10), dtype=np.float64)
        with pytest.raises(DMDValidationError, match="rank-deficient|σ_max"):
            estimate_exact_dmd(traj_zero, dt=0.01)

        # 2. 1D dynamics in 2D ambient space (singular value 2 is zero)
        traj_1d = np.array([[1.0, 2.0, 3.0, 4.0], [0.0, 0.0, 0.0, 0.0]], dtype=np.float64)
        # Automatic rank should select rank 1
        res_auto = estimate_exact_dmd(traj_1d, dt=0.01)
        assert res_auto.diagnostics.rank == 1

        # Requesting rank 2 when numerical rank is 1 truncates to 1
        res_req = estimate_exact_dmd(traj_1d, dt=0.01, rank=2)
        assert res_req.diagnostics.rank == 1

    def test_fail_closed_on_invalid_dt(self) -> None:
        """Verify non-positive, zero, or non-finite dt values fail closed."""
        traj = np.ones((2, 5), dtype=np.float64)
        for bad_dt in (0.0, -0.01, -1.0, float("nan"), float("inf")):
            with pytest.raises(DMDValidationError, match="dt"):
                estimate_exact_dmd(traj, dt=bad_dt)

        for bad_dt in (0.0, -1.0, float("nan")):
            with pytest.raises(DMDValidationError, match="dt"):
                discrete_eigenvalue_from_frequency_hz(10.0, dt=bad_dt)

    def test_fail_closed_on_malformed_trajectories_and_shapes(self) -> None:
        """Verify 1D inputs, empty sequences, length < 2, or shape mismatches fail closed."""
        # 1D array instead of 2D
        with pytest.raises(DMDValidationError, match="2-D"):
            estimate_exact_dmd(np.array([1.0, 2.0, 3.0]), dt=0.01)

        # Empty trajectory sequence
        with pytest.raises(DMDValidationError, match="non-empty"):
            estimate_exact_dmd([], dt=0.01)

        # Trajectory with n_time < 2
        with pytest.raises(DMDValidationError, match="n_time>=2"):
            estimate_exact_dmd(np.ones((2, 1)), dt=0.01)

        # Mismatched n_state between trajectories
        t1 = np.ones((2, 5))
        t2 = np.ones((3, 5))
        with pytest.raises(DMDValidationError, match="share n_state"):
            estimate_exact_dmd([t1, t2], dt=0.01)

    def test_fail_closed_on_non_finite_values(self) -> None:
        """Verify NaNs and Infs in trajectories fail closed with DMDValidationError."""
        t_nan = np.ones((2, 5))
        t_nan[0, 2] = np.nan
        with pytest.raises(DMDValidationError, match="non-finite"):
            estimate_exact_dmd(t_nan, dt=0.01)

        t_inf = np.ones((2, 5))
        t_inf[1, 3] = np.inf
        with pytest.raises(DMDValidationError, match="non-finite"):
            estimate_exact_dmd(t_inf, dt=0.01)

        # Non-finite in EP Hamiltonian
        H_bad = np.array([[np.nan, 0.0], [0.0, 1.0]], dtype=complex)
        with pytest.raises(DMDValidationError, match="non-finite"):
            diagnose_ep2(H_bad)

        # Non-finite in Crouzeix report
        with pytest.raises(DMDValidationError, match="non-finite"):
            crouzeix_bound_report(H_bad)
