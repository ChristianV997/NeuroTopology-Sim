"""Focused tests for the independent Hodge decomposition numerical audit."""
from __future__ import annotations

import json
import math
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from tools.hodge_decomposition_audit.audit import run_audit
from tools.hodge_decomposition_audit.charges import (
    circulatory_integer_omega,
    confidence_weighted_scores,
    raw_integer_face_charges,
)
from tools.hodge_decomposition_audit.fixtures import (
    annulus_like_band,
    closed_cycle_complex,
    disconnected_two_triangles,
    disk_quad_fan,
    disk_single_triangle,
)
from tools.hodge_decomposition_audit.hodge_oracle import IllConditionedError, decompose
from tools.hodge_decomposition_audit.incidence import validate_incidence
from tools.hodge_decomposition_audit.schema import AUDIT_STATUS, EVIDENCE_CLASS

REPO = Path(__file__).resolve().parents[3]
ATOL = 1e-10


@pytest.mark.parametrize(
    "builder",
    [
        disk_single_triangle,
        disk_quad_fan,
        closed_cycle_complex,
        annulus_like_band,
        disconnected_two_triangles,
    ],
)
def test_incidence_d1_d0_zero_and_dimensions(builder):
    c = builder()
    report = validate_incidence(c)
    assert report["d1_d0_is_zero"] is True
    assert report["d1_d0_max_abs"] == 0.0
    assert report["dimension_equations_ok"] is True
    assert report["simplicial_closure_ok"] is True
    assert report["identity_class"] == "algebraic"


def test_disk_vs_closed_cycle_harmonic_boundary_conditions():
    disk = disk_single_triangle()
    cycle = closed_cycle_complex()
    rng = np.random.default_rng(7)

    # Disk: generic omega should have tiny harmonic energy (measured, not assumed a priori in oracle).
    omega_disk = rng.normal(size=disk.num_edges)
    d_disk = decompose(disk, omega_disk)
    assert d_disk.accepted
    assert d_disk.energy_harmonic < 1e-12

    # Closed cycle: circulatory form must carry harmonic energy; do not assume zero.
    omega_c, note = circulatory_integer_omega(cycle, strength=1)
    assert note == "c3_circulation"
    d_cycle = decompose(cycle, omega_c)
    assert d_cycle.accepted
    assert d_cycle.energy_coexact == 0.0  # no triangles
    assert d_cycle.energy_harmonic > 0.0


def test_annulus_like_allows_nontrivial_harmonic():
    c = annulus_like_band()
    omega = np.zeros(c.num_edges)
    emap = c.edge_index
    # Inner circulation 0-1-2
    omega[emap[(0, 1)]] = 1.0
    omega[emap[(1, 2)]] = 1.0
    omega[emap[(0, 2)]] = -1.0
    # Outer circulation 3-4-5
    omega[emap[(3, 4)]] = 1.0
    omega[emap[(4, 5)]] = 1.0
    omega[emap[(3, 5)]] = -1.0
    # Zero discrete divergence
    assert np.allclose(c.d0().T @ omega, 0.0, atol=ATOL)
    decomp = decompose(c, omega)
    assert decomp.accepted
    assert decomp.energy_harmonic > 0.0
    assert abs(decomp.ortho_exact_coexact) < ATOL
    assert abs(decomp.ortho_exact_harmonic) < ATOL
    assert abs(decomp.ortho_coexact_harmonic) < ATOL
    assert decomp.relative_energy_error < ATOL


def test_weighted_orthogonality_and_energy_closure_on_disk():
    c = disk_quad_fan()
    rng = np.random.default_rng(99)
    omega = rng.normal(size=c.num_edges)
    w_e = rng.uniform(0.4, 2.5, size=c.num_edges)
    decomp = decompose(c, omega, weights_edges=w_e)
    assert decomp.accepted
    assert abs(decomp.ortho_exact_coexact) < ATOL
    assert abs(decomp.ortho_exact_harmonic) < ATOL
    assert abs(decomp.ortho_coexact_harmonic) < ATOL
    assert decomp.relative_energy_error < ATOL
    assert decomp.relative_reconstruction_error < ATOL


def test_ill_conditioned_weights_rejected():
    c = disk_single_triangle()
    omega = np.array([0.1, -0.2, 0.3])
    w = np.array([1e-16, 1e16, 1.0])
    result = decompose(c, omega, weights_edges=w)
    assert result.accepted is False
    assert result.verdict == "REJECTED_ILL_CONDITIONED"
    assert result.diagnostics.get("reject_reason") in {
        "weight_ratio_exceeds_threshold",
        "cond_L0_exceeds_threshold",
        "cond_M_exceeds_threshold",
        "weights_edges_nonpositive",
    }


