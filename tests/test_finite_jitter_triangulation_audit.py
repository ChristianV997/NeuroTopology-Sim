from __future__ import annotations

import json
import math
import subprocess
import sys
import tempfile
import unittest
from fractions import Fraction
from pathlib import Path

from tools.audit_finite_jitter_triangulation import audit_triangulation


REPO_ROOT = Path(__file__).resolve().parents[1]
AUDITOR = REPO_ROOT / "tools" / "audit_finite_jitter_triangulation.py"


PointValue = float | Fraction
TestPoint = tuple[PointValue, PointValue]


def _orient(a: TestPoint, b: TestPoint, c: TestPoint) -> PointValue:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _sixteen_point_fixture() -> tuple[list[tuple[float, float]], list[tuple[int, int, int]]]:
    """Six inner and ten outer points, with a deterministic annulus zipper mesh."""
    outer_count = 10
    inner_count = 6
    inner_phase = math.pi / 9.0
    outer_angles = [2.0 * math.pi * i / outer_count for i in range(outer_count)]
    inner_angles = [inner_phase + 2.0 * math.pi * i / inner_count for i in range(inner_count)]
    points = [(math.cos(a), math.sin(a)) for a in outer_angles]
    points.extend((0.4 * math.cos(a), 0.4 * math.sin(a)) for a in inner_angles)

    triangles: list[tuple[int, int, int]] = []
    outer_steps = 0
    inner_steps = 0
    for _ in range(outer_count + inner_count):
        next_outer = (
            2.0 * math.pi * (outer_steps + 1) / outer_count
            if outer_steps < outer_count
            else math.inf
        )
        next_inner = (
            inner_phase + 2.0 * math.pi * (inner_steps + 1) / inner_count
            if inner_steps < inner_count
            else math.inf
        )
        outer = outer_steps % outer_count
        inner = outer_count + (inner_steps % inner_count)
        if next_outer <= next_inner:
            nxt = (outer_steps + 1) % outer_count
            triangle = (outer, nxt, inner)
            outer_steps += 1
        else:
            nxt = outer_count + ((inner_steps + 1) % inner_count)
            triangle = (outer, inner, nxt)
            inner_steps += 1
        a, b, c = (points[i] for i in triangle)
        if _orient(a, b, c) < 0.0:
            triangle = (triangle[0], triangle[2], triangle[1])
        triangles.append(triangle)

    anchor = outer_count
    triangles.extend(
        (anchor, anchor + i, anchor + i + 1)
        for i in range(1, inner_count - 1)
    )
    return points, triangles


def _exact_rational_sixteen_point_fixture() -> tuple[list[TestPoint], list[tuple[int, int, int]]]:
    """Six and ten exactly cocircular rational points at radii 0.4 and 1.0."""
    outer_parameters = [
        Fraction(0), Fraction(1, 3), Fraction(3, 4), Fraction(7, 5), Fraction(3),
        None, Fraction(-3), Fraction(-7, 5), Fraction(-3, 4), Fraction(-1, 3),
    ]
    inner_parameters = [
        Fraction(1, 6), Fraction(5, 6), Fraction(11, 4),
        Fraction(-17, 3), Fraction(-6, 5), Fraction(-3, 8),
    ]

    def point_on_circle(parameter: Fraction | None, radius: Fraction) -> TestPoint:
        if parameter is None:
            return (-radius, Fraction(0))
        denominator = 1 + parameter * parameter
        return (
            radius * (1 - parameter * parameter) / denominator,
            radius * (2 * parameter) / denominator,
        )

    points: list[TestPoint] = [point_on_circle(value, Fraction(1)) for value in outer_parameters]
    points.extend(point_on_circle(value, Fraction(2, 5)) for value in inner_parameters)

    def angle(index: int) -> float:
        return math.atan2(float(points[index][1]), float(points[index][0])) % (2.0 * math.pi)

    outer_ring = sorted(range(10), key=angle)
    inner_ring = sorted(range(10, 16), key=angle)
    outer_steps = 0
    inner_steps = 0
    triangles: list[tuple[int, int, int]] = []
    for _ in range(16):
        outer = outer_ring[outer_steps % 10]
        inner = inner_ring[inner_steps % 6]
        next_outer = outer_ring[(outer_steps + 1) % 10]
        next_inner = inner_ring[(inner_steps + 1) % 6]
        outer_angle = angle(next_outer) + (2.0 * math.pi if outer_steps + 1 >= 10 else 0.0)
        inner_angle = angle(next_inner) + (2.0 * math.pi if inner_steps + 1 >= 6 else 0.0)
        if outer_angle <= inner_angle:
            triangle = (outer, next_outer, inner)
            outer_steps += 1
        else:
            triangle = (outer, inner, next_inner)
            inner_steps += 1
        if _orient(*(points[index] for index in triangle)) < 0:
            triangle = (triangle[0], triangle[2], triangle[1])
        triangles.append(triangle)

    anchor = inner_ring[0]
    for position in range(1, len(inner_ring) - 1):
        triangle = (anchor, inner_ring[position], inner_ring[position + 1])
        if _orient(*(points[index] for index in triangle)) < 0:
            triangle = (triangle[0], triangle[2], triangle[1])
        triangles.append(triangle)
    return points, triangles


