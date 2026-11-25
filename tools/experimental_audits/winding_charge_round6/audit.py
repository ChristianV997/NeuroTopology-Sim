"""Executable conformance audit runner for Round 6 discrete identities.

Produces engineering conformance results only. Never emits scientific
VALIDATED/PASS labels. Project posture remains HOLD / SYNTHETIC_ONLY.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import numpy as np

from tools.experimental_audits.winding_charge_round6 import conventions
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
    shift_origin,
    topological_charges_from_phases,
    translate_coordinates,
    triangle_loop_winding,
    wrap_principal,
)

# Engineering-only vocabulary (scientific VALIDATED/PASS forbidden).
STATUS_HOLD = "HOLD"
STATUS_SYNTHETIC = "SYNTHETIC_ONLY"
CHECK_PASS = "DISCRETE_IDENTITY_HOLDS"
CHECK_FAIL = "DISCRETE_IDENTITY_FAILS"
CHECK_INCONCLUSIVE = "INCONCLUSIVE_INPUT"


@dataclass
class CheckResult:
    name: str
    status: str
    detail: str
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass
class AuditReport:
    project_status: str
    data_policy: str
    claim_scope: str
    oracle_identity: str
    candidate_engine_touched: bool
    generated_at_utc: str
    conventions: dict[str, Any]
    ambiguities: tuple[str, ...]
    checks: list[CheckResult]
    summary: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        # Never allow scientific promotion keys
        payload["scientific_validated"] = False
        payload["scientific_pass"] = False
        payload["note"] = (
            "Discrete identity conformance only; not a biological or clinical claim."
        )
        return payload

    def write_json(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n")


def _run(name: str, fn: Callable[[], tuple[str, str, dict[str, Any]]]) -> CheckResult:
    try:
        status, detail, evidence = fn()
        return CheckResult(name=name, status=status, detail=detail, evidence=evidence)
    except Exception as exc:  # noqa: BLE001 - audit must capture failures
        return CheckResult(
            name=name,
            status=CHECK_FAIL,
            detail=f"raised {type(exc).__name__}: {exc}",
            evidence={},
        )


def run_conformance_audit() -> AuditReport:
    checks: list[CheckResult] = []

    def integer_vortex() -> tuple[str, str, dict[str, Any]]:
        c = single_triangle_complex()
        q = topological_charges_from_phases(c, vortex_phases_plus())
        ok = q.dtype == np.int64 and int(q[0]) == 1
        return (
            CHECK_PASS if ok else CHECK_FAIL,
            f"q={q.tolist()}",
            {"q": q.tolist()},
        )

    def orientation_reversal() -> tuple[str, str, dict[str, Any]]:
        phases = vortex_phases_plus()
        w012 = triangle_loop_winding(phases, (0, 1, 2))
        w120 = triangle_loop_winding(phases, (1, 2, 0))
        w021 = triangle_loop_winding(phases, (0, 2, 1))
        ok = w012 == 1 and w120 == 1 and w021 == -1
        return (
            CHECK_PASS if ok else CHECK_FAIL,
            f"w012={w012}, w120={w120}, w021={w021}",
            {"w012": w012, "w120": w120, "w021": w021},
        )

    two_pi_shift = np.array([2.0 * np.pi, -4.0 * np.pi, 2.0 * np.pi])

    def phase_wrap_invariance() -> tuple[str, str, dict[str, Any]]:
        c = single_triangle_complex()
        base = vortex_phases_plus()
        shifted = base + two_pi_shift
        q0 = topological_charges_from_phases(c, base)
        q1 = topological_charges_from_phases(c, shifted)
        ok = np.array_equal(q0, q1)
        return (
            CHECK_PASS if ok else CHECK_FAIL,
            f"q0={q0.tolist()} q1={q1.tolist()}",
            {"q0": q0.tolist(), "q1": q1.tolist()},
        )

    def net_charge_conservation() -> tuple[str, str, dict[str, Any]]:
        c = dipole_complex()
        phases = np.concatenate([vortex_phases_plus(), vortex_phases_minus()])
        q = topological_charges_from_phases(c, phases)
        q_net = int(np.sum(q))
        q_abs = int(np.sum(np.abs(q)))
        ok = q_net == 0 and q_abs == 2 and set(map(int, q.tolist())) == {1, -1}
        return (
            CHECK_PASS if ok else CHECK_FAIL,
            f"q={q.tolist()} net={q_net} abs={q_abs}",
            {"q": q.tolist(), "net": q_net, "abs": q_abs},
        )

    def origin_shift_qnet0() -> tuple[str, str, dict[str, Any]]:
        c = dipole_complex()
        charges = np.array([1, -1], dtype=np.int64)
        a = np.array([3.5, -7.25])
        m0 = charge_moments(c, charges).signed_first_moment
        m1 = charge_moments(shift_origin(c, a), charges).signed_first_moment
        assert m0 is not None and m1 is not None
        # p_q(r-a) = p_q(r) - Q_net * a ; Q_net=0 ⇒ invariant
        ok = bool(np.allclose(m1, m0))
        return (
            CHECK_PASS if ok else CHECK_FAIL,
            f"m0={m0.tolist()} m1={m1.tolist()}",
            {"m0": m0.tolist(), "m1": m1.tolist(), "a": a.tolist()},
        )

    def origin_shift_qnet_nonzero() -> tuple[str, str, dict[str, Any]]:
        c = dipole_complex()
        charges = np.array([1, 0], dtype=np.int64)
        a = np.array([2.0, 1.0])
        m0 = charge_moments(c, charges).signed_first_moment
        m1 = charge_moments(shift_origin(c, a), charges).signed_first_moment
        assert m0 is not None and m1 is not None
        expected = m0 - 1 * a
        ok = bool(np.allclose(m1, expected))
        # Also verify translation form m(r+v)=m+Q_net*v with v=-a
        m_t = charge_moments(translate_coordinates(c, -a), charges).signed_first_moment
        ok = ok and m_t is not None and bool(np.allclose(m_t, expected))
        return (
            CHECK_PASS if ok else CHECK_FAIL,
            f"m0={m0.tolist()} m1={m1.tolist()} expected={expected.tolist()}",
            {
                "m0": m0.tolist(),
                "m1": m1.tolist(),
                "expected": expected.tolist(),
                "a": a.tolist(),
            },
        )

    def exact_pm_pi_branch() -> tuple[str, str, dict[str, Any]]:
        vals = phases_at_exact_pm_pi()
        wp = wrap_principal(vals["plus_pi"])
        wm = wrap_principal(vals["minus_pi"])
        n_p, o_p = branch_index_and_wrapped(vals["plus_pi"])
        n_m, o_m = branch_index_and_wrapped(vals["minus_pi"])
        ok = (
            float(wp) == float(-np.pi)
            and float(wm) == float(-np.pi)
            and float(o_p) == float(-np.pi)
            and float(o_m) == float(-np.pi)
            and int(np.asarray(n_p).reshape(())) == 1
            and int(np.asarray(n_m).reshape(())) == 0
        )
        # plus_pi: Δ=π ⇒ wrap→−π, n=(π−(−π))/2π=1
        # minus_pi: Δ=−π ⇒ wrap→−π, n=0
        return (
            CHECK_PASS if ok else CHECK_FAIL,
            f"wrap(+π)={wp}, wrap(−π)={wm}, n(+π)={n_p}, n(−π)={n_m}",
            {
                "wrap_plus_pi": float(wp),
                "wrap_minus_pi": float(wm),
                "n_plus_pi": int(np.asarray(n_p).reshape(())),
                "n_minus_pi": int(np.asarray(n_m).reshape(())),
                "near_plus": float(wrap_principal(vals["near_plus_pi"])),
                "near_minus": float(wrap_principal(vals["near_minus_pi"])),
            },
        )

    def no_charge_separation_undefined() -> tuple[str, str, dict[str, Any]]:
        c = single_triangle_complex()
        res = charge_moments(c, np.array([0], dtype=np.int64))
        ok = (
            (not res.charge_separation_defined)
            and isinstance(res.charge_separation, float)
            and np.isnan(res.charge_separation)
            and res.charge_separation != 0.0
        )
        return (
            CHECK_PASS if ok else CHECK_FAIL,
            f"defined={res.charge_separation_defined} sep={res.charge_separation}",
            {"defined": res.charge_separation_defined, "status": res.status},
        )

    def only_positive_undefined() -> tuple[str, str, dict[str, Any]]:
        c = single_triangle_complex()
        res = charge_moments(c, np.array([1], dtype=np.int64))
        ok = (not res.charge_separation_defined) and np.isnan(res.charge_separation)
        return (
            CHECK_PASS if ok else CHECK_FAIL,
            f"defined={res.charge_separation_defined}",
            {"positive_count": res.positive_count, "negative_count": res.negative_count},
        )

    def only_negative_undefined() -> tuple[str, str, dict[str, Any]]:
        c = single_triangle_complex()
        res = charge_moments(c, np.array([-1], dtype=np.int64))
        ok = (not res.charge_separation_defined) and np.isnan(res.charge_separation)
        return (
            CHECK_PASS if ok else CHECK_FAIL,
            f"defined={res.charge_separation_defined}",
            {"positive_count": res.positive_count, "negative_count": res.negative_count},
        )

    def malformed_shapes() -> tuple[str, str, dict[str, Any]]:
        c = single_triangle_complex()
        raised = 0
        for label, bad in (
            ("short", np.array([0.0, 1.0])),
            ("2d", np.zeros((3, 2))),
        ):
            try:
                topological_charges_from_phases(c, bad)  # type: ignore[arg-type]
            except ValueError:
                raised += 1
            else:
                return CHECK_FAIL, f"did not reject {label}", {}
        # Malformed complex edge order
        try:
            IndependentComplex(3, edges=((1, 0),), triangles=(), coordinates=None)
            return CHECK_FAIL, "accepted non-canonical edge", {}
        except ValueError:
            raised += 1
        return CHECK_PASS, f"rejected={raised}", {"rejected": raised}

    def nonfinite_inputs() -> tuple[str, str, dict[str, Any]]:
        c = single_triangle_complex()
        rejected = 0
        for name, vec in nonfinite_phase_vectors(3):
            try:
                topological_charges_from_phases(c, vec)
            except ValueError:
                rejected += 1
            else:
                return CHECK_FAIL, f"accepted nonfinite {name}", {}
        # Nonfinite coordinates should fail at moment time
        bad_coords = c.coordinates.copy()  # type: ignore[union-attr]
        bad_coords[0, 0] = float("nan")
        bad_c = IndependentComplex(c.num_vertices, c.edges, c.triangles, bad_coords)
        try:
            charge_moments(bad_c, np.array([1], dtype=np.int64))
            return CHECK_FAIL, "accepted nonfinite coordinates", {}
        except ValueError:
            rejected += 1
        return CHECK_PASS, f"rejected={rejected}", {"rejected": rejected}

    def confidence_weights_preserve_integers() -> tuple[str, str, dict[str, Any]]:
        q = np.array([1, -1, 0, 2], dtype=np.int64)
        w = np.array([0.5, 0.25, 1.0, 0.8])
        scores, q_out = apply_confidence_weights(q, w)
        ok = np.array_equal(q_out, q) and np.allclose(scores, w * q.astype(float))
        # Mutating scores must not affect q_out integers beyond the copy contract
        return (
            CHECK_PASS if ok else CHECK_FAIL,
            f"scores={scores.tolist()} q={q_out.tolist()}",
            {"scores": scores.tolist(), "q": q_out.tolist()},
        )

    checklist = [
        ("integer_valued_vortex_charge", integer_vortex),
        ("orientation_reversal_sign_convention", orientation_reversal),
        ("phase_wrapping_invariance_plus_2pi", phase_wrap_invariance),
        ("charge_conservation_net_zero_dipole", net_charge_conservation),
        ("origin_shift_identity_qnet_zero", origin_shift_qnet0),
        ("origin_shift_identity_qnet_nonzero", origin_shift_qnet_nonzero),
        ("exact_pm_pi_branch_convention", exact_pm_pi_branch),
        ("no_charge_separation_undefined", no_charge_separation_undefined),
        ("only_positive_separation_undefined", only_positive_undefined),
        ("only_negative_separation_undefined", only_negative_undefined),
        ("malformed_shapes_rejected", malformed_shapes),
        ("nonfinite_inputs_rejected", nonfinite_inputs),
        ("confidence_weights_do_not_alter_integer_charges", confidence_weights_preserve_integers),
    ]
    for name, fn in checklist:
        checks.append(_run(name, fn))

    summary = {
        CHECK_PASS: sum(1 for c in checks if c.status == CHECK_PASS),
        CHECK_FAIL: sum(1 for c in checks if c.status == CHECK_FAIL),
        CHECK_INCONCLUSIVE: sum(1 for c in checks if c.status == CHECK_INCONCLUSIVE),
    }
    return AuditReport(
        project_status=STATUS_HOLD,
        data_policy=STATUS_SYNTHETIC,
        claim_scope="discrete_identity_only",
        oracle_identity=(
            "independent specification oracle "
            "(tools/experimental_audits/winding_charge_round6); "
            "not a test of experimental/phase_cochain_reference"
        ),
        candidate_engine_touched=False,
        generated_at_utc=datetime.now(timezone.utc).isoformat(),
        conventions={
            "WRAP_INTERVAL": conventions.WRAP_INTERVAL,
            "BRANCH_AT_PLUS_PI": conventions.BRANCH_AT_PLUS_PI,
            "BRANCH_AT_MINUS_PI": conventions.BRANCH_AT_MINUS_PI,
            "BRANCH_INDEX_METHOD": conventions.BRANCH_INDEX_METHOD,
            "ORIGIN_SHIFT_IDENTITY": conventions.ORIGIN_SHIFT_IDENTITY,
            "COORDINATE_TRANSLATION_IDENTITY": conventions.COORDINATE_TRANSLATION_IDENTITY,
            "MISSING_SIGN_SEPARATION": conventions.MISSING_SIGN_SEPARATION,
        },
        ambiguities=conventions.AMBIGUITIES,
        checks=checks,
        summary=summary,
    )
