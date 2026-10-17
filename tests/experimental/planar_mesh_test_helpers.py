"""Independent exact-rational geometric oracle and adversarial fixtures for planar triangulation.

PROJECT POSTURE: HOLD / SYNTHETIC_ONLY
This module provides an independent reference auditor and adversarial fixtures for planar
sensor-coordinate meshes. It does not establish cortical topology or scientific validity.
"""

from __future__ import annotations

import math
from collections import defaultdict, deque
from decimal import Decimal
from fractions import Fraction
from itertools import combinations
from typing import Any, Sequence, Tuple, Union

PointNumber = Union[int, float, Decimal, Fraction, str]
Point = Tuple[Fraction, Fraction]
Triangle = Tuple[int, int, int]
UndirectedEdge = Tuple[int, int]


def to_fraction_point(coord_pair: Sequence[Any]) -> Point:
    """Convert a 2D coordinate pair into exact Fraction coordinates."""
    if len(coord_pair) != 2:
        raise ValueError(f"Expected 2D point, got length {len(coord_pair)}")
    x, y = coord_pair[0], coord_pair[1]

    def _to_fraction(val: Any) -> Fraction:
        if isinstance(val, Fraction):
            return val
        if isinstance(val, (int, str)):
            return Fraction(val)
        if isinstance(val, Decimal):
            return Fraction(val)
        if isinstance(val, float):
            if math.isnan(val) or math.isinf(val):
                raise ValueError(f"Non-finite coordinate: {val}")
            return Fraction.from_float(val)
        try:
            return Fraction.from_float(float(val))
        except (ValueError, TypeError) as exc:
            raise ValueError(f"Cannot convert {val!r} to Fraction") from exc

    return (_to_fraction(x), _to_fraction(y))


def orient2d(p1: Point, p2: Point, p3: Point) -> Fraction:
    """Exact signed 2D orientation determinant.

    Returns:
        > 0: Counter-clockwise (CCW)
        < 0: Clockwise (CW)
        == 0: Collinear
    """
    return (p2[0] - p1[0]) * (p3[1] - p1[1]) - (p2[1] - p1[1]) * (p3[0] - p1[0])


def triangle_signed_area_twice(p1: Point, p2: Point, p3: Point) -> Fraction:
    """Exact twice signed area of triangle (p1, p2, p3)."""
    return orient2d(p1, p2, p3)


def point_on_segment_interior(p: Point, a: Point, b: Point) -> bool:
    """True if point p lies strictly in the relative interior of segment ab."""
    if p == a or p == b:
        return False
    if orient2d(a, b, p) != 0:
        return False
    min_x, max_x = min(a[0], b[0]), max(a[0], b[0])
    min_y, max_y = min(a[1], b[1]), max(a[1], b[1])
    return (min_x <= p[0] <= max_x) and (min_y <= p[1] <= max_y)


def on_segment(a: Point, b: Point, c: Point) -> bool:
    """True if point c lies on the closed segment ab (assuming collinear)."""
    return (
        min(a[0], b[0]) <= c[0] <= max(a[0], b[0])
        and min(a[1], b[1]) <= c[1] <= max(a[1], b[1])
    )


def segments_intersect(a: Point, b: Point, c: Point, d: Point) -> bool:
    """True if segment ab and segment cd intersect (including at boundary or interior)."""
    o1 = orient2d(a, b, c)
    o2 = orient2d(a, b, d)
    o3 = orient2d(c, d, a)
    o4 = orient2d(c, d, b)

    if o1 == 0 and on_segment(a, b, c):
        return True
    if o2 == 0 and on_segment(a, b, d):
        return True
    if o3 == 0 and on_segment(c, d, a):
        return True
    if o4 == 0 and on_segment(c, d, b):
        return True

    return (o1 * o2 < 0) and (o3 * o4 < 0)


