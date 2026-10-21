"""Run the independent Round-6 Hodge decomposition numerical audit."""
from __future__ import annotations

from typing import Any, Dict, List

import numpy as np

from tools.hodge_decomposition_audit.charges import (
    compare_charges_under_weight_change,
    circulatory_integer_omega,
    confidence_weighted_scores,
    raw_integer_face_charges,
)
from tools.hodge_decomposition_audit.fixtures import ALL_FIXTURES
from tools.hodge_decomposition_audit.hodge_oracle import decompose
from tools.hodge_decomposition_audit.incidence import validate_incidence
from tools.hodge_decomposition_audit.schema import (
    ALGEBRAIC_IDENTITIES,
    AUDIT_STATUS,
    CLAIM_SCOPE,
    DEFAULT_ATOL,
    EVIDENCE_CLASS,
    NUMERICAL_TOLERANCE_DEPENDENCIES,
    SCHEMA_VERSION,
    BoundaryClass,
)


def _fixture_audit(builder) -> Dict[str, Any]:
    complex_ = builder()
    incidence = validate_incidence(complex_)
    rng = np.random.default_rng(20261017)
    omega = rng.normal(size=complex_.num_edges)
    w_uniform = np.ones(complex_.num_edges, dtype=float)
    w_varied = rng.uniform(0.5, 2.0, size=complex_.num_edges)

    decomp_u = decompose(complex_, omega, weights_edges=w_uniform)
    decomp_v = decompose(complex_, omega, weights_edges=w_varied)

    circ_omega, circ_note = circulatory_integer_omega(complex_, strength=1)
    charges = raw_integer_face_charges(complex_, circ_omega)
    charge_compare = compare_charges_under_weight_change(
        complex_, circ_omega, w_uniform, w_varied
    )
    face_conf = np.linspace(0.2, 1.0, complex_.num_triangles) if complex_.num_triangles else np.zeros(0)
    weighted_scores = (
        confidence_weighted_scores(charges, face_conf).tolist() if complex_.num_triangles else []
    )

    # Decomposition change under weights (when both accepted).
    decomp_changed = False
    if decomp_u.accepted and decomp_v.accepted:
        decomp_changed = not (
            np.allclose(decomp_u.exact, decomp_v.exact, atol=DEFAULT_ATOL)
            and np.allclose(decomp_u.coexact, decomp_v.coexact, atol=DEFAULT_ATOL)
            and np.allclose(decomp_u.harmonic, decomp_v.harmonic, atol=DEFAULT_ATOL)
        )

    # Ill-conditioned probe (extreme weights) — expect rejection.
    w_bad = np.ones(complex_.num_edges, dtype=float)
    if complex_.num_edges >= 2:
        w_bad[0] = 1e-16
        w_bad[1] = 1e16
    else:
        w_bad[0] = 1e-16
    decomp_bad = decompose(complex_, omega, weights_edges=w_bad)

    # Boundary-condition note on harmonic energy.
    harmonic_expectation = "not_assumed_zero"
    if complex_.boundary_class == BoundaryClass.DISK_WITH_BOUNDARY.value:
        harmonic_expectation = "expected_near_zero_for_generic_omega_but_measured_not_assumed"
    elif complex_.boundary_class == BoundaryClass.CLOSED_CYCLE_COMPLEX.value:
        harmonic_expectation = "nontrivial_harmonic_expected_for_circulation"
    elif complex_.boundary_class == BoundaryClass.ANNULUS_LIKE.value:
        harmonic_expectation = "nontrivial_harmonic_possible_b1_gt_0"

    return {
        "name": complex_.name,
        "boundary_class": complex_.boundary_class,
        "notes": complex_.notes,
        "num_vertices": complex_.num_vertices,
        "num_edges": complex_.num_edges,
        "num_triangles": complex_.num_triangles,
        "incidence": incidence,
        "incidence_ok": bool(
            incidence["d1_d0_is_zero"]
            and incidence["dimension_equations_ok"]
            and incidence["simplicial_closure_ok"]
        ),
        "decomp_uniform": {
            "accepted": decomp_u.accepted,
            "verdict": decomp_u.verdict,
            "ortho_exact_coexact": decomp_u.ortho_exact_coexact,
            "ortho_exact_harmonic": decomp_u.ortho_exact_harmonic,
            "ortho_coexact_harmonic": decomp_u.ortho_coexact_harmonic,
            "relative_energy_error": decomp_u.relative_energy_error,
            "relative_reconstruction_error": decomp_u.relative_reconstruction_error,
            "energy_harmonic": decomp_u.energy_harmonic,
            "cond_L0": decomp_u.cond_L0,
            "cond_M": decomp_u.cond_M,
        },
        "decomp_varied_weights": {
            "accepted": decomp_v.accepted,
            "verdict": decomp_v.verdict,
            "energy_exact": decomp_v.energy_exact,
            "energy_coexact": decomp_v.energy_coexact,
            "energy_harmonic": decomp_v.energy_harmonic,
            "cond_L0": decomp_v.cond_L0,
            "cond_M": decomp_v.cond_M,
        },
        "weighting_changes_decomposition": decomp_changed,
        "integer_charges_invariant_under_W1": charge_compare["charges_identical"],
        "charge_compare": charge_compare,
        "circulation_omega_note": circ_note,
        "raw_integer_charges": [int(x) for x in charges],
        "confidence_weighted_scores": weighted_scores,
        "ill_conditioned_probe": {
            "accepted": decomp_bad.accepted,
            "verdict": decomp_bad.verdict,
            "reject_reason": (decomp_bad.diagnostics or {}).get("reject_reason"),
            "cond_L0": decomp_bad.cond_L0,
            "cond_M": decomp_bad.cond_M,
        },
        "harmonic_expectation": harmonic_expectation,
        "decomp_verdict": decomp_u.verdict,
        "cond_L0": decomp_u.cond_L0,
        "energy_harmonic": decomp_u.energy_harmonic,
    }


