"""Independent Round 6 winding/charge oracle tests (SYNTHETIC_ONLY).

These tests exercise the specification oracle under
``tools/experimental_audits/winding_charge_round6``. They do **not** import
``experimental.phase_cochain_reference`` (Gemini candidate / PR #385).
"""

from __future__ import annotations

import json
import math

import numpy as np
import pytest

from tools.experimental_audits.winding_charge_round6.audit import (
    CHECK_FAIL,
    CHECK_PASS,
    run_conformance_audit,
)
from tools.experimental_audits.winding_charge_round6.fixtures import (
    dipole_complex,
    nonfinite_phase_vectors,
    phases_at_exact_pm_pi,
    single_triangle_complex,
    vortex_phases_minus,
    vortex_phases_plus,
)
from tools.experimental_audits.winding_charge_round6.oracle import (
    IndependentComplex,
    apply_confidence_weights,
    branch_index_and_wrapped,
    charge_moments,
    net_charge,
    shift_origin,
    topological_charges_from_phases,
    translate_coordinates,
    triangle_loop_winding,
    wrap_principal,
)


def test_oracle_does_not_import_candidate_engine():
    import sys

    import tools.experimental_audits.winding_charge_round6.audit  # noqa: F401
    import tools.experimental_audits.winding_charge_round6.oracle  # noqa: F401

    loaded = [name for name in sys.modules if "phase_cochain_reference" in name]
    assert loaded == [], f"candidate engine modules loaded: {loaded}"
    # Source may mention the candidate by name in disclaimers; imports must not.
    from pathlib import Path

    for rel in (
        "tools/experimental_audits/winding_charge_round6/oracle.py",
        "tools/experimental_audits/winding_charge_round6/audit.py",
    ):
        src = Path(rel).read_text(encoding="utf-8")
        assert "from experimental.phase_cochain_reference" not in src
        assert "import experimental.phase_cochain_reference" not in src