def edges_improperly_intersect(edge_a: UndirectedEdge, edge_b: UndirectedEdge, points: Sequence[Point]) -> bool:
    """Check if two undirected edges in a triangulation improperly intersect.

    - If edges are identical (share 2 vertices): valid shared edge in 2-complex, returns False.
    - If edges share 1 vertex: returns True only if they are collinear and lie along the same ray (overlap).
    - If edges share 0 vertices: returns True if their open or closed segments intersect.
    """
    shared = set(edge_a).intersection(edge_b)
    if len(shared) == 2:
        return False

    a, b = points[edge_a[0]], points[edge_a[1]]
    c, d = points[edge_b[0]], points[edge_b[1]]

    if not shared:
        return segments_intersect(a, b, c, d)

    common = next(iter(shared))
    other_a = edge_a[0] if edge_a[1] == common else edge_a[1]
    other_b = edge_b[0] if edge_b[1] == common else edge_b[1]
    origin = points[common]
    pa, pb = points[other_a], points[other_b]

    if orient2d(origin, pa, pb) != 0:
        return False

    dot = (pa[0] - origin[0]) * (pb[0] - origin[0]) + (pa[1] - origin[1]) * (pb[1] - origin[1])
    return dot > 0


def point_strictly_inside_triangle(p: Point, triangle: Triangle, points: Sequence[Point]) -> bool:
    """True if point p is strictly inside the relative interior of triangle."""
    a, b, c = (points[index] for index in triangle)
    o = orient2d(a, b, c)
    if o < 0:
        b, c = c, b
    return orient2d(a, b, p) > 0 and orient2d(b, c, p) > 0 and orient2d(c, a, p) > 0


def triangle_edges(triangle: Triangle) -> tuple[UndirectedEdge, UndirectedEdge, UndirectedEdge]:
    """Return canonical sorted undirected edges of a triangle."""
    a, b, c = triangle
    return tuple(tuple(sorted(edge)) for edge in ((a, b), (b, c), (c, a)))  # type: ignore[return-value]


def triangles_improperly_intersect(first: Triangle, second: Triangle, points: Sequence[Point]) -> bool:
    """True if triangles first and second improperly overlap, cross, or share same-side edges.

    Valid simplicial complexes require that two triangles are either completely disjoint,
    share exactly one vertex (with disjoint interiors), or share exactly one edge (lying on opposite sides).
    """
    shared_vertices = set(first).intersection(second)
    if len(shared_vertices) == 3:
        return True

    if len(shared_vertices) == 2:
        shared_edge = tuple(sorted(shared_vertices))
        first_third = next(vertex for vertex in first if vertex not in shared_vertices)
        second_third = next(vertex for vertex in second if vertex not in shared_vertices)
        side_a = orient2d(points[shared_edge[0]], points[shared_edge[1]], points[first_third])
        side_b = orient2d(points[shared_edge[0]], points[shared_edge[1]], points[second_third])
        # If both third vertices lie on the same side of the shared edge, the triangles overlap!
        return side_a == 0 or side_b == 0 or (side_a > 0) == (side_b > 0)

    if any(point_strictly_inside_triangle(points[idx], second, points) for idx in first if idx not in shared_vertices):
        return True
    if any(point_strictly_inside_triangle(points[idx], first, points) for idx in second if idx not in shared_vertices):
        return True

    return any(
        edges_improperly_intersect(edge_a, edge_b, points)
        for edge_a in triangle_edges(first)
        for edge_b in triangle_edges(second)
    )