def run_audit() -> Dict[str, Any]:
    fixtures: List[Dict[str, Any]] = [_fixture_audit(b) for b in ALL_FIXTURES]
    all_incidence_ok = all(f["incidence_ok"] for f in fixtures)
    all_well_conditioned_ok = all(
        f["decomp_uniform"]["accepted"] and f["decomp_varied_weights"]["accepted"] for f in fixtures
    )
    all_ill_rejected = all(
        f["ill_conditioned_probe"]["verdict"] == "REJECTED_ILL_CONDITIONED" for f in fixtures
    )
    charges_invariant = all(f["integer_charges_invariant_under_W1"] for f in fixtures)

    return {
        "schema_version": SCHEMA_VERSION,
        "evidence_class": EVIDENCE_CLASS,
        "audit_status": AUDIT_STATUS,
        "claim_scope": CLAIM_SCOPE,
        "proposal_imported": False,
        "proposal_claimed_passed": False,
        "scientific_validated_claimed": False,
        "proposal_reference": {
            "note": (
                "Open PR #385 owns experimental/phase_cochain_reference/**. "
                "This audit builds an independent fixture oracle on main and does not "
                "claim that proposal passed."
            ),
            "pr": 385,
            "owned_elsewhere": "experimental/phase_cochain_reference/",
        },
        "algebraic_identities": list(ALGEBRAIC_IDENTITIES),
        "numerical_tolerance_dependencies": list(NUMERICAL_TOLERANCE_DEPENDENCIES),
        "fixtures": fixtures,
        "summary": {
            "all_incidence_ok": all_incidence_ok,
            "all_well_conditioned_accepted": all_well_conditioned_ok,
            "all_ill_conditioned_rejected": all_ill_rejected,
            "integer_charges_invariant_under_W1": charges_invariant,
            "engineering_checks_ok": bool(
                all_incidence_ok
                and all_well_conditioned_ok
                and all_ill_rejected
                and charges_invariant
            ),
        },
        "limitations": [
            "SYNTHETIC_ONLY / HOLD — not scientific VALIDATED.",
            "No SciPy, no external datasets, no participant data.",
            "Mesh generation and winding-charge metric lanes were not edited.",
            "Numerical residuals depend on conditioning and scale; see NUMERICAL_TOLERANCE_DEPENDENCIES.",
        ],
    }
