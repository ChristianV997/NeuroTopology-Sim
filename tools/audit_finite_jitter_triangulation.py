from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict, deque
from decimal import Decimal
from fractions import Fraction
from itertools import combinations
from pathlib import Path
from typing import Any, Sequence


_DECISION = "HOLD / SYNTHETIC_ONLY"
_SCOPE = (
    "Independent geometric consistency checks on supplied coordinates and triangle indices; "
    "not a production triangulator, Delaunay check, empirical result, or scientific validation."
)
_CHECK_NAMES = (
    "point_sequence_valid",
    "coordinates_finite",
    "coordinates_unique",
    "nondegenerate_convex_hull",
    "triangle_sequence_valid",
    "triangles_well_formed",
    "all_input_points_covered",
    "nonzero_triangle_areas",
    "consistent_triangle_orientation",
    "edge_incidence_valid",
    "edge_connected",
    "noncrossing_edges",
    "nonoverlapping_triangles",
    "boundary_matches_independent_hull",
    "euler_counts_match",
    "area_partition_identity",
)

_Point = tuple[Fraction, Fraction]
_Edge = tuple[int, int]
_Triangle = tuple[int, int, int]


def _new_report() -> dict[str, Any]:
    return {
        "schema_version": "finite-jitter-triangulation-audit/1",
        "decision": _DECISION,
        "scope": _SCOPE,
        "geometry_checks_all_satisfied": False,
        "counts": {
            "point_count": None,
            "triangle_count": None,
            "edge_count": None,
            "extreme_hull_vertex_count": None,
            "hull_boundary_vertex_count": None,
        },
        "checks": {name: None for name in _CHECK_NAMES},
        "metrics": {
            "triangle_area_twice_exact": None,
            "convex_hull_area_twice_exact": None,
            "expected_edge_count": None,
            "expected_triangle_count": None,
        },
        "hull": {
            "extreme_point_indices": [],
            "boundary_point_indices": [],
            "expected_boundary_edges": [],
            "observed_boundary_edges": [],
        },
        "uncovered_point_indices": [],
        "edge_crossings": [],
        "triangle_intersections": [],
        "issues": [],
    }


def _issue(report: dict[str, Any], check: str, detail: str) -> None:
    report["checks"][check] = False
    message = f"{check}: {detail}"
    if message not in report["issues"]:
        report["issues"].append(message)