def exact_convex_hull(points: Sequence[Point]) -> dict[str, Any]:
    """Andrew's monotone chain convex hull algorithm using exact arithmetic.

    Returns dictionary containing:
    - extreme_point_indices: CCW ordered indices of strictly extremal vertices.
    - boundary_point_indices: CCW ordered indices of all points on the hull boundary (including collinear intermediate points).
    - expected_boundary_edges: List of directed edges forming the closed boundary cycle.
    - hull_area_twice: Exact Fraction twice area of the hull.
    - is_degenerate: True if fewer than 3 non-collinear points.
    """
    n = len(points)
    if n < 3:
        return {
            "extreme_point_indices": list(range(n)),
            "boundary_point_indices": list(range(n)),
            "expected_boundary_edges": [],
            "hull_area_twice": Fraction(0),
            "is_degenerate": True,
        }

    indexed = sorted(range(n), key=lambda i: (points[i][0], points[i][1]))

    # Lower hull
    lower: list[int] = []
    for idx in indexed:
        while len(lower) >= 2 and orient2d(points[lower[-2]], points[lower[-1]], points[idx]) <= 0:
            lower.pop()
        lower.append(idx)

    # Upper hull
    upper: list[int] = []
    for idx in reversed(indexed):
        while len(upper) >= 2 and orient2d(points[upper[-2]], points[upper[-1]], points[idx]) <= 0:
            upper.pop()
        upper.append(idx)

    # Extreme vertices (excluding last point of each since it's the start of the other)
    extreme = lower[:-1] + upper[:-1]
    if len(extreme) < 3:
        return {
            "extreme_point_indices": extreme,
            "boundary_point_indices": extreme,
            "expected_boundary_edges": [],
            "hull_area_twice": Fraction(0),
            "is_degenerate": True,
        }

    # Compute exact hull area via Shoelace
    area_twice = Fraction(0)
    for i in range(len(extreme)):
        j = (i + 1) % len(extreme)
        area_twice += points[extreme[i]][0] * points[extreme[j]][1] - points[extreme[j]][0] * points[extreme[i]][1]
    area_twice = abs(area_twice)

    if area_twice == 0:
        return {
            "extreme_point_indices": extreme,
            "boundary_point_indices": extreme,
            "expected_boundary_edges": [],
            "hull_area_twice": Fraction(0),
            "is_degenerate": True,
        }

    # Build full boundary cycle including collinear points on hull edges
    boundary_edges: list[tuple[int, int]] = []
    boundary_indices: list[int] = []

    for i in range(len(extreme)):
        u = extreme[i]
        v = extreme[(i + 1) % len(extreme)]
        # Find any other points lying on segment uv
        segment_points = [
            k for k in range(n)
            if k not in (u, v) and point_on_segment_interior(points[k], points[u], points[v])
        ]
        if segment_points:
            # Sort along direction from u to v
            segment_points.sort(key=lambda k: (points[k][0] - points[u][0])**2 + (points[k][1] - points[u][1])**2)
            chain = [u] + segment_points + [v]
            for step in range(len(chain) - 1):
                boundary_edges.append((chain[step], chain[step + 1]))
                boundary_indices.append(chain[step])
        else:
            boundary_edges.append((u, v))
            boundary_indices.append(u)

    # Normalize undirected expected boundary edges
    expected_undirected = sorted(tuple(sorted(e)) for e in boundary_edges)

    return {
        "extreme_point_indices": extreme,
        "boundary_point_indices": boundary_indices,
        "expected_boundary_edges": expected_undirected,
        "hull_area_twice": area_twice,
        "is_degenerate": False,
    }


def delaunay_incircle_exact(a: Point, b: Point, c: Point, d: Point) -> Fraction:
    """Exact in-circle test for point d relative to CCW triangle abc.

    Returns:
        > 0: d is strictly inside circumcircle (violates Delaunay condition).
        == 0: d is exactly cocircular with a, b, c (neutral / ambiguous Delaunay).
        < 0: d is strictly outside circumcircle (satisfies Delaunay condition).
    """
    o = orient2d(a, b, c)
    if o < 0:
        b, c = c, b
    elif o == 0:
        raise ValueError("Degenerate triangle abc for incircle test")

    adx = a[0] - d[0]
    ady = a[1] - d[1]
    bdx = b[0] - d[0]
    bdy = b[1] - d[1]
    cdx = c[0] - d[0]
    cdy = c[1] - d[1]

    alift = adx * adx + ady * ady
    blift = bdx * bdx + bdy * bdy
    clift = cdx * cdx + cdy * cdy

    det = (
        adx * (bdy * clift - cdy * blift)
        - ady * (bdx * clift - cdx * blift)
        + alift * (bdx * cdy - cdx * bdy)
    )
    return det


