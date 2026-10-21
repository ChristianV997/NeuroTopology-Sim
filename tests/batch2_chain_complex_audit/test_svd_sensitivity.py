"""Exact rational rank vs float SVD — report instability, do not pick a tol."""

from __future__ import annotations

from fractions import Fraction

import numpy as np
import pytest

from tools.batch2_chain_complex_audit.fixtures import (
    filled_tetrahedron,
    open_triangular_prism,
    tetrahedron_surface,
)
from tools.batch2_chain_complex_audit.rank import (
    exact_rank,
    float_svd_rank,
    svd_rank_sensitivity,
)


def test_exact_rank_identity():
    eye = [[Fraction(1), 0], [0, Fraction(1)]]
    assert exact_rank(eye) == 2


def test_exact_rank_dependent_rows():
    m = [
        [Fraction(1), Fraction(2)],
        [Fraction(2), Fraction(4)],
    ]
    assert exact_rank(m) == 1


def test_svd_requires_explicit_tol():
    with pytest.raises(TypeError):
        float_svd_rank([[1.0, 0.0], [0.0, 1.0]])  # tol is keyword-only required


def test_open_prism_exact_vs_svd_stable_at_loose_tols():
    c = open_triangular_prism()
    d2 = c.boundary_2()
    report = svd_rank_sensitivity(
        d2, tolerances=(1e-12, 1e-9, 1e-6, 1e-3)
    )
    assert report["exact_rank"] == c.ranks()["rank_d2"]
    # Well-conditioned integer boundary matrices should agree at these tols.
    assert report["unstable"] is False
    assert report["mismatches_vs_exact"] == {}


def test_near_dependent_rows_svd_unstable_across_tols():
    """Construct a float matrix whose SVD rank flips with tolerance.

    Row1 ≈ 2 * Row0 with a tiny residual → exact rational rank of the
    Fraction truncation may differ; we build the float matrix directly and
    show SVD ranks disagree across declared tolerances (instability report).
    """
    eps = 1e-10
    m = [
        [1.0, 0.0, 0.0],
        [2.0, eps, 0.0],
        [0.0, 0.0, 1.0],
    ]
    # Exact Fraction conversion of these floats is messy; use float path only
    # for the sensitivity report, and compute a rationalized companion separately.
    tols = (1e-12, 1e-9, 1e-6, 1e-3)
    ranks = {repr(t): float_svd_rank(m, tol=t) for t in tols}
    # At least two distinct numerical ranks across the declared grid
    assert len(set(ranks.values())) > 1, ranks

    # Rational companion: treat eps as exact Fraction(1, 10**10)
    m_q = [
        [Fraction(1), Fraction(0), Fraction(0)],
        [Fraction(2), Fraction(1, 10**10), Fraction(0)],
        [Fraction(0), Fraction(0), Fraction(1)],
    ]
    report = svd_rank_sensitivity(m_q, tolerances=tols)
    assert report["exact_rank"] == 3
    assert report["unstable"] is True
    # Do not silently select a tolerance — callers must read the report.
    assert report["agrees_all_tols"] is False


def test_tetrahedron_boundaries_exact_ranks():
    hollow = tetrahedron_surface()
    solid = filled_tetrahedron()
    assert hollow.ranks()["rank_d1"] == 3
    assert hollow.ranks()["rank_d2"] == 3  # β2 = 4 - 3 - 0 = 1
    assert solid.ranks()["rank_d3"] == 1
    assert solid.ranks()["rank_d2"] == 3  # β2 = 4 - 3 - 1 = 0


def test_empty_matrix_ranks():
    assert exact_rank([]) == 0
    assert exact_rank([[]]) == 0
    assert float_svd_rank([], tol=1e-9) == 0
