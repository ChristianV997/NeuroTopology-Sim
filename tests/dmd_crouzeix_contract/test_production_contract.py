"""Contract smoke for neurotopology_sim.experimental.dynamics.dmd_crouzeix.

HOLD / SYNTHETIC_ONLY. These tests belong to the production-writer path and do
**not** edit or replace Antigravity Agent D's independent DMD regression file.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from neurotopology_sim.experimental.dynamics.dmd_crouzeix import (
    CROUZEIX_PEER_REVIEWED_C,
    CROUZEIX_PREPRINT_C2_LABEL,
    PROJECT_STATUS,
    SCHEMA_VERSION,
    DMDValidationError,
    alias_ambiguity_report,
    build_snapshot_matrices,
    crouzeix_bound_report,
    diagnose_ep2,
    discrete_eigenvalue_from_frequency_hz,
    ep2_hamiltonian,
    estimate_exact_dmd,
)


def test_schema_and_hold_status():
    assert SCHEMA_VERSION == "NeuroTopology.DMDCrouzeix.v1"
    assert PROJECT_STATUS == "HOLD_SYNTHETIC_ONLY"


def test_within_trajectory_pairing_rejects_seam():
    a = np.array([[1.0, 2.0, 3.0], [0.0, 0.0, 0.0]], dtype=float)
    b = np.array([[100.0, 101.0], [0.0, 0.0]], dtype=float)
    X, Y, meta = build_snapshot_matrices([a, b])
    pairs = list(zip(X[0], Y[0]))
    assert pairs == [(1.0, 2.0), (2.0, 3.0), (100.0, 101.0)]
    assert (3.0, 100.0) not in pairs
    naive = list(zip(np.concatenate([a[0], b[0]]), np.concatenate([a[0], b[0]])[1:]))
    assert (3.0, 100.0) in naive
    assert meta.pairs_per_trajectory == (2, 1)
    assert meta.pairing_rule == "within_trajectory_adjacent_only"


def test_exact_dmd_recovers_known_discrete_operator():
    rng = np.random.default_rng(0)
    A_true = np.array([[0.9, 0.1], [0.0, 0.8]], dtype=float)
    x0 = rng.normal(size=2)
    cols = [x0]
    for _ in range(40):
        cols.append(A_true @ cols[-1])
    traj = np.column_stack(cols)
    result = estimate_exact_dmd(traj, dt=0.01, estimate_generator=False)
    assert result.project_status == PROJECT_STATUS
    assert result.A.shape == (2, 2)
    assert np.linalg.norm(result.A - A_true, ord="fro") < 1e-8
    assert result.diagnostics.residual_fro < 1e-8


def test_rank_deficient_snapshots_fail_closed():
    # Zero snapshot matrix → σ_max ≤ 0.
    traj = np.zeros((2, 5), dtype=float)
    with pytest.raises(DMDValidationError, match="rank-deficient|σ_max"):
        estimate_exact_dmd(traj, dt=0.01)


def test_rank_deficient_single_direction():
    # One-dimensional dynamics in 2-D ambient space with requested full rank.
    A = np.array([[0.5, 0.0], [0.0, 0.0]], dtype=float)
    x = np.array([1.0, 0.0])
    cols = [x]
    for _ in range(10):
        cols.append(A @ cols[-1])
    traj = np.column_stack(cols)
    # Numerical rank is 1; requesting rank 2 must truncate / stay at auto rank.
    result = estimate_exact_dmd(traj, dt=0.01, rank=2)
    assert result.diagnostics.rank == 1


def test_alias_240hz_matches_minus_10hz_at_250hz():
    report = alias_ambiguity_report(240.0, 250.0)
    assert report.f_alias_hz == pytest.approx(-10.0)
    assert report.phases_match
    assert abs(report.lambda_true - report.lambda_alias) < 1e-12
    dt = 1.0 / 250.0
    assert discrete_eigenvalue_from_frequency_hz(240.0, dt) == pytest.approx(
        discrete_eigenvalue_from_frequency_hz(-10.0, dt)
    )
    assert "ambiguity" in report.claim


def test_generator_path_reports_branch_limitations():
    # Rotation by a near-π phase → near branch cut for principal log.
    theta = math.pi - 1e-8
    A = np.array(
        [[math.cos(theta), -math.sin(theta)], [math.sin(theta), math.cos(theta)]],
        dtype=float,
    )
    # Build a short trajectory from A.
    x = np.array([1.0, 0.0])
    cols = [x]
    for _ in range(8):
        cols.append(A @ cols[-1])
    traj = np.column_stack(cols)
    result = estimate_exact_dmd(traj, dt=0.004, estimate_generator=True, sample_rate_hz=250.0)
    assert result.generator_diagnostics is not None
    gd = result.generator_diagnostics
    assert gd.principal_branch
    assert gd.nyquist_ambiguity
    assert "principal_branch_matrix_logarithm" in gd.assumptions
    assert "reconstruction check" in gd.note
    # Round-trip may succeed while status is ambiguous near the cut.
    if gd.round_trip_residual is not None and gd.status in {"ok", "ambiguous"}:
        assert gd.round_trip_residual < 1e-6


def test_exact_ep2_nilpotency_and_coalescence():
    delta = 1.2
    H = ep2_hamiltonian(omega=0.0, delta=delta, gamma=0.0, g=delta)
    report = diagnose_ep2(H, omega=0.0, gamma=0.0)
    assert report.theoretical_coalesced
    assert report.operator_entry_ok
    assert report.nilpotent_norm > 1e-10
    assert report.nilpotent_square_norm < 1e-10
    assert report.algebraic_multiplicity == 2
    assert report.geometric_multiplicity == 1
    assert report.project_status == PROJECT_STATUS
    # Away from EP: discriminant nonzero, not operator-ok as EP nilpotent.
    H2 = ep2_hamiltonian(0.0, 1.2, 0.0, 0.4)
    r2 = diagnose_ep2(H2, omega=0.0, gamma=0.0)
    assert not r2.theoretical_coalesced


def test_crouzeix_peer_reviewed_fallback_and_preprint_label():
    A = np.array([[0.5, 2.0], [0.0, 0.5]], dtype=complex)
    peer = crouzeix_bound_report(A, role="discrete_operator", use_preprint_c2=False)
    assert peer.constant == pytest.approx(CROUZEIX_PEER_REVIEWED_C)
    assert peer.constant_label == "peer_reviewed_crouzeix_palencia_2017"
    assert peer.not_biological_safety_certificate
    assert "numerical range" in peer.theorem_statement.lower() or "W(A)" in peer.theorem_statement
    pre = crouzeix_bound_report(A, role="discrete_operator", use_preprint_c2=True)
    assert pre.constant == 2.0
    assert pre.constant_label == CROUZEIX_PREPRINT_C2_LABEL


def test_validation_rejects_bad_dt_and_nonfinite():
    traj = np.ones((2, 3), dtype=float)
    with pytest.raises(DMDValidationError):
        estimate_exact_dmd(traj, dt=0.0)
    bad = traj.copy()
    bad[0, 0] = np.nan
    with pytest.raises(DMDValidationError):
        estimate_exact_dmd(bad, dt=0.01)