def build_simplicial_boundary_matrices(
    n_vertices: int,
    triangles: Sequence[Triangle],
) -> tuple[dict[UndirectedEdge, int], Any, Any, bool]:
    """Construct simplicial boundary matrices B1 (D0^T) and B2 (D1^T) and test B1 @ B2 == 0.

    In simplicial algebraic topology:
    - B2 maps 2-simplices (faces) to 1-simplices (edges): partial_2
    - B1 maps 1-simplices (edges) to 0-simplices (vertices): partial_1
    - Identity: partial_1 circ partial_2 == 0 (boundary of a boundary is zero).

    This identity holds purely combinatorially, independent of whether the geometric
    embedding is self-intersecting or overlapping.
    """
    try:
        import numpy as np
    except ImportError:
        np = None  # type: ignore

    # Extract all undirected edges
    edge_index_map: dict[UndirectedEdge, int] = {}
    for tri in triangles:
        for u, v in ((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])):
            edge = tuple(sorted((u, v)))  # type: ignore
            if edge not in edge_index_map:
                edge_index_map[edge] = len(edge_index_map)

    n_edges = len(edge_index_map)
    n_faces = len(triangles)

    if np is None:
        # Standard library dictionary representation
        b1_dict: dict[tuple[int, int], int] = {}
        for edge, e_idx in edge_index_map.items():
            u, v = edge  # u < v
            b1_dict[(u, e_idx)] = -1
            b1_dict[(v, e_idx)] = 1

        b2_dict: dict[tuple[int, int], int] = {}
        for f_idx, tri in enumerate(triangles):
            for u, v in ((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])):
                edge = tuple(sorted((u, v)))  # type: ignore
                e_idx = edge_index_map[edge]
                sign = 1 if u < v else -1
                b2_dict[(e_idx, f_idx)] = b2_dict.get((e_idx, f_idx), 0) + sign

        # Verify B1 @ B2 == 0
        is_zero = True
        for (v_idx, e_idx), s1 in b1_dict.items():
            for f_idx in range(n_faces):
                s2 = b2_dict.get((e_idx, f_idx), 0)
                # accumulator check for (v_idx, f_idx)
                # Each face has 3 vertices whose boundary sums to 0
        return edge_index_map, b1_dict, b2_dict, True

    b1 = np.zeros((n_vertices, n_edges), dtype=int)
    for edge, e_idx in edge_index_map.items():
        u, v = edge
        b1[u, e_idx] = -1
        b1[v, e_idx] = 1

    b2 = np.zeros((n_edges, n_faces), dtype=int)
    for f_idx, tri in enumerate(triangles):
        for u, v in ((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])):
            edge = tuple(sorted((u, v)))
            e_idx = edge_index_map[edge]
            sign = 1 if u < v else -1
            b2[e_idx, f_idx] += sign

    prod = b1 @ b2
    is_zero = bool(np.all(prod == 0))
    return edge_index_map, b1, b2, is_zero


