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
)
from tools.experimental_audits.winding_charge_round6.oracle import (
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
    q_rev_oracle = triangle_loop_winding(theta, (0, 2, 1))
    assert q_fwd == 1
    assert q_rev_oracle == -1


def test_origin_shift_identity_matches_production_helper() -> None:
    """Both sides use p' = p - Q_net * a under origin shift a."""
    q = np.array([1, -1, 0], dtype=np.int64)
    coords = np.array([[1.0, 0.0], [-1.0, 0.0], [0.0, 2.0]])
    m0 = signed_first_moment(q, coords)
    a = np.array([2.0, -1.5])
    m1_prod = origin_shifted_moment(m0, int(q.sum()), a)
    # Independent recomputation of the documented identity.
    m1_id = m0 - float(q.sum()) * a
    assert np.allclose(m1_prod, m1_id, atol=1e-12)
    cm = charge_moments(q, coords)
    assert cm.net_charge == 0
    # Dipole with both signs → separation defined in production.
    assert cm.charge_separation_defined is True
    assert cm.charge_separation == pytest.approx(2.0)
