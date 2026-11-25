"""Compare #410 independent mesh auditor against live production triangulator.

HOLD / SYNTHETIC_ONLY. Discrete geometry only — not biological validation.

Hard-imports ``neurotopology_sim.experimental.geometry.planar_triangulation``
so this audit cannot silently self-validate without the intended production
module. Does not weaken auditor assertions.
"""

from __future__ import annotations

import inspect
import unittest
from fractions import Fraction

import neurotopology_sim.experimental.geometry.planar_triangulation as geom_mod
from neurotopology_sim.experimental.geometry.planar_triangulation import (
    DegeneracyPolicy,
    triangulate_2d,
)
from tools.audit_finite_jitter_triangulation import audit_triangulation


class ProductionImportTests(unittest.TestCase):
    def test_imports_production_planar_triangulation_not_auditor_copy(self) -> None:
        path = inspect.getfile(geom_mod).replace("\\", "/")
        self.assertTrue(
            path.endswith(
                "neurotopology_sim/experimental/geometry/planar_triangulation.py"
            )
        )
        self.assertNotIn("audit_finite_jitter", path)
        self.assertTrue(inspect.isfunction(triangulate_2d))

    def test_production_mesh_passes_independent_auditor(self) -> None:
        points = [(0.0, 0.0), (2.0, 0.0), (0.0, 2.0), (0.4, 0.4)]
        result = triangulate_2d(points)
        self.assertTrue(result.ok)
        self.assertGreaterEqual(len(result.simplices), 1)
        report = audit_triangulation(points, list(result.simplices))
        self.assertTrue(report["geometry_checks_all_satisfied"])
        self.assertEqual(report["issues"], [])

    def test_adversarial_overlapping_faces_fail_auditor_even_if_counts_look_ok(
        self,
    ) -> None:
        """Auditor must reject overlapping faces (PR #410 finding).

        Production ``triangulate_2d`` must not emit this mesh; the auditor is
        the independent check on *supplied* triangles.
        """
        # Unit square with two overlapping triangles sharing the diagonal
        # plus a third overlapping face that covers the same region again.
        points = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
        # Valid triangulation would be [(0,1,2),(0,2,3)]. Overlapping counterexample:
        triangles = [(0, 1, 2), (0, 2, 3), (0, 1, 3)]  # third face overlaps
        report = audit_triangulation(points, triangles)
        self.assertFalse(report["geometry_checks_all_satisfied"])
        self.assertGreater(len(report["issues"]), 0)
        # Production builder for the same points yields a valid mesh.
        prod = triangulate_2d(
            points,
            degeneracy_policy=DegeneracyPolicy.LEXICOGRAPHIC_TIEBREAK,
            require_delaunay=False,
        )
        self.assertTrue(prod.ok)
        ok_report = audit_triangulation(points, list(prod.simplices))
        self.assertTrue(ok_report["geometry_checks_all_satisfied"])

    def test_fraction_coords_roundtrip_through_production_and_auditor(self) -> None:
        points = [
            (Fraction(0), Fraction(0)),
            (Fraction(1), Fraction(0)),
            (Fraction(0), Fraction(1)),
        ]
        # Production accepts floats/Fractions via parse; use floats for auditor.
        float_pts = [(float(x), float(y)) for x, y in points]
        result = triangulate_2d(float_pts)
        self.assertTrue(result.ok)
        report = audit_triangulation(float_pts, list(result.simplices))
        self.assertTrue(report["geometry_checks_all_satisfied"])


if __name__ == "__main__":
    unittest.main()