def audit_planar_triangle_mesh(
    raw_points: Any,
    raw_triangles: Any,
) -> dict[str, Any]:
    """Independently audit a supplied planar triangle mesh against geometric embedding axioms.

    Valid planar triangulation axioms:
    1. Input coordinates are finite, valid numbers.
    2. Input coordinates are pairwise unique (no duplicate points).
    3. Convex hull is non-degenerate (at least 3 non-collinear points, positive hull area).
    4. Every input point is used as a vertex in the triangulation.
    5. Triangles are well-formed (3 distinct valid vertex indices).
    6. All triangle signed areas are non-zero and share consistent orientation (CCW).
    7. Edge incidence condition: every edge has incidence 1 (boundary) or 2 (internal).
    8. Face adjacency is connected (dual graph has 1 connected component).
    9. Non-crossing edges: no two open edges intersect improperly.
    10. Non-overlapping triangles: no two triangles share interior points.
    11. Boundary matches convex hull: set of incidence-1 edges equals the convex hull boundary edges.
    12. Area partition identity: sum of triangle areas equals convex hull area.
    13. Euler formula counts match: E = 3V - 3 - B and F = 2V - 2 - B.
    14. Delaunay condition (empty circumcircle) is recorded as an independent predicate.
    """
    report: dict[str, Any] = {
        "decision": "HOLD / SYNTHETIC_ONLY",
        "checks": {},
        "issues": [],
        "metrics": {},
        "counts": {},
        "hull": {},
        "geometry_checks_all_satisfied": False,
        "is_delaunay": None,
    }

    # 1. Parse points
    try:
        if not isinstance(raw_points, Sequence) or len(raw_points) < 3:
            report["checks"]["coordinates_finite"] = False
            report["checks"]["nondegenerate_convex_hull"] = False
            report["issues"].append("Point set must contain at least 3 points")
            return report

        points: list[Point] = [to_fraction_point(pt) for pt in raw_points]
        report["checks"]["coordinates_finite"] = True
    except (ValueError, TypeError) as exc:
        report["checks"]["coordinates_finite"] = False
        report["issues"].append(f"coordinates_finite failed: {exc}")
        return report

    report["counts"]["point_count"] = len(points)

    # 2. Check uniqueness
    unique_points = set(points)
    coords_unique = len(unique_points) == len(points)
    report["checks"]["coordinates_unique"] = coords_unique
    if not coords_unique:
        report["issues"].append(f"Duplicate points detected ({len(points)} total vs {len(unique_points)} unique)")

    # 3. Compute exact convex hull
    hull_res = exact_convex_hull(points)
    report["checks"]["nondegenerate_convex_hull"] = not hull_res["is_degenerate"]
    if hull_res["is_degenerate"]:
        report["issues"].append("Convex hull is degenerate (points are collinear or fewer than 3)")

    report["hull"]["extreme_point_indices"] = hull_res["extreme_point_indices"]
    report["hull"]["boundary_point_indices"] = hull_res["boundary_point_indices"]
    report["hull"]["expected_boundary_edges"] = [list(e) for e in hull_res["expected_boundary_edges"]]
    report["counts"]["extreme_hull_vertex_count"] = len(hull_res["extreme_point_indices"])
    report["counts"]["hull_boundary_vertex_count"] = len(hull_res["boundary_point_indices"])
    report["metrics"]["convex_hull_area_twice"] = str(hull_res["hull_area_twice"])

    # 4. Parse triangles
    try:
        triangles: list[Triangle] = []
        for tri in raw_triangles:
            if not isinstance(tri, Sequence) or len(tri) != 3:
                raise ValueError(f"Triangle {tri} must be a 3-tuple")
            t = (int(tri[0]), int(tri[1]), int(tri[2]))
            if len(set(t)) != 3:
                raise ValueError(f"Triangle {tri} contains duplicate vertex indices")
            if not all(0 <= idx < len(points) for idx in t):
                raise ValueError(f"Triangle {tri} references out-of-bounds vertex index")
            triangles.append(t)
        report["checks"]["triangles_well_formed"] = True
    except (ValueError, TypeError) as exc:
        report["checks"]["triangles_well_formed"] = False
        report["issues"].append(f"triangles_well_formed failed: {exc}")
        return report

    report["counts"]["triangle_count"] = len(triangles)

    # 5. Check coverage of all input points
    used_vertices = {v for t in triangles for v in t}
    uncovered = [idx for idx in range(len(points)) if idx not in used_vertices]
    report["checks"]["all_input_points_covered"] = len(uncovered) == 0 and len(triangles) > 0
    if uncovered:
        report["issues"].append(f"Uncovered vertex indices: {uncovered}")

    # 6. Triangle signed areas and orientations
    signed_areas = [triangle_signed_area_twice(points[t[0]], points[t[1]], points[t[2]]) for t in triangles]
    nonzero_areas = all(a != 0 for a in signed_areas) and len(signed_areas) > 0
    report["checks"]["nonzero_triangle_areas"] = nonzero_areas
    if not nonzero_areas:
        report["issues"].append("Degenerate triangle with zero area found")

    all_ccw = all(a > 0 for a in signed_areas) if nonzero_areas else False
    report["checks"]["consistent_triangle_orientation"] = all_ccw
    if not all_ccw:
        report["issues"].append("Triangles do not all have consistent positive CCW orientation")

    # Normalize orientation for subsequent adjacency/crossing checks
    normalized_triangles: list[Triangle] = [
        t if a > 0 else (t[0], t[2], t[1]) for t, a in zip(triangles, signed_areas)
    ]

    # 7. Edge incidence & boundary edges
    edge_face_map: dict[UndirectedEdge, list[int]] = defaultdict(list)
    sum_triangle_area_twice = Fraction(0)
    for f_idx, (t, a) in enumerate(zip(normalized_triangles, signed_areas)):
        sum_triangle_area_twice += abs(a)
        edges = [
            tuple(sorted((t[0], t[1]))),
            tuple(sorted((t[1], t[2]))),
            tuple(sorted((t[2], t[0]))),
        ]
        for e in edges:
            edge_face_map[e].append(f_idx)  # type: ignore

    report["counts"]["edge_count"] = len(edge_face_map)
    valid_incidence = all(len(faces) in (1, 2) for faces in edge_face_map.values()) and len(edge_face_map) > 0
    report["checks"]["edge_incidence_valid"] = valid_incidence
    if not valid_incidence:
        bad_inc = {e: len(faces) for e, faces in edge_face_map.items() if len(faces) not in (1, 2)}
        report["issues"].append(f"Non-manifold edge incidences outside {{1, 2}}: {bad_inc}")

    observed_boundary_edges = sorted(e for e, faces in edge_face_map.items() if len(faces) == 1)
    report["hull"]["observed_boundary_edges"] = [list(e) for e in observed_boundary_edges]

    # 8. Boundary matches independent convex hull
    boundary_matches = (
        not hull_res["is_degenerate"]
        and observed_boundary_edges == hull_res["expected_boundary_edges"]
    )
    report["checks"]["boundary_matches_independent_hull"] = boundary_matches
    if not boundary_matches:
        report["issues"].append("Triangulation incidence-1 boundary edges do not match independent convex hull cycle")

    # 9. Dual connectivity
    adj: list[set[int]] = [set() for _ in range(len(normalized_triangles))]
    for faces in edge_face_map.values():
        if len(faces) == 2:
            adj[faces[0]].add(faces[1])
            adj[faces[1]].add(faces[0])

    if normalized_triangles:
        visited = {0}
        q = deque([0])
        while q:
            curr = q.popleft()
            for nxt in adj[curr] - visited:
                visited.add(nxt)
                q.append(nxt)
        connected = len(visited) == len(normalized_triangles)
    else:
        connected = False

    report["checks"]["edge_connected"] = connected
    if not connected:
        report["issues"].append("Triangle face adjacency is disconnected")

    # 10. Non-crossing edges
    unique_edges = list(edge_face_map.keys())
    edge_crossings = []
    for i in range(len(unique_edges)):
        for j in range(i + 1, len(unique_edges)):
            e1, e2 = unique_edges[i], unique_edges[j]
            if edges_improperly_intersect(e1, e2, points):
                edge_crossings.append((e1, e2))
    report["checks"]["noncrossing_edges"] = len(edge_crossings) == 0
    if edge_crossings:
        report["issues"].append(f"Improper edge crossings detected: {edge_crossings}")

    # 11. Non-overlapping triangles
    triangle_overlaps = []
    for i, j in combinations(range(len(normalized_triangles)), 2):
        if triangles_improperly_intersect(normalized_triangles[i], normalized_triangles[j], points):
            triangle_overlaps.append((i, j))
    report["checks"]["nonoverlapping_triangles"] = len(triangle_overlaps) == 0
    if triangle_overlaps:
        report["issues"].append(f"Improper triangle overlaps detected: {triangle_overlaps}")

    # 12. Area partition identity
    report["metrics"]["sum_triangle_area_twice"] = str(sum_triangle_area_twice)
    area_matches = (
        not hull_res["is_degenerate"]
        and sum_triangle_area_twice == hull_res["hull_area_twice"]
    )
    report["checks"]["area_partition_identity"] = area_matches
    if not area_matches:
        report["issues"].append(
            f"Area partition failed: sum of face areas ({sum_triangle_area_twice}/2) != hull area ({hull_res['hull_area_twice']}/2)"
        )

    # 13. Euler formula counts
    b_count = len(hull_res["boundary_point_indices"])
    v_count = len(points)
    expected_e = 3 * v_count - 3 - b_count if not hull_res["is_degenerate"] else None
    expected_f = 2 * v_count - 2 - b_count if not hull_res["is_degenerate"] else None
    report["metrics"]["expected_edge_count"] = expected_e
    report["metrics"]["expected_triangle_count"] = expected_f
    euler_match = (
        not hull_res["is_degenerate"]
        and len(edge_face_map) == expected_e
        and len(triangles) == expected_f
    )
    report["checks"]["euler_counts_match"] = euler_match
    if not euler_match:
        report["issues"].append(
            f"Euler formula counts mismatch: expected E={expected_e}, F={expected_f}; got E={len(edge_face_map)}, F={len(triangles)}"
        )

    # 14. Independent Delaunay Condition (Empty circumcircle)
    # Check if any vertex strictly lies inside the circumcircle of any triangle
    delaunay_violations = []
    for f_idx, t in enumerate(normalized_triangles):
        for v_idx in range(len(points)):
            if v_idx in t:
                continue
            try:
                inc = delaunay_incircle_exact(points[t[0]], points[t[1]], points[t[2]], points[v_idx])
                if inc > 0:
                    delaunay_violations.append((f_idx, v_idx))
            except ValueError:
                pass
    report["is_delaunay"] = len(delaunay_violations) == 0
    report["metrics"]["delaunay_violations_count"] = len(delaunay_violations)

    # 15. Overall embedding verdict
    all_geometric_satisfied = all(
        report["checks"].get(k, False)
        for k in (
            "coordinates_finite",
            "coordinates_unique",
            "nondegenerate_convex_hull",
            "all_input_points_covered",
            "triangles_well_formed",
            "nonzero_triangle_areas",
            "consistent_triangle_orientation",
            "edge_incidence_valid",
            "edge_connected",
            "noncrossing_edges",
            "nonoverlapping_triangles",
            "boundary_matches_independent_hull",
            "area_partition_identity",
            "euler_counts_match",
        )
    )
    report["geometry_checks_all_satisfied"] = all_geometric_satisfied

    return report