def _fraction(value: Any) -> Fraction:
    if isinstance(value, bool):
        raise ValueError("boolean coordinate is not numeric geometry")
    if isinstance(value, int):
        return Fraction(value)
    if isinstance(value, Fraction):
        return value
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("coordinate is not finite")
        return Fraction(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("coordinate is not finite")
        return Fraction.from_float(value)
    raise ValueError("coordinate must be an integer, fraction, finite float, or finite decimal")


def _orientation(a: _Point, b: _Point, c: _Point) -> Fraction:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _shoelace_twice(points: Sequence[_Point]) -> Fraction:
    total = Fraction(0)
    for i in range(len(points)):
        next_point = points[(i + 1) % len(points)]
        total += points[i][0] * next_point[1] - next_point[0] * points[i][1]
    return total


def _strict_hull(points: Sequence[_Point]) -> list[int]:
    ordered = sorted(range(len(points)), key=lambda index: (points[index][0], points[index][1]))

    def half(indices: Sequence[int]) -> list[int]:
        chain: list[int] = []
        for index in indices:
            while len(chain) >= 2 and _orientation(
                points[chain[-2]], points[chain[-1]], points[index]
            ) <= 0:
                chain.pop()
            chain.append(index)
        return chain

    lower = half(ordered)
    upper = half(list(reversed(ordered)))
    return lower[:-1] + upper[:-1]


def _on_segment(a: _Point, b: _Point, point: _Point) -> bool:
    return (
        _orientation(a, b, point) == 0
        and min(a[0], b[0]) <= point[0] <= max(a[0], b[0])
        and min(a[1], b[1]) <= point[1] <= max(a[1], b[1])
    )


def _hull_boundary(points: Sequence[_Point], hull: Sequence[int]) -> tuple[list[int], list[_Edge]]:
    boundary: list[int] = []
    edges: list[_Edge] = []
    for start, end in zip(hull, (*hull[1:], hull[0])):
        a, b = points[start], points[end]
        dx, dy = b[0] - a[0], b[1] - a[1]
        on_edge = [index for index, point in enumerate(points) if _on_segment(a, b, point)]
        on_edge.sort(key=lambda index: (points[index][0] - a[0]) * dx + (points[index][1] - a[1]) * dy)
        if not on_edge or on_edge[0] != start or on_edge[-1] != end:
            continue
        boundary.extend(on_edge[:-1])
        for left, right in zip(on_edge, on_edge[1:]):
            edges.append((min(left, right), max(left, right)))
    return boundary, sorted(set(edges))


def _parse_points(raw_points: Any, report: dict[str, Any]) -> list[_Point] | None:
    if not isinstance(raw_points, (list, tuple)):
        _issue(report, "point_sequence_valid", "points must be a list or tuple")
        report["checks"]["coordinates_finite"] = False
        return None
    report["checks"]["point_sequence_valid"] = True
    report["counts"]["point_count"] = len(raw_points)
    points: list[_Point] = []
    for index, pair in enumerate(raw_points):
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            _issue(report, "point_sequence_valid", f"point {index} must contain exactly two coordinates")
            report["checks"]["coordinates_finite"] = False
            return None
        try:
            points.append((_fraction(pair[0]), _fraction(pair[1])))
        except (TypeError, ValueError, OverflowError) as exc:
            _issue(report, "coordinates_finite", f"point {index}: {exc}")
            return None
    report["checks"]["coordinates_finite"] = True
    return points


def _parse_triangles(raw_triangles: Any, point_count: int, report: dict[str, Any]) -> list[_Triangle] | None:
    if not isinstance(raw_triangles, (list, tuple)):
        _issue(report, "triangle_sequence_valid", "triangles must be a list or tuple")
        report["checks"]["triangles_well_formed"] = False
        return None
    report["checks"]["triangle_sequence_valid"] = True
    report["counts"]["triangle_count"] = len(raw_triangles)
    triangles: list[_Triangle] = []
    seen: set[tuple[int, int, int]] = set()
    for index, raw_triangle in enumerate(raw_triangles):
        if not isinstance(raw_triangle, (list, tuple)) or len(raw_triangle) != 3:
            _issue(report, "triangles_well_formed", f"triangle {index} must contain exactly three indices")
            return None
        if any(isinstance(vertex, bool) or not isinstance(vertex, int) for vertex in raw_triangle):
            _issue(report, "triangles_well_formed", f"triangle {index} indices must be integers")
            return None
        triangle = tuple(raw_triangle)
        if any(vertex < 0 or vertex >= point_count for vertex in triangle):
            _issue(report, "triangles_well_formed", f"triangle {index} contains an out-of-range index")
            return None
        if len(set(triangle)) != 3:
            _issue(report, "triangles_well_formed", f"triangle {index} repeats a vertex")
            return None
        canonical = tuple(sorted(triangle))
        if canonical in seen:
            _issue(report, "triangles_well_formed", f"triangle {index} duplicates an earlier face")
            return None
        seen.add(canonical)
        triangles.append(triangle)
    report["checks"]["triangles_well_formed"] = True
    return triangles


def _segments_intersect(a: _Point, b: _Point, c: _Point, d: _Point) -> bool:
    o1 = _orientation(a, b, c)
    o2 = _orientation(a, b, d)
    o3 = _orientation(c, d, a)
    o4 = _orientation(c, d, b)
    if o1 == 0 and _on_segment(a, b, c):
        return True
    if o2 == 0 and _on_segment(a, b, d):
        return True
    if o3 == 0 and _on_segment(c, d, a):
        return True
    if o4 == 0 and _on_segment(c, d, b):
        return True
    return o1 * o2 < 0 and o3 * o4 < 0


def _edges_improperly_intersect(edge_a: _Edge, edge_b: _Edge, points: Sequence[_Point]) -> bool:
    shared = set(edge_a).intersection(edge_b)
    if len(shared) == 2:
        return False
    a, b = points[edge_a[0]], points[edge_a[1]]
    c, d = points[edge_b[0]], points[edge_b[1]]
    if not shared:
        return _segments_intersect(a, b, c, d)
    common = next(iter(shared))
    other_a = edge_a[0] if edge_a[1] == common else edge_a[1]
    other_b = edge_b[0] if edge_b[1] == common else edge_b[1]
    origin = points[common]
    pa, pb = points[other_a], points[other_b]
    if _orientation(origin, pa, pb) != 0:
        return False
    dot = (pa[0] - origin[0]) * (pb[0] - origin[0]) + (pa[1] - origin[1]) * (pb[1] - origin[1])
    return dot > 0


def _point_strictly_inside(point: _Point, triangle: _Triangle, points: Sequence[_Point]) -> bool:
    a, b, c = (points[index] for index in triangle)
    return _orientation(a, b, point) > 0 and _orientation(b, c, point) > 0 and _orientation(c, a, point) > 0


def _triangle_edges(triangle: _Triangle) -> tuple[_Edge, _Edge, _Edge]:
    a, b, c = triangle
    return tuple(tuple(sorted(edge)) for edge in ((a, b), (b, c), (c, a)))  # type: ignore[return-value]


def _triangles_improperly_intersect(
    first: _Triangle,
    second: _Triangle,
    points: Sequence[_Point],
) -> bool:
    shared_vertices = set(first).intersection(second)
    if len(shared_vertices) == 3:
        return True
    if len(shared_vertices) == 2:
        shared_edge = tuple(sorted(shared_vertices))
        first_third = next(vertex for vertex in first if vertex not in shared_vertices)
        second_third = next(vertex for vertex in second if vertex not in shared_vertices)
        side_a = _orientation(points[shared_edge[0]], points[shared_edge[1]], points[first_third])
        side_b = _orientation(points[shared_edge[0]], points[shared_edge[1]], points[second_third])
        return side_a == 0 or side_b == 0 or (side_a > 0) == (side_b > 0)

    if any(_point_strictly_inside(points[index], second, points) for index in first if index not in shared_vertices):
        return True
    if any(_point_strictly_inside(points[index], first, points) for index in second if index not in shared_vertices):
        return True
    return any(
        _edges_improperly_intersect(edge_a, edge_b, points)
        for edge_a in _triangle_edges(first)
        for edge_b in _triangle_edges(second)
    )


def _fraction_text(value: Fraction) -> str:
    return f"{value.numerator}/{value.denominator}"


def audit_triangulation(points: Any, triangles: Any) -> dict[str, Any]:
    """Audit whether indexed triangles form a planar triangulation of point hull.

    Predicates use exact rational arithmetic on the supplied numeric values:
    integers, fractions, and JSON decimals are exact; Python floats are treated
    as their exact binary floating-point values. This checks a supplied mesh
    only and does not generate or perturb a triangulation.
    """
    report = _new_report()
    parsed_points = _parse_points(points, report)
    if parsed_points is None:
        return report

    point_positions: dict[_Point, list[int]] = defaultdict(list)
    for index, point in enumerate(parsed_points):
        point_positions[point].append(index)
    duplicates = [indices for indices in point_positions.values() if len(indices) > 1]
    report["checks"]["coordinates_unique"] = not duplicates
    if duplicates:
        _issue(report, "coordinates_unique", f"duplicate coordinate indices: {duplicates}")
        return report

    triangles_parsed = _parse_triangles(triangles, len(parsed_points), report)
    if triangles_parsed is None:
        return report

    hull = _strict_hull(parsed_points)
    hull_area_twice = abs(_shoelace_twice([parsed_points[index] for index in hull])) if len(hull) >= 3 else Fraction(0)
    nondegenerate_hull = len(hull) >= 3 and hull_area_twice > 0
    report["checks"]["nondegenerate_convex_hull"] = nondegenerate_hull
    if not nondegenerate_hull:
        _issue(report, "nondegenerate_convex_hull", "at least three non-collinear unique points are required")
    boundary_indices, expected_boundary_edges = _hull_boundary(parsed_points, hull) if nondegenerate_hull else ([], [])
    report["hull"]["extreme_point_indices"] = hull
    report["hull"]["boundary_point_indices"] = boundary_indices
    report["hull"]["expected_boundary_edges"] = [list(edge) for edge in expected_boundary_edges]
    report["counts"]["extreme_hull_vertex_count"] = len(hull)
    report["counts"]["hull_boundary_vertex_count"] = len(boundary_indices)
    report["metrics"]["convex_hull_area_twice_exact"] = _fraction_text(hull_area_twice)

    used_indices = {vertex for triangle in triangles_parsed for vertex in triangle}
    report["uncovered_point_indices"] = [i for i in range(len(parsed_points)) if i not in used_indices]
    report["checks"]["all_input_points_covered"] = not report["uncovered_point_indices"] and bool(triangles_parsed)
    if report["uncovered_point_indices"] or not triangles_parsed:
        _issue(report, "all_input_points_covered", f"uncovered indices: {report['uncovered_point_indices']}")

    signed_areas = [
        _orientation(*(parsed_points[index] for index in triangle))
        for triangle in triangles_parsed
    ]
    nonzero_areas = all(area != 0 for area in signed_areas) and bool(signed_areas)
    report["checks"]["nonzero_triangle_areas"] = nonzero_areas
    if not nonzero_areas:
        _issue(report, "nonzero_triangle_areas", "at least one face is degenerate or no faces were supplied")
    orientation_signs = {1 if area > 0 else -1 for area in signed_areas if area != 0}
    consistent_orientation = nonzero_areas and len(orientation_signs) == 1
    report["checks"]["consistent_triangle_orientation"] = consistent_orientation
    if not consistent_orientation:
        _issue(report, "consistent_triangle_orientation", "all nondegenerate faces must use one winding direction")

    normalized: list[_Triangle] = []
    for triangle, area in zip(triangles_parsed, signed_areas):
        normalized.append(triangle if area >= 0 else (triangle[0], triangle[2], triangle[1]))
    edge_faces: dict[_Edge, list[int]] = defaultdict(list)
    triangle_area_twice = Fraction(0)
    for face_index, (triangle, area) in enumerate(zip(normalized, signed_areas)):
        triangle_area_twice += abs(area)
        for edge in _triangle_edges(triangle):
            edge_faces[edge].append(face_index)

    edge_count = len(edge_faces)
    report["counts"]["edge_count"] = edge_count
    incidence_valid = all(len(incident) in (1, 2) for incident in edge_faces.values()) and bool(edge_faces)
    report["checks"]["edge_incidence_valid"] = incidence_valid
    if not incidence_valid:
        bad = {edge: len(incident) for edge, incident in edge_faces.items() if len(incident) not in (1, 2)}
        _issue(report, "edge_incidence_valid", f"edge incidences outside {{1, 2}}: {bad}")

    observed_boundary_edges = sorted(edge for edge, incident in edge_faces.items() if len(incident) == 1)
    report["hull"]["observed_boundary_edges"] = [list(edge) for edge in observed_boundary_edges]
    boundary_matches = nondegenerate_hull and observed_boundary_edges == expected_boundary_edges
    report["checks"]["boundary_matches_independent_hull"] = boundary_matches
    if not boundary_matches:
        _issue(report, "boundary_matches_independent_hull", "one-face edges do not equal the independently computed hull chain")

    adjacency: list[set[int]] = [set() for _ in normalized]
    for incident in edge_faces.values():
        if len(incident) == 2:
            first, second = incident
            adjacency[first].add(second)
            adjacency[second].add(first)
    if normalized:
        visited = {0}
        queue = deque([0])
        while queue:
            current = queue.popleft()
            for neighbor in adjacency[current] - visited:
                visited.add(neighbor)
                queue.append(neighbor)
        connected = len(visited) == len(normalized)
    else:
        connected = False
    report["checks"]["edge_connected"] = connected
    if not connected:
        _issue(report, "edge_connected", "triangle adjacency through shared edges is disconnected")

    edge_crossings: list[dict[str, list[int]]] = []
    unique_edges = sorted(edge_faces)
    for first_index, edge_a in enumerate(unique_edges):
        for edge_b in unique_edges[first_index + 1:]:
            if _edges_improperly_intersect(edge_a, edge_b, parsed_points):
                edge_crossings.append({"edge_a": list(edge_a), "edge_b": list(edge_b)})
    report["edge_crossings"] = edge_crossings
    report["checks"]["noncrossing_edges"] = not edge_crossings
    if edge_crossings:
        _issue(report, "noncrossing_edges", f"{len(edge_crossings)} non-shared edge intersection(s) found")

    triangle_intersections: list[list[int]] = []
    for first_index, second_index in combinations(range(len(normalized)), 2):
        if _triangles_improperly_intersect(normalized[first_index], normalized[second_index], parsed_points):
            triangle_intersections.append([first_index, second_index])
    report["triangle_intersections"] = triangle_intersections
    report["checks"]["nonoverlapping_triangles"] = not triangle_intersections
    if triangle_intersections:
        _issue(report, "nonoverlapping_triangles", f"intersecting face pairs: {triangle_intersections}")

    expected_edges = 3 * len(parsed_points) - 3 - len(boundary_indices) if nondegenerate_hull else None
    expected_triangles = 2 * len(parsed_points) - 2 - len(boundary_indices) if nondegenerate_hull else None
    report["metrics"]["expected_edge_count"] = expected_edges
    report["metrics"]["expected_triangle_count"] = expected_triangles
    euler_counts_match = (
        nondegenerate_hull
        and edge_count == expected_edges
        and len(normalized) == expected_triangles
    )
    report["checks"]["euler_counts_match"] = euler_counts_match
    if not euler_counts_match:
        _issue(report, "euler_counts_match", "observed face/edge counts do not match the triangulated-hull formulas")

    report["metrics"]["triangle_area_twice_exact"] = _fraction_text(triangle_area_twice)
    area_partition = nondegenerate_hull and triangle_area_twice == hull_area_twice
    report["checks"]["area_partition_identity"] = area_partition
    if not area_partition:
        _issue(report, "area_partition_identity", "sum of absolute face areas differs from convex-hull area")

    report["geometry_checks_all_satisfied"] = all(value is True for value in report["checks"].values())
    return report


def _input_error_report(message: str) -> dict[str, Any]:
    report = _new_report()
    report["issues"].append(f"input_json: {message}")
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Independently audit a supplied planar triangle mesh.")
    parser.add_argument("--input", required=True, type=Path, help="JSON with points:[[x,y],...] and triangles:[[i,j,k],...]")
    args = parser.parse_args(argv)
    try:
        with args.input.open("r", encoding="utf-8") as handle:
            payload = json.load(handle, parse_float=Decimal)
        if not isinstance(payload, dict):
            raise ValueError("root JSON value must be an object")
        report = audit_triangulation(payload.get("points"), payload.get("triangles"))
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        report = _input_error_report(str(exc))
        json.dump(report, sys.stdout, indent=2, sort_keys=True, allow_nan=False)
        sys.stdout.write("\n")
        return 2
    json.dump(report, sys.stdout, indent=2, sort_keys=True, allow_nan=False)
    sys.stdout.write("\n")
    return 0 if report["geometry_checks_all_satisfied"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
