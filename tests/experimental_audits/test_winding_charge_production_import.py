"""Compare #399 independent oracle against live production winding module.

HOLD / SYNTHETIC_ONLY. Discrete identity only — not biological validation.

These tests **hard-import** ``neurotopology_sim.experimental.topology.winding``
(merged production leaf) so the audit suite cannot silently self-validate a
copied oracle while skipping the intended implementation. They do not weaken
oracle assertions; mismatches fail.
"""

from __future__ import annotations

import inspect
import math

import numpy as np
import pytest

import neurotopology_sim.experimental.topology.winding as winding_mod
from neurotopology_sim.experimental.topology.winding import (
    TWO_PI,
    charge_moments,
    origin_shifted_moment,
    phase_winding,
    signed_first_moment,
    WindingError,
)
from tools.experimental_audits.winding_charge_round6.oracle import (
    branch_index_and_wrapped,
    triangle_loop_winding,
)


def test_imports_production_winding_module_not_oracle_copy():
    path = inspect.getfile(winding_mod)
    assert path.replace("\\", "/").endswith(
        "neurotopology_sim/experimental/topology/winding.py"
    )
    assert inspect.isfunction(phase_winding)
    # Must not be the audit oracle package path.
    assert "experimental_audits" not in path


def _standard_triangle_incidence() -> tuple[np.ndarray, np.ndarray]:
    d0 = np.array(
        [
            [-1, 1, 0],
            [0, -1, 1],
            [-1, 0, 1],
        ],
        dtype=np.int64,
    )
    d1 = np.array([[1, 1, -1]], dtype=np.int64)
    return d0, d1


@pytest.mark.parametrize(
    "theta,expected_q",
    [
        (np.array([0.0, 2.0 * math.pi / 3.0, 4.0 * math.pi / 3.0]), 1),
        (np.array([0.0, -2.0 * math.pi / 3.0, 2.0 * math.pi / 3.0]), -1),
        (np.array([0.0, 2.0 * math.pi / 3.0, -2.0 * math.pi / 3.0]), 1),
    ],
)
def test_oracle_triangle_winding_matches_production_face_charge(
    theta: np.ndarray, expected_q: int
) -> None:
    d0, d1 = _standard_triangle_incidence()
    prod = phase_winding(theta, d0, d1)
    ora = triangle_loop_winding(theta, (0, 1, 2))
    assert prod.face_charge.tolist() == [expected_q]
    assert ora == expected_q
    assert int(prod.face_charge[0]) == ora
    circ = float(np.asarray(d1.astype(float) @ prod.omega).reshape(()))
    assert abs(circ - TWO_PI * expected_q) < 1e-12


def test_orientation_reversal_sign_matches_production() -> None:
    d0, d1 = _standard_triangle_incidence()
    theta = np.array([0.0, 2.0 * math.pi / 3.0, 4.0 * math.pi / 3.0])
    q_fwd = int(phase_winding(theta, d0, d1).face_charge[0])
    q_rev_production = int(phase_winding(theta, d0, -d1).face_charge[0])
    q_rev_oracle = triangle_loop_winding(theta, (0, 2, 1))
    assert q_fwd == 1
    assert q_rev_production == -1
    assert q_rev_oracle == -1
    assert q_rev_production == q_rev_oracle


@pytest.mark.parametrize("raw,expected_branch", [(math.pi, 1), (-math.pi, 0)])
def test_production_branch_cut_matches_independent_oracle(raw, expected_branch) -> None:
    d0, d1 = _standard_triangle_incidence()
    theta = np.array([0.0, raw, raw])
    result = phase_winding(theta, d0, d1)
    oracle_branch, oracle_wrapped = branch_index_and_wrapped(raw)
    assert int(result.branch_index[0]) == expected_branch
    assert int(np.asarray(oracle_branch).reshape(())) == expected_branch
    assert result.omega[0] == -math.pi
    assert float(np.asarray(oracle_wrapped).reshape(())) == -math.pi
    assert bool(result.tie_edge_mask[0])


@pytest.mark.parametrize(
    "theta",
    [
        np.array([0.0, float("nan"), 0.0]),
        np.array([0.0, float("inf"), 0.0]),
        np.array([0.0, 1.0]),
    ],
)
def test_production_winding_fails_closed_on_invalid_phases(theta) -> None:
    d0, d1 = _standard_triangle_incidence()
    with pytest.raises(WindingError):
        phase_winding(theta, d0, d1)


def test_origin_shift_identity_matches_production_helper() -> None:
    """Both sides use p' = p - Q_net * a under origin shift a."""
    q = np.array([2, -1, 0], dtype=np.int64)
    coords = np.array([[1.0, 0.0], [-1.0, 0.0], [0.0, 2.0]])
    m0_expected = np.sum(q.astype(float)[:, None] * coords, axis=0)
    a = np.array([2.0, -1.5])
    shifted_expected = np.sum(q.astype(float)[:, None] * (coords - a), axis=0)
    m0_prod = signed_first_moment(q, coords)
    m1_prod = signed_first_moment(q, coords - a)
    m1_helper = origin_shifted_moment(m0_prod, int(q.sum()), a)
    np.testing.assert_allclose(m0_prod, m0_expected, atol=1e-12)
    np.testing.assert_allclose(m1_prod, shifted_expected, atol=1e-12)
    np.testing.assert_allclose(m1_helper, shifted_expected, atol=1e-12)
    cm = charge_moments(q, coords)
    assert cm.net_charge == 1
    assert cm.abs_charge == 3
    # Dipole with both signs → separation defined in production.
    assert cm.charge_separation_defined is True
    assert cm.charge_separation == pytest.approx(2.0)


def test_production_missing_sign_separation_is_explicitly_undefined() -> None:
    q = np.array([1, 0, 0], dtype=np.int64)
    coords = np.array([[1.0, 0.0], [-1.0, 0.0], [0.0, 2.0]])
    result = charge_moments(q, coords)
    assert result.charge_separation_defined is False
    assert math.isnan(result.charge_separation)
    assert result.status == "undefined_separation"