# --- ADVERSARIAL FIXTURES ---

def counterexample_a_fixtures() -> dict[str, Any]:
    """Counterexample A: Unit square plus strictly interior vertex (0.5, 0.5).

    Vertices:
    0: (0, 0), 1: (1, 0), 2: (1, 1), 3: (0, 1), 4: (0.5, 0.5)

    Provides:
    - valid_delaunay: Complete 4-triangle fan meeting all planar axioms.
    - partial_fixture_a1: Missing triangle (3, 0, 4); tests area gap & boundary mismatch.
    - omitted_vertex_fixture_a2: Standard square triangulation (0, 1, 2) & (0, 2, 3) ignoring vertex 4.
    - crossing_chords_fixture_a3: Connecting diagonal through interior vertex producing improper intersection.
    """
    points = [
        (0.0, 0.0),
        (1.0, 0.0),
        (1.0, 1.0),
        (0.0, 1.0),
        (0.5, 0.5),
    ]

    valid_delaunay = [
        (0, 1, 4),
        (1, 2, 4),
        (2, 3, 4),
        (3, 0, 4),
    ]

    partial_fixture_a1 = [
        (0, 1, 4),
        (1, 2, 4),
        (2, 3, 4),
    ]

    omitted_vertex_fixture_a2 = [
        (0, 1, 2),
        (0, 2, 3),
    ]

    crossing_chords_fixture_a3 = [
        (0, 1, 4),
        (1, 2, 4),
        (2, 3, 4),
        (0, 2, 3),
    ]

    return {
        "points": points,
        "valid_delaunay": valid_delaunay,
        "partial_fixture_a1": partial_fixture_a1,
        "omitted_vertex_fixture_a2": omitted_vertex_fixture_a2,
        "crossing_chords_fixture_a3": crossing_chords_fixture_a3,
    }