def _assert_geometry_consistent(test: unittest.TestCase, report: dict) -> None:
    test.assertTrue(report["geometry_checks_all_satisfied"], report["issues"])
    test.assertEqual(report["issues"], [])


class FiniteJitterTriangulationAuditTests(unittest.TestCase):
    def test_sixteen_point_fixture_has_claimed_combinatorics_and_independent_hull(self) -> None:
        points, triangles = _sixteen_point_fixture()
        report = audit_triangulation(points, triangles)

        _assert_geometry_consistent(self, report)
        self.assertEqual(report["decision"], "HOLD / SYNTHETIC_ONLY")
        self.assertEqual(report["counts"]["point_count"], 16)
        self.assertEqual(report["counts"]["triangle_count"], 20)
        self.assertEqual(report["counts"]["edge_count"], 35)
        self.assertEqual(report["counts"]["extreme_hull_vertex_count"], 10)
        self.assertEqual(report["counts"]["hull_boundary_vertex_count"], 10)
        self.assertEqual(report["metrics"]["expected_edge_count"], 35)
        self.assertEqual(report["metrics"]["expected_triangle_count"], 20)

    def test_exact_rational_fixture_is_cocircular_on_both_rings(self) -> None:
        points, triangles = _exact_rational_sixteen_point_fixture()

        self.assertTrue(all(x * x + y * y == 1 for x, y in points[:10]))
        self.assertTrue(all(x * x + y * y == Fraction(4, 25) for x, y in points[10:]))
        report = audit_triangulation(points, triangles)

        _assert_geometry_consistent(self, report)
        self.assertEqual(report["counts"]["triangle_count"], 20)
        self.assertEqual(report["counts"]["edge_count"], 35)
        self.assertEqual(report["counts"]["extreme_hull_vertex_count"], 10)

    def test_area_identity_and_angle_sorted_boundary_do_not_rule_out_overlap(self) -> None:
        points = [(0, 0), (1, 0), (1, 1), (0, 1)]
        # These two positive-area triangles overlap above edge 0-1; their areas
        # still sum to the square's area, and their inferred boundary vertices
        # angularly sort to the square's convex hull.
        report = audit_triangulation(points, [(0, 1, 2), (0, 1, 3)])

        self.assertTrue(report["checks"]["area_partition_identity"])
        self.assertEqual(
            report["metrics"]["triangle_area_twice_exact"],
            report["metrics"]["convex_hull_area_twice_exact"],
        )
        inferred_boundary = sorted({
            vertex
            for edge in report["hull"]["observed_boundary_edges"]
            for vertex in edge
        })
        center_x = sum(points[index][0] for index in inferred_boundary) / len(inferred_boundary)
        center_y = sum(points[index][1] for index in inferred_boundary) / len(inferred_boundary)
        angle_sorted = sorted(
            inferred_boundary,
            key=lambda index: math.atan2(points[index][1] - center_y, points[index][0] - center_x),
        )
        angle_area_twice = abs(sum(
            points[index][0] * points[angle_sorted[(position + 1) % len(angle_sorted)]][1]
            - points[angle_sorted[(position + 1) % len(angle_sorted)]][0] * points[index][1]
            for position, index in enumerate(angle_sorted)
        ))
        self.assertEqual(
            Fraction.from_float(angle_area_twice),
            Fraction(report["metrics"]["convex_hull_area_twice_exact"]),
        )
        self.assertTrue(report["checks"]["all_input_points_covered"])
        self.assertTrue(report["checks"]["nonzero_triangle_areas"])
        self.assertTrue(report["checks"]["consistent_triangle_orientation"])
        self.assertTrue(report["checks"]["edge_incidence_valid"])
        self.assertTrue(report["checks"]["euler_counts_match"])
        self.assertFalse(report["checks"]["noncrossing_edges"])
        self.assertFalse(report["checks"]["nonoverlapping_triangles"])
        self.assertFalse(report["checks"]["boundary_matches_independent_hull"])
        self.assertFalse(report["geometry_checks_all_satisfied"])

    def test_near_cocircular_perturbation_accepts_either_planar_diagonal(self) -> None:
        delta = 1e-12
        points = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0 + delta), (0.0, 1.0)]
        first_diagonal = [(0, 1, 2), (0, 2, 3)]
        second_diagonal = [(0, 1, 3), (1, 2, 3)]

        for triangles in (first_diagonal, second_diagonal):
            with self.subTest(triangles=triangles):
                _assert_geometry_consistent(self, audit_triangulation(points, triangles))

    def test_near_collinear_positive_area_is_not_discarded_by_an_absolute_tolerance(self) -> None:
        points = [(0.0, 0.0), (1.0, 0.0), (0.5, 1e-30)]
        report = audit_triangulation(points, [(0, 1, 2)])

        _assert_geometry_consistent(self, report)
        self.assertNotEqual(report["metrics"]["triangle_area_twice_exact"], "0/1")

    def test_hull_edge_points_are_required_in_the_independent_boundary_chain(self) -> None:
        points = [(0, 0), (0.5, 0), (1, 0), (1, 1), (0, 1)]
        triangles = [(4, 0, 1), (4, 1, 2), (4, 2, 3)]
        report = audit_triangulation(points, triangles)

        _assert_geometry_consistent(self, report)
        self.assertEqual(report["counts"]["extreme_hull_vertex_count"], 4)
        self.assertEqual(report["counts"]["hull_boundary_vertex_count"], 5)

    def test_reordered_vertices_preserve_geometric_result(self) -> None:
        points, triangles = _sixteen_point_fixture()
        original = audit_triangulation(points, triangles)
        permutation = [7, 2, 13, 0, 15, 4, 9, 1, 10, 5, 12, 3, 14, 6, 11, 8]
        remap = {old_index: new_index for new_index, old_index in enumerate(permutation)}
        reordered_points = [points[i] for i in permutation]
        reordered_triangles = [tuple(remap[i] for i in tri) for tri in triangles]
        reordered = audit_triangulation(reordered_points, reordered_triangles)

        _assert_geometry_consistent(self, original)
        _assert_geometry_consistent(self, reordered)
        for key in ("point_count", "triangle_count", "edge_count", "extreme_hull_vertex_count"):
            self.assertEqual(original["counts"][key], reordered["counts"][key])
        self.assertEqual(
            original["metrics"]["triangle_area_twice_exact"],
            reordered["metrics"]["triangle_area_twice_exact"],
        )

    def test_well_conditioned_translation_and_extreme_scalings(self) -> None:
        points, triangles = _sixteen_point_fixture()
        transforms = (
            (1e-100, 0.0, 0.0),
            (1e100, 0.0, 0.0),
            (1.0, 2**30, -(2**30)),
        )
        for scale, tx, ty in transforms:
            transformed = [(scale * x + tx, scale * y + ty) for x, y in points]
            with self.subTest(scale=scale, translation=(tx, ty)):
                report = audit_triangulation(transformed, triangles)
                _assert_geometry_consistent(self, report)
                self.assertEqual(report["counts"]["triangle_count"], 20)
                self.assertEqual(report["counts"]["edge_count"], 35)

    def test_relative_finite_jitter_can_be_lost_after_large_translation(self) -> None:
        points = [(0.0, 0.0), (1.0, 0.0), (0.0, 1.0)]
        span = 1.0
        jitter = 1e-10 * span
        signs = [(1.0, -1.0), (-1.0, 1.0), (1.0, 1.0)]
        jittered_at_origin = [
            (x + jitter * sx, y + jitter * sy)
            for (x, y), (sx, sy) in zip(points, signs)
        ]
        offset = float(2**30)
        translated = [(x + offset, y - offset) for x, y in points]
        jittered_after_translation = [
            (x + jitter * sx, y + jitter * sy)
            for (x, y), (sx, sy) in zip(translated, signs)
        ]

        self.assertNotEqual(jittered_at_origin, points)
        self.assertEqual(jittered_after_translation, translated)
        _assert_geometry_consistent(self, audit_triangulation(translated, [(0, 1, 2)]))

    def test_missing_point_is_reported_as_uncovered(self) -> None:
        report = audit_triangulation(
            [(0, 0), (1, 0), (1, 1), (0, 1)],
            [(0, 1, 2)],
        )

        self.assertFalse(report["checks"]["all_input_points_covered"])
        self.assertEqual(report["uncovered_point_indices"], [3])
        self.assertFalse(report["geometry_checks_all_satisfied"])

    def test_inconsistent_orientation_and_nonmanifold_incidence_are_reported(self) -> None:
        square = [(0, 0), (1, 0), (1, 1), (0, 1)]
        mixed = audit_triangulation(square, [(0, 1, 2), (0, 3, 2)])
        self.assertFalse(mixed["checks"]["consistent_triangle_orientation"])

        three_sides = [(0, 0), (2, 0), (1, 2), (1, 1), (1, -1)]
        nonmanifold = audit_triangulation(
            three_sides,
            [(0, 1, 2), (1, 0, 3), (0, 1, 4)],
        )
        self.assertFalse(nonmanifold["checks"]["edge_incidence_valid"])

    def test_disconnected_mesh_and_malformed_degenerate_inputs_are_held(self) -> None:
        disconnected = audit_triangulation(
            [(0, 0), (1, 0), (0, 1), (3, 0), (4, 0), (3, 1)],
            [(0, 1, 2), (3, 4, 5)],
        )
        self.assertFalse(disconnected["checks"]["edge_connected"])

        collinear = audit_triangulation([(0, 0), (1, 0), (2, 0)], [(0, 1, 2)])
        self.assertFalse(collinear["checks"]["nondegenerate_convex_hull"])
        self.assertFalse(collinear["geometry_checks_all_satisfied"])

        duplicate = audit_triangulation([(0, 0), (1, 0), (0, 1), (0, 0)], [(0, 1, 2)])
        self.assertFalse(duplicate["checks"]["coordinates_unique"])

        bad_index = audit_triangulation([(0, 0), (1, 0), (0, 1)], [(0, 1, 3)])
        self.assertFalse(bad_index["checks"]["triangles_well_formed"])

        nonfinite = audit_triangulation([(0, 0), (1, 0), (0, float("nan"))], [(0, 1, 2)])
        self.assertFalse(nonfinite["checks"]["coordinates_finite"])

    def test_cli_reads_json_and_emits_hold_scope(self) -> None:
        payload = {
            "points": [[0, 0], [1, 0], [1, 1], [0, 1]],
            "triangles": [[0, 1, 2], [0, 2, 3]],
        }
        with tempfile.TemporaryDirectory() as temporary_directory:
            input_path = Path(temporary_directory) / "mesh.json"
            input_path.write_text(json.dumps(payload), encoding="utf-8")
            completed = subprocess.run(
                [sys.executable, str(AUDITOR), "--input", str(input_path)],
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        emitted = json.loads(completed.stdout)
        self.assertEqual(emitted["decision"], "HOLD / SYNTHETIC_ONLY")
        self.assertTrue(emitted["geometry_checks_all_satisfied"], emitted["issues"])

    def test_auditor_has_no_scipy_import(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                "-c",
                "import sys; from tools.audit_finite_jitter_triangulation import audit_triangulation; "
                "assert not any(name == 'scipy' or name.startswith('scipy.') for name in sys.modules)",
            ],
            check=False,
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)


if __name__ == "__main__":
    unittest.main()