def test_oracle_import_does_not_load_production_winding_module():
    import subprocess
    import sys

    probe = (
        "import sys; "
        "import tools.experimental_audits.winding_charge_round6.audit; "
        "import tools.experimental_audits.winding_charge_round6.oracle; "
        "loaded = [name for name in sys.modules if "
        "name == 'neurotopology_sim.experimental.topology.winding' or "
        "name.startswith('neurotopology_sim.experimental.topology.winding.')]; "
        "assert not loaded, loaded"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr


def test_integer_valued_charges():
    c = single_triangle_complex()
    q = topological_charges_from_phases(c, vortex_phases_plus())
    assert q.dtype == np.int64
    assert int(q[0]) == 1
    q_m = topological_charges_from_phases(c, vortex_phases_minus())
    assert int(q_m[0]) == -1


def test_orientation_reversal_and_cyclic_invariance():
    phases = vortex_phases_plus()
    assert triangle_loop_winding(phases, (0, 1, 2)) == 1
    assert triangle_loop_winding(phases, (1, 2, 0)) == 1
    assert triangle_loop_winding(phases, (2, 0, 1)) == 1
    assert triangle_loop_winding(phases, (0, 2, 1)) == -1
    assert triangle_loop_winding(phases, (2, 1, 0)) == -1
    assert triangle_loop_winding(phases, (1, 0, 2)) == -1


def test_phase_wrapping_invariance():
    c = single_triangle_complex()
    base = vortex_phases_plus()
    shifted = base + np.array([2.0 * np.pi, -4.0 * np.pi, 6.0 * np.pi])
    assert np.array_equal(
        topological_charges_from_phases(c, base),
        topological_charges_from_phases(c, shifted),
    )


def test_charge_conservation_dipole_net_zero():
    c = dipole_complex()
    phases = np.concatenate([vortex_phases_plus(), vortex_phases_minus()])
    q = topological_charges_from_phases(c, phases)
    assert int(np.sum(q)) == 0
    assert int(np.sum(np.abs(q))) == 2


def test_origin_shift_identity_qnet_zero():
    c = dipole_complex()
    charges = np.array([1, -1], dtype=np.int64)
    a = np.array([5.0, -2.5])
    m0 = charge_moments(c, charges).signed_first_moment
    m1 = charge_moments(shift_origin(c, a), charges).signed_first_moment
    assert m0 is not None and m1 is not None
    np.testing.assert_allclose(m1, m0)


def test_origin_shift_identity_qnet_nonzero():
    c = dipole_complex()
    charges = np.array([1, 0], dtype=np.int64)
    a = np.array([1.25, 3.5])
    m0 = charge_moments(c, charges).signed_first_moment
    m1 = charge_moments(shift_origin(c, a), charges).signed_first_moment
    assert m0 is not None and m1 is not None
    np.testing.assert_allclose(m1, m0 - a)  # −Q_net * a with Q_net=1
    # Equivalent translation form with v = −a
    m_t = charge_moments(translate_coordinates(c, -a), charges).signed_first_moment
    assert m_t is not None
    np.testing.assert_allclose(m_t, m0 - a)


def test_exact_and_near_pm_pi():
    vals = phases_at_exact_pm_pi()
    assert wrap_principal(vals["plus_pi"]) == pytest.approx(-math.pi)
    assert wrap_principal(vals["minus_pi"]) == pytest.approx(-math.pi)
    assert wrap_principal(vals["near_plus_pi"]) < math.pi
    assert wrap_principal(vals["near_minus_pi"]) >= -math.pi
    # just over +π should wrap near −π
    assert wrap_principal(vals["just_over_plus_pi"]) == pytest.approx(-math.pi, abs=1e-9)


def test_exact_pm_pi_branch_index_is_unambiguous():
    vals = phases_at_exact_pm_pi()
    n_plus, omega_plus = branch_index_and_wrapped(vals["plus_pi"])
    n_minus, omega_minus = branch_index_and_wrapped(vals["minus_pi"])
    assert int(np.asarray(n_plus).reshape(())) == 1
    assert int(np.asarray(n_minus).reshape(())) == 0
    assert float(np.asarray(omega_plus).reshape(())) == -math.pi
    assert float(np.asarray(omega_minus).reshape(())) == -math.pi


def test_no_charge_separation_is_nan_not_zero():
    c = single_triangle_complex()
    res = charge_moments(c, np.array([0], dtype=np.int64))
    assert res.charge_separation_defined is False
    assert math.isnan(res.charge_separation)
    assert res.charge_separation != 0.0


def test_only_positive_and_only_negative_undefined():
    c = single_triangle_complex()
    pos = charge_moments(c, np.array([2], dtype=np.int64))
    neg = charge_moments(c, np.array([-3], dtype=np.int64))
    assert pos.charge_separation_defined is False and math.isnan(pos.charge_separation)
    assert neg.charge_separation_defined is False and math.isnan(neg.charge_separation)
    # Dipole is defined
    d = dipole_complex(separation=4.0)
    both = charge_moments(d, np.array([1, -1], dtype=np.int64))
    assert both.charge_separation_defined is True
    assert both.charge_separation == pytest.approx(4.0)


def test_malformed_shapes_rejected():
    c = single_triangle_complex()
    with pytest.raises(ValueError):
        topological_charges_from_phases(c, np.array([0.0, 1.0]))
    with pytest.raises(ValueError):
        IndependentComplex(3, edges=((1, 0), (0, 2), (1, 2)), triangles=((0, 1, 2),))


def test_nonfinite_phase_and_coords_rejected():
    c = single_triangle_complex()
    for _, vec in nonfinite_phase_vectors(3):
        with pytest.raises(ValueError):
            topological_charges_from_phases(c, vec)
    bad = c.coordinates.copy()  # type: ignore[union-attr]
    bad[0, 0] = float("nan")
    bad_c = IndependentComplex(c.num_vertices, c.edges, c.triangles, bad)
    with pytest.raises(ValueError):
        charge_moments(bad_c, np.array([1], dtype=np.int64))


def test_confidence_weights_do_not_alter_integer_charges():
    q = np.array([1, -1, 0, 2], dtype=np.int64)
    original = q.copy()
    scores, q_out = apply_confidence_weights(q, np.array([0.5, 0.25, 1.0, 0.8]))
    assert np.array_equal(q, original)
    assert np.array_equal(q_out, original)
    np.testing.assert_allclose(scores, np.array([0.5, -0.25, 0.0, 1.6]))
    with pytest.raises(ValueError):
        apply_confidence_weights(q, np.array([0.5, 0.0, 1.0, 0.8]))


@pytest.mark.parametrize(
    "helper", ["net_charge", "apply_confidence_weights", "charge_moments"]
)
@pytest.mark.parametrize("invalid", [1.5, float("nan"), float("inf"), float("-inf")])
def test_charge_helpers_reject_noninteger_or_nonfinite_values(helper, invalid):
    c = single_triangle_complex()
    values = np.array([invalid], dtype=float)
    with pytest.raises(ValueError, match="charges must be finite integer-valued"):
        if helper == "net_charge":
            net_charge(values)
        elif helper == "apply_confidence_weights":
            apply_confidence_weights(values, None)
        else:
            charge_moments(c, values)


def test_charge_helpers_accept_exact_integer_floats():
    values = np.array([2.0, -1.0])
    assert net_charge(values) == 1
    scores, q_out = apply_confidence_weights(values, np.array([0.5, 2.0]))
    np.testing.assert_array_equal(q_out, np.array([2, -1], dtype=np.int64))
    np.testing.assert_allclose(scores, np.array([1.0, -2.0]))
    result = charge_moments(
        single_triangle_complex(), np.array([1.0])
    )
    assert result.net_charge == 1


def test_net_charge_accumulates_without_int64_overflow():
    maximum = int(np.iinfo(np.int64).max)
    assert net_charge(np.array([maximum, 1], dtype=np.int64)) == maximum + 1


def test_charge_moments_handles_int64_minimum_magnitude():
    minimum = int(np.iinfo(np.int64).min)
    result = charge_moments(
        single_triangle_complex(), np.array([minimum], dtype=np.int64)
    )
    assert result.net_charge == minimum
    assert result.abs_charge == -minimum
    assert result.negative_count == 1
    assert result.negative_centroid is not None


def test_full_audit_runner_hold_synthetic_only():
    report = run_conformance_audit()
    assert report.project_status == "HOLD"
    assert report.data_policy == "SYNTHETIC_ONLY"
    assert report.candidate_engine_touched is False
    assert report.summary[CHECK_FAIL] == 0
    assert report.summary[CHECK_PASS] >= 13
    payload = report.to_dict()
    assert payload["scientific_validated"] is False
    assert payload["scientific_pass"] is False
    # JSON serializable including NaN-free metadata (checks evidence may omit NaN)
    text = json.dumps(
        {k: v for k, v in payload.items() if k != "checks"},
        allow_nan=False,
    )
    assert "HOLD" in text


def test_cli_module_runs(tmp_path):
    import subprocess
    import sys

    out = tmp_path / "report.json"
    proc = subprocess.run(
        [sys.executable, "-m", "tools.experimental_audits.winding_charge_round6", "--json", str(out)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert out.exists()
    data = json.loads(out.read_text())
    assert data["project_status"] == "HOLD"
    assert data["data_policy"] == "SYNTHETIC_ONLY"