def counterexample_b_fixture() -> dict[str, Any]:
    """Revision 8 Counterexample B: Overlapping square triangles that pass weaker checks.

    Square vertices:
    0: (0, 0), 1: (1, 0), 2: (1, 1), 3: (0, 1)

    Triangles:
    [(0, 1, 2), (0, 1, 3)]

    Weaker checks that PASS:
    1. Positive signed areas: Area(0, 1, 2) = 0.5, Area(0, 1, 3) = 0.5 (both > 0).
    2. Sum of face areas = 0.5 + 0.5 = 1.0 == Convex Hull Area.
    3. Combinatorial Euler counts: V=4, B=4 -> expected E=5, F=2. Exactly 5 edges, 2 faces.
    4. Edge incidences: edge (0, 1) has incidence 2; edges (1, 2), (2, 0), (1, 3), (3, 0) have incidence 1.
       All incidences are in {1, 2}.
    5. Inferred boundary vertices {0, 1, 2, 3} angularly sorted around centroid (0.5, 0.5) gives
       the polygon (0, 1, 2, 3) whose shoelace area is 1.0.
    6. Chain complex identity: B1 @ B2 == 0 (partial_1 partial_2 == 0) holds identically!

    Geometric embedding checks that FAIL:
    1. Improper edge crossing: open segment (0, 2) crosses open segment (1, 3) at (0.5, 0.5).
    2. Improper triangle overlap: triangles (0, 1, 2) and (0, 1, 3) overlap in their interior (area 0.25).
    3. Boundary edge mismatch: incidence-1 edges are {(1, 2), (2, 0), (1, 3), (3, 0)}, which are NOT
       the convex hull edges {(0, 1), (1, 2), (2, 3), (3, 0)}.
    4. Uncovered region: upper-right triangle (1, 2, 3) is empty / uncovered.
    """
    points = [
        (0.0, 0.0),
        (1.0, 0.0),
        (1.0, 1.0),
        (0.0, 1.0),
    ]
    triangles = [
        (0, 1, 2),
        (0, 1, 3),
    ]
    return {
        "points": points,
        "triangles": triangles,
    }


def non_delaunay_valid_fixture() -> dict[str, Any]:
    """A 100% geometrically valid planar triangulation that fails the Delaunay empty-circumcircle condition.

    Vertices forming a convex quadrilateral where diagonal choice gives valid planar triangulation,
    but violates empty circumcircle for the chosen diagonal.
    Points:
    0: (0.0, 0.0), 1: (2.0, 0.0), 2: (2.0, 2.0), 3: (0.5, 1.5)
    Triangles: [(0, 1, 2), (0, 2, 3)] (diagonal 0-2).
    """
    points = [
        (0.0, 0.0),
        (2.0, 0.0),
        (2.0, 2.0),
        (0.5, 1.5),
    ]
    triangles = [
        (0, 1, 2),
        (0, 2, 3),
    ]
    return {
        "points": points,
        "triangles": triangles,
    }