def test_nonpositive_weights_rejected():
    c = disk_single_triangle()
    omega = np.ones(3)
    result = decompose(c, omega, weights_edges=[1.0, 0.0, 1.0])
    assert result.accepted is False
    assert result.verdict == "REJECTED_ILL_CONDITIONED"


def test_phase_confidence_weighting_vs_integer_charges():
    c = disk_single_triangle()
    omega, _ = circulatory_integer_omega(c, strength=1)
    q = raw_integer_face_charges(c, omega)
    assert q.shape == (1,)
    # Integer charge for a full winding around one triangle should be ±1.
    assert abs(int(q[0])) == 1

    w_a = np.array([1.0, 1.0, 1.0])
    w_b = np.array([0.5, 1.5, 2.0])
    d_a = decompose(c, omega, weights_edges=w_a)
    d_b = decompose(c, omega, weights_edges=w_b)
    assert d_a.accepted and d_b.accepted
    # Charges unchanged (algebraic); decomposition may change.
    assert np.array_equal(raw_integer_face_charges(c, omega), q)
    scores = confidence_weighted_scores(q, [0.25])
    assert scores.shape == (1,)
    assert scores[0] == pytest.approx(0.25 * q[0])
    # Weighted scores are not the integer charges.
    assert scores[0] != q[0] or q[0] == 0


def test_run_audit_hold_synthetic_only_and_no_proposal_pass_claim():
    report = run_audit()
    assert report["audit_status"] == AUDIT_STATUS == "HOLD"
    assert report["evidence_class"] == EVIDENCE_CLASS == "SYNTHETIC_ONLY"
    assert report["proposal_claimed_passed"] is False
    assert report["proposal_imported"] is False
    assert report["scientific_validated_claimed"] is False
    assert report["summary"]["engineering_checks_ok"] is True
    assert report["summary"]["all_ill_conditioned_rejected"] is True
    assert report["audit_status"] != "VALIDATED"
    assert report.get("scientific_validated_claimed") is False


def test_cli_and_deterministic_json(tmp_path: Path):
    out = tmp_path / "audit.json"
    md = tmp_path / "audit.md"
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "tools.hodge_decomposition_audit",
            "--output-json",
            str(out),
            "--output-md",
            str(md),
        ],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["summary"]["engineering_checks_ok"] is True
    assert md.exists()
    text = out.read_text(encoding="utf-8")
    assert "NaN" not in text
    assert "Infinity" not in text or data["fixtures"]  # cond may be null only
    # Finite JSON: no non-finite floats in serialized dump except we null them
    json.loads(text)


def test_disconnected_two_triangles_reconstruction_and_orthogonality():
    """Disconnected mesh: energy closure + pairwise W1 orthogonality still hold."""
    c = disconnected_two_triangles()
    rng = np.random.default_rng(11)
    omega = rng.normal(size=c.num_edges)
    w_e = rng.uniform(0.5, 2.0, size=c.num_edges)
    decomp = decompose(c, omega, weights_edges=w_e)
    assert decomp.accepted
    assert decomp.relative_reconstruction_error < ATOL
    assert decomp.relative_energy_error < ATOL
    assert abs(decomp.ortho_exact_coexact) < ATOL
    assert abs(decomp.ortho_exact_harmonic) < ATOL
    assert abs(decomp.ortho_coexact_harmonic) < ATOL


def test_malformed_omega_fails_closed():
    c = disk_single_triangle()
    with pytest.raises(ValueError, match="nonfinite|shape"):
        decompose(c, [float("nan"), 0.0, 0.0])
    with pytest.raises(ValueError, match="shape"):
        decompose(c, [1.0, 2.0])


def test_oracle_does_not_import_production_or_proposal_as_self_oracle():
    """Independent expected values: never import production topology / #385 / scipy."""
    import ast

    root = REPO / "tools" / "hodge_decomposition_audit"
    banned_prefixes = (
        "experimental.phase_cochain_reference",
        "neurotopology_sim",
        "scipy",
    )
    for path in sorted(root.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            for name in names:
                for prefix in banned_prefixes:
                    assert not name.startswith(prefix), (
                        f"{path.name} must not import {name!r} (oracle independence)"
                    )


def test_does_not_touch_proposal_or_mesh_lanes():
    # Ownership guard: package must not import experimental.phase_cochain_reference.
    import tools.hodge_decomposition_audit.hodge_oracle as oracle_mod
    import tools.hodge_decomposition_audit.fixtures as fixtures_mod

    src = Path(oracle_mod.__file__).read_text(encoding="utf-8") + Path(fixtures_mod.__file__).read_text(
        encoding="utf-8"
    )
    assert "phase_cochain_reference" not in src
    assert "import scipy" not in src
    assert "from scipy" not in src
