"""Robust 2D planar triangulation construction and validation.

Project posture: HOLD / SYNTHETIC_ONLY.
Successful discrete geometry checks do **not** establish cortical topology,
biological vortices, or empirical validity. ``scientific_pass`` is always False.

Predicate / precision policy
----------------------------
Binary floating-point coordinates are interpreted as their **IEEE-754 binary
values as represented** via ``fractions.Fraction.from_float``. Orientation and
incircle *signs* are then evaluated with rational arithmetic on those
represented values (a represented-input exact-sign policy). This is **not**
Shewchuk's adaptive floating-point expansion kernel (not copied), **not** a
claim of exactness with respect to ideal reals before rounding, and **not** a
fixed geometric epsilon tolerance dressed up as exact arithmetic.

Fixed geometric epsilons are **not** used as orientation/incircle predicates.
Finite coordinate jitter is **not** Simulation of Simplicity and is never
treated as proof about the original (pre-jitter) geometry.

Three separate claim layers (never conflated)
---------------------------------------------
1. Abstract simplicial chain identity ``D1 @ D0 == 0``.
2. Valid planar straight-line embedding that triangulates the convex hull.
3. Delaunay empty-circumcircle validity (optional / separate diagnostic).

Degeneracy policy (Delaunay layer only)
---------------------------------------
Cocircularity and empty-circumcircle rules apply **only** when Delaunay
validation is requested (``require_delaunay=True`` / ``check_delaunay=True``).
A valid planar triangulation of a cocircular point set must not be rejected
merely for failing to be a unique Delaunay triangulation when Delaunay is
disabled.

``reject`` (default, with Delaunay requested): reject configurations that
retain represented cocircular point-on-circumcircle incidents.
``lexicographic_tiebreak`` (with Delaunay requested): allow weak Delaunay
(points may lie on circumcircles) via deterministic cavity rules **without**
moving coordinates.
Duplicates and globally collinear sets are always rejected as invalid inputs
for a 2D triangulation.

Sources (retrieved for attribution; code not copied)
----------------------------------------------------
- Shewchuk, J. R. "Adaptive Precision Floating-Point Arithmetic and Fast
  Robust Geometric Predicates." https://people.eecs.berkeley.edu/~jrs/papers/robustr.pdf
- CGAL Triangulation_2 / Delaunay_triangulation_2 reference manuals
  (planar subdivision of the convex hull vs empty-circle property).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from fractions import Fraction
from typing import Any, Mapping, Sequence

# ---------------------------------------------------------------------------
# Public constants / schema
# ---------------------------------------------------------------------------

SCHEMA_VERSION = "neurotopology_sim.planar_triangulation.v1"
PROJECT_STATUS = "HOLD"
DATA_POLICY = "SYNTHETIC_ONLY"

Point = tuple[Fraction, Fraction]
Triangle = tuple[int, int, int]
Edge = tuple[int, int]


class DegeneracyPolicy(str, Enum):
    """How exact degeneracies are handled (no coordinate perturbation)."""

    REJECT = "reject"
    LEXICOGRAPHIC_TIEBREAK = "lexicographic_tiebreak"


class ClaimLayer(str, Enum):
    ABSTRACT_CHAIN = "abstract_chain"
    PLANAR_HULL_TRIANGULATION = "planar_hull_triangulation"
    DELAUNAY_EMPTY_CIRCLE = "delaunay_empty_circle"
    INPUT_VALIDATION = "input_validation"


class FailureKind(str, Enum):
    """Structured failure class (orthogonal to claim-layer diagnostics).

    Distinguishes malformed input from invalid planar embeddings from
    Delaunay/degeneracy-policy failures. ``D1 @ D0 == 0`` never certifies
    geometric validity and is never mapped to a success failure_kind.
    """

    NONE = "none"
    MALFORMED_INPUT = "malformed_input"
    INVALID_PLANAR_EMBEDDING = "invalid_planar_embedding"
    DELAUNAY_POLICY_FAILURE = "delaunay_policy_failure"


@dataclass(frozen=True)
class LayerDiagnostic:
    """Result of one claim layer (engineering only)."""

    layer: str
    status: str  # holds | fails | skipped | inconclusive
    ok: bool
    detail: str
    evidence: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "layer": self.layer,
            "status": self.status,
            "ok": self.ok,
            "detail": self.detail,
            "evidence": dict(self.evidence),
        }


@dataclass(frozen=True)
class PlanarTriangulationResult:
    """Documented triangulation / validation result.

    Fields
    ------
    simplices:
        CCW-oriented triangles as index triples into the input coordinate list.
    hull_cycle:
        Ordered extreme convex-hull vertices (CCW), no collinear mid-edge points.
    hull_boundary_cycle:
        Ordered boundary including input points that lie on hull edges.
    edge_incidences:
        Mapping undirected edge ``(min,max) -> face count`` (1 = boundary, 2 = interior).
    diagnostics:
        Separate layer diagnostics for chain / planar / Delaunay / input.
    """

    schema_version: str
    ok: bool
    status: str  # ok | rejected | inconclusive
    project_status: str
    data_policy: str
    scientific_pass: bool
    degeneracy_policy: str
    failure_kind: str
    n_points: int
    simplices: tuple[Triangle, ...]
    hull_cycle: tuple[int, ...]
    hull_boundary_cycle: tuple[int, ...]
    edge_incidences: Mapping[Edge, int]
    diagnostics: tuple[LayerDiagnostic, ...]
    issues: tuple[str, ...]
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "ok": self.ok,
            "status": self.status,
            "project_status": self.project_status,
            "data_policy": self.data_policy,
            "scientific_pass": False,
            "degeneracy_policy": self.degeneracy_policy,
            "failure_kind": self.failure_kind,
            "n_points": self.n_points,
            "simplices": [list(t) for t in self.simplices],
            "hull_cycle": list(self.hull_cycle),
            "hull_boundary_cycle": list(self.hull_boundary_cycle),
            "edge_incidences": {
                f"{a},{b}": count for (a, b), count in sorted(self.edge_incidences.items())
            },
            "diagnostics": [d.to_dict() for d in self.diagnostics],
            "issues": list(self.issues),
            "notes": list(self.notes),
        }


# ---------------------------------------------------------------------------
# Exact predicates on represented inputs
# ---------------------------------------------------------------------------


def _as_fraction(value: Any) -> Fraction:
    if isinstance(value, bool):
        raise ValueError("boolean is not a geometric coordinate")
    if isinstance(value, Fraction):
        return value
    if isinstance(value, int):
        return Fraction(value)
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):  # NaN/Inf
            raise ValueError("non-finite float coordinate")
        # Represented IEEE binary value (not ideal-real exactness).
        return Fraction.from_float(value)
    raise ValueError(f"unsupported coordinate type: {type(value)!r}")


def _parse_coords(coords: Any) -> list[Point]:
    """Parse 2D coordinates from sequences or NumPy arrays (shape ``(n, 2)``)."""
    # NumPy ndarray support without requiring NumPy at import time.
    if hasattr(coords, "shape") and hasattr(coords, "__getitem__"):
        shape = getattr(coords, "shape", None)
        if shape is not None and len(shape) == 2 and shape[1] == 2:
            rows = [coords[i] for i in range(int(shape[0]))]
        elif shape is not None and len(shape) != 1:
            raise ValueError(f"coords array must have shape (n, 2); got {shape}")
        else:
            rows = list(coords)
    elif isinstance(coords, (list, tuple)):
        rows = list(coords)
    else:
        try:
            rows = list(coords)
        except TypeError as exc:
            raise ValueError("coords must be a sequence or (n, 2) array of 2D points") from exc

    points: list[Point] = []
    for i, row in enumerate(rows):
        try:
            if hasattr(row, "shape") and tuple(getattr(row, "shape", ())) == (2,):
                x, y = row[0], row[1]
            elif isinstance(row, (list, tuple)) and len(row) == 2:
                x, y = row[0], row[1]
            else:
                raise ValueError(f"coords[{i}] must have shape (2,)")
            points.append((_as_fraction(x), _as_fraction(y)))
        except ValueError:
            raise
        except Exception as exc:  # noqa: BLE001 - structured rejection, no raw crash
            raise ValueError(f"coords[{i}] could not be parsed: {exc}") from exc
    return points


def _parse_simplex_index(value: Any, *, n_points: int, context: str) -> int:
    """Validate a simplex vertex index before any array dereference.

    Rejects booleans (``bool`` is a subclass of ``int``), non-integers including
    floats such as ``0.9``, negatives (no Python wraparound), and out-of-range
    indices. Never raises ``IndexError``.
    """
    if isinstance(value, bool):
        raise ValueError(f"{context}: boolean is not a valid simplex index")
    if isinstance(value, float):
        raise ValueError(
            f"{context}: floating-point simplex index is not allowed "
            f"(got {value!r}; reject before conversion/indexing)"
        )
    if not isinstance(value, int):
        # NumPy integer scalars expose .item(); reject float dtypes.
        if hasattr(value, "dtype") and hasattr(value, "item"):
            dtype = getattr(value, "dtype", None)
            kind = getattr(dtype, "kind", None)
            if kind == "b":
                raise ValueError(f"{context}: boolean is not a valid simplex index")
            if kind == "f":
                raise ValueError(
                    f"{context}: floating-point simplex index is not allowed "
                    f"(got {value!r}; reject before conversion/indexing)"
                )
            if kind in ("i", "u"):
                try:
                    value = int(value.item())
                except Exception as exc:  # noqa: BLE001
                    raise ValueError(f"{context}: simplex index must be an integer") from exc
            else:
                raise ValueError(f"{context}: simplex index must be an integer")
        elif hasattr(value, "item") and not hasattr(value, "shape"):
            try:
                value = value.item()
            except Exception as exc:  # noqa: BLE001
                raise ValueError(f"{context}: simplex index must be an integer") from exc
        elif hasattr(value, "shape") and tuple(getattr(value, "shape", (None,))) == ():
            try:
                value = value.item() if hasattr(value, "item") else int(value)  # type: ignore[arg-type]
            except Exception as exc:  # noqa: BLE001
                raise ValueError(f"{context}: simplex index must be an integer") from exc
            if isinstance(value, bool):
                raise ValueError(f"{context}: boolean is not a valid simplex index")
            if isinstance(value, float):
                raise ValueError(
                    f"{context}: floating-point simplex index is not allowed "
                    f"(got {value!r}; reject before conversion/indexing)"
                )
        else:
            raise ValueError(f"{context}: simplex index must be an integer")
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{context}: simplex index must be an integer")
    if value < 0:
        # Phrase keeps Antigravity substring match without raising IndexError /
        # allowing negative-index wraparound.
        raise ValueError(
            f"{context}: out-of-range index {value} "
            f"(negative simplex index is not allowed; n_points={n_points})"
        )
    if value >= n_points:
        raise ValueError(
            f"{context}: out-of-range index {value} for n_points={n_points}"
        )
    return value


def _parse_simplices(
    simplices: Any, *, n_points: int
) -> list[Triangle]:
    """Parse triangle index triples with fail-closed validation (no IndexError)."""
    try:
        rows = list(simplices)
    except TypeError as exc:
        raise ValueError("simplices must be a sequence of index triples") from exc
    out: list[Triangle] = []
    for ti, raw in enumerate(rows):
        context = f"simplex[{ti}]"
        try:
            if hasattr(raw, "shape") and tuple(getattr(raw, "shape", ())) == (3,):
                vals = [raw[0], raw[1], raw[2]]
            elif isinstance(raw, (list, tuple)) and len(raw) == 3:
                vals = [raw[0], raw[1], raw[2]]
            else:
                raise ValueError(f"{context} must contain exactly three indices")
        except ValueError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"{context} could not be parsed: {exc}") from exc
        i = _parse_simplex_index(vals[0], n_points=n_points, context=f"{context}[0]")
        j = _parse_simplex_index(vals[1], n_points=n_points, context=f"{context}[1]")
        k = _parse_simplex_index(vals[2], n_points=n_points, context=f"{context}[2]")
        if len({i, j, k}) != 3:
            raise ValueError(
                f"triangle {ti} is degenerate in indices: repeated vertices "
                f"are not allowed ({context}={i},{j},{k})"
            )
        out.append((i, j, k))
    return out


def orient2d(a: Point, b: Point, c: Point) -> int:
    """Exact orientation sign: +1 if c is left of directed line a→b (CCW)."""
    det = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    if det > 0:
        return 1
    if det < 0:
        return -1
    return 0


def _orient_value(a: Point, b: Point, c: Point) -> Fraction:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def incircle(a: Point, b: Point, c: Point, d: Point) -> int:
    """Exact incircle sign (translated 3×3 form).

    Assumes ``a,b,c`` are not collinear. If ``orient2d(a,b,c) > 0`` (CCW),
    returns +1 when ``d`` is strictly inside the circumcircle of ``a,b,c``,
    -1 when strictly outside, 0 when exactly cocircular.

    Formula matches the standard robust-predicates determinant with exact
    rational arithmetic on represented inputs (not a copied adaptive kernel).
    """
    o = orient2d(a, b, c)
    if o == 0:
        raise ValueError("incircle undefined for collinear a,b,c")
    adx, ady = a[0] - d[0], a[1] - d[1]
    bdx, bdy = b[0] - d[0], b[1] - d[1]
    cdx, cdy = c[0] - d[0], c[1] - d[1]
    alift = adx * adx + ady * ady
    blift = bdx * bdx + bdy * bdy
    clift = cdx * cdx + cdy * cdy
    det = (
        adx * (bdy * clift - cdy * blift)
        - ady * (bdx * clift - cdx * blift)
        + alift * (bdx * cdy - cdx * bdy)
    )
    if o < 0:
        det = -det
    if det > 0:
        return 1
    if det < 0:
        return -1
    return 0


def _edge_key(i: int, j: int) -> Edge:
    return (i, j) if i < j else (j, i)


def _canonicalize_ccw(points: Sequence[Point], i: int, j: int, k: int) -> Triangle:
    if orient2d(points[i], points[j], points[k]) < 0:
        return (i, k, j)
    return (i, j, k)


# ---------------------------------------------------------------------------
# Convex hull (Andrew monotone chain) with exact orientation
# ---------------------------------------------------------------------------


def convex_hull_extreme(points: Sequence[Point]) -> list[int]:
    """Return extreme hull vertex indices in CCW order (no collinear midpoints)."""
    n = len(points)
    if n == 0:
        return []
    order = sorted(range(n), key=lambda i: (points[i][0], points[i][1]))

    def build(seq: Sequence[int]) -> list[int]:
        chain: list[int] = []
        for i in seq:
            while len(chain) >= 2 and orient2d(points[chain[-2]], points[chain[-1]], points[i]) <= 0:
                chain.pop()
            chain.append(i)
        return chain

    lower = build(order)
    upper = build(list(reversed(order)))
    return lower[:-1] + upper[:-1]


def hull_boundary_with_collinear(
    points: Sequence[Point], extreme: Sequence[int]
) -> tuple[list[int], list[Edge]]:
    """Expand extreme hull with input points lying on hull edges; return cycle + edges."""
    if not extreme:
        return [], []
    boundary: list[int] = []
    edges: list[Edge] = []
    for a_idx, b_idx in zip(extreme, (*extreme[1:], extreme[0])):
        a, b = points[a_idx], points[b_idx]
        dx, dy = b[0] - a[0], b[1] - a[1]
        on_edge = [
            i
            for i, p in enumerate(points)
            if orient2d(a, b, p) == 0
            and min(a[0], b[0]) <= p[0] <= max(a[0], b[0])
            and min(a[1], b[1]) <= p[1] <= max(a[1], b[1])
        ]
        on_edge.sort(key=lambda i: (points[i][0] - a[0]) * dx + (points[i][1] - a[1]) * dy)
        if not on_edge or on_edge[0] != a_idx or on_edge[-1] != b_idx:
            # Should not happen for a correct extreme hull; leave incomplete.
            continue
        boundary.extend(on_edge[:-1])
        for u, v in zip(on_edge, on_edge[1:]):
            edges.append(_edge_key(u, v))
    return boundary, sorted(set(edges))


# ---------------------------------------------------------------------------
# Bowyer–Watson Delaunay (exact-sign cavity; no coordinate jitter)
# ---------------------------------------------------------------------------


def _triangle_edges(t: Triangle) -> tuple[Edge, Edge, Edge]:
    i, j, k = t
    return _edge_key(i, j), _edge_key(j, k), _edge_key(k, i)


def _bowyer_watson(
    points: Sequence[Point],
    *,
    reject_exact_cocircular: bool,
) -> tuple[list[Triangle], list[str]]:
    """Compute a triangulation via Bowyer–Watson; returns (triangles, issues).

    ``reject_exact_cocircular`` must be True only when the caller requires a
    Delaunay result under the ``reject`` degeneracy policy. When False, points
    on circumcircles are treated as weak-Delaunay (not strictly inside) so a
    valid planar mesh can still be produced for cocircular inputs.
    """
    issues: list[str] = []
    n = len(points)
    if n < 3:
        return [], ["fewer than 3 points"]

    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    xmin, xmax = min(xs), max(xs)
    ymin, ymax = min(ys), max(ys)
    dx = xmax - xmin
    dy = ymax - ymin
    delta = max(dx, dy, Fraction(1))
    # Super-triangle far outside the axis-aligned bounding box (rational).
    p0 = (xmin - Fraction(2) * delta, ymin - delta)
    p1 = (xmin + Fraction(2) * delta, ymin - delta)
    p2 = (xmin + dx / 2, ymax + Fraction(2) * delta)
    work: list[Point] = list(points) + [p0, p1, p2]
    s0, s1, s2 = n, n + 1, n + 2
    triangles: list[Triangle] = [_canonicalize_ccw(work, s0, s1, s2)]

    for p_idx in range(n):
        bad: list[Triangle] = []
        cocircular_hit = False
        for tri in triangles:
            a, b, c = tri
            # Skip if triangle uses only real points and is somehow collinear
            if orient2d(work[a], work[b], work[c]) == 0:
                continue
            sign = incircle(work[a], work[b], work[c], work[p_idx])
            if sign > 0:
                bad.append(tri)
            elif sign == 0:
                cocircular_hit = True
                # Weak Delaunay: point on circumcircle is not strictly inside.
                # Do not add to cavity.
        if cocircular_hit and reject_exact_cocircular:
            issues.append(
                f"represented cocircularity encountered while inserting point {p_idx}; "
                "rejected because require_delaunay=True and degeneracy_policy=reject"
            )
            return [], issues

        if not bad:
            # Point outside all circumcircles of current triangles — should not
            # happen with a correct super-triangle; treat as failure.
            issues.append(f"insertion cavity empty for point {p_idx}")
            return [], issues

        # Boundary of the polygonal cavity: edges appearing once among bad tris.
        edge_count: dict[Edge, int] = {}
        for tri in bad:
            for e in _triangle_edges(tri):
                edge_count[e] = edge_count.get(e, 0) + 1
        boundary = [e for e, c in edge_count.items() if c == 1]
        # Deterministic order for lexicographic reproducibility.
        boundary.sort()

        triangles = [t for t in triangles if t not in bad]
        for u, v in boundary:
            # Orient new triangle CCW with p_idx.
            tri = _canonicalize_ccw(work, u, v, p_idx)
            if orient2d(work[tri[0]], work[tri[1]], work[tri[2]]) == 0:
                issues.append(f"zero-area triangle while inserting {p_idx}")
                return [], issues
            triangles.append(tri)

    # Remove triangles that touch the super-triangle vertices.
    kept = [t for t in triangles if s0 not in t and s1 not in t and s2 not in t]
    # Ensure CCW
    kept = [_canonicalize_ccw(points, *t) for t in kept]
    kept.sort()  # deterministic simplex list
    return kept, issues


# ---------------------------------------------------------------------------
# Validation layers
# ---------------------------------------------------------------------------


def _edge_incidence_map(simplices: Sequence[Triangle]) -> dict[Edge, int]:
    counts: dict[Edge, int] = {}
    for t in simplices:
        for e in _triangle_edges(t):
            counts[e] = counts.get(e, 0) + 1
    return counts


def _build_d0_d1(
    n_vertices: int, edges: Sequence[Edge], triangles: Sequence[Triangle]
) -> tuple[list[list[int]], list[list[int]]]:
    """Integer coboundary matrices (same sign convention as Round 6 cochain docs)."""
    edge_index = {e: i for i, e in enumerate(edges)}
    d0 = [[0] * n_vertices for _ in edges]
    for e_i, (u, v) in enumerate(edges):
        d0[e_i][v] = 1
        d0[e_i][u] = -1
    d1 = [[0] * len(edges) for _ in triangles]
    for t_i, (i, j, k) in enumerate(triangles):
        # Canonical triangle order i<j<k for coboundary formula, with orientation sign.
        ordered = sorted((i, j, k))
        a, b, c = ordered
        # Permutation sign from (i,j,k) to (a,b,c)
        perm = (i, j, k)
        # Count inversions relative to sorted
        sign = 1
        # Map oriented triangle to coboundary on sorted vertices with sign.
        # For sorted (a,b,c): (d1 ω)= ω_(b,c) - ω_(a,c) + ω_(a,b)
        # If original orientation differs from sorted CCW assumption, flip.
        # Use geometric orientation of original ordering vs sorted.
        # Simpler: use edges of the oriented triangle with + on each directed edge
        # matching Round-6: for canonical i<j<k, coeffs +jk -ik +ij.
        # Orientation of (i,j,k) relative to (a,b,c):
        even = perm in ((a, b, c), (b, c, a), (c, a, b))
        sign = 1 if even else -1
        coeffs = {
            _edge_key(b, c): sign * 1,
            _edge_key(a, c): sign * (-1),
            _edge_key(a, b): sign * 1,
        }
        for e, coeff in coeffs.items():
            d1[t_i][edge_index[e]] += coeff
    return d0, d1


def _matmul(a: Sequence[Sequence[int]], b: Sequence[Sequence[int]]) -> list[list[int]]:
    n, m = len(a), len(a[0]) if a else 0
    p = len(b[0]) if b else 0
    out = [[0] * p for _ in range(n)]
    for i in range(n):
        for k in range(m):
            if a[i][k] == 0:
                continue
            for j in range(p):
                out[i][j] += a[i][k] * b[k][j]
    return out


def _segments_properly_intersect(
    a: Point, b: Point, c: Point, d: Point
) -> bool:
    """True if open segments ab and cd properly intersect (including collinear overlap)."""
    o1 = orient2d(a, b, c)
    o2 = orient2d(a, b, d)
    o3 = orient2d(c, d, a)
    o4 = orient2d(c, d, b)
    if o1 == 0 and o2 == 0 and o3 == 0 and o4 == 0:
        # Collinear: overlap if projections overlap.
        def between(p: Point, q: Point, r: Point) -> bool:
            return (
                min(p[0], q[0]) <= r[0] <= max(p[0], q[0])
                and min(p[1], q[1]) <= r[1] <= max(p[1], q[1])
            )

        return (
            between(a, b, c)
            or between(a, b, d)
            or between(c, d, a)
            or between(c, d, b)
        )
    return o1 != o2 and o3 != o4


def _triangles_overlap_interior(
    points: Sequence[Point], t0: Triangle, t1: Triangle
) -> bool:
    """Detect interior overlap of two CCW triangles (including same-side shared-edge case)."""
    shared = set(t0) & set(t1)
    if len(shared) >= 3:
        return True
    if len(shared) == 2:
        # Share an edge: interiors disjoint iff apexes lie on opposite sides.
        u, v = tuple(shared)
        apex0 = next(x for x in t0 if x not in shared)
        apex1 = next(x for x in t1 if x not in shared)
        o0 = orient2d(points[u], points[v], points[apex0])
        o1 = orient2d(points[u], points[v], points[apex1])
        return o0 != 0 and o1 != 0 and (o0 > 0) == (o1 > 0)

    a0 = (points[t0[0]], points[t0[1]], points[t0[2]])
    a1 = (points[t1[0]], points[t1[1]], points[t1[2]])

    def _strict_inside(p: Point, tri: tuple[Point, Point, Point]) -> bool:
        return (
            orient2d(tri[0], tri[1], p) > 0
            and orient2d(tri[1], tri[2], p) > 0
            and orient2d(tri[2], tri[0], p) > 0
        )

    for p in a0:
        if _strict_inside(p, a1):
            return True
    for p in a1:
        if _strict_inside(p, a0):
            return True

    edges0 = [(t0[0], t0[1]), (t0[1], t0[2]), (t0[2], t0[0])]
    edges1 = [(t1[0], t1[1]), (t1[1], t1[2]), (t1[2], t1[0])]
    for u, v in edges0:
        for r, s in edges1:
            if len({u, v, r, s}) < 4:
                continue
            if _segments_properly_intersect(points[u], points[v], points[r], points[s]):
                return True
    return False


def validate_layers(
    points: Sequence[Point],
    simplices: Sequence[Triangle],
    *,
    check_delaunay: bool,
    degeneracy_policy: DegeneracyPolicy,
) -> tuple[bool, list[LayerDiagnostic], list[str], dict[Edge, int], list[int], list[int]]:
    """Run the three claim layers (+ input shape already assumed parsed)."""
    issues: list[str] = []
    diagnostics: list[LayerDiagnostic] = []
    n = len(points)

    # --- Input structural checks on simplices ---
    for ti, t in enumerate(simplices):
        if len(t) != 3 or len(set(t)) != 3:
            issues.append(f"triangle {ti} is degenerate in indices")
        if any(v < 0 or v >= n for v in t):
            issues.append(f"triangle {ti} has out-of-range index")

    incidences = _edge_incidence_map(simplices)
    extreme = convex_hull_extreme(points)
    boundary_cycle, expected_boundary_edges = hull_boundary_with_collinear(points, extreme)
    expected_boundary_set = set(expected_boundary_edges)

    # --- Layer 1: abstract chain ---
    edges_sorted = sorted(incidences.keys())
    chain_ok = True
    chain_detail = "D1 @ D0 == 0"
    if simplices and edges_sorted:
        d0, d1 = _build_d0_d1(n, edges_sorted, list(simplices))
        prod = _matmul(d1, d0)
        chain_ok = all(all(v == 0 for v in row) for row in prod)
        if not chain_ok:
            issues.append("abstract chain identity D1@D0 failed")
            chain_detail = "D1 @ D0 != 0"
    diagnostics.append(
        LayerDiagnostic(
            layer=ClaimLayer.ABSTRACT_CHAIN.value,
            status="holds" if chain_ok else "fails",
            ok=chain_ok,
            detail=chain_detail,
            evidence={"n_edges": len(edges_sorted), "n_triangles": len(simplices)},
        )
    )

    # --- Layer 2: planar hull triangulation ---
    planar_ok = True
    planar_notes: list[str] = []

    # Positive orientation
    for ti, t in enumerate(simplices):
        o = orient2d(points[t[0]], points[t[1]], points[t[2]])
        if o <= 0:
            planar_ok = False
            issues.append(f"triangle {ti} is not strictly positive-CCW")
            planar_notes.append(f"nonpositive orientation at {ti}")

    # Incidence: boundary edges incidence 1 and match hull; interior 2
    observed_boundary = {e for e, c in incidences.items() if c == 1}
    interior = {e for e, c in incidences.items() if c == 2}
    bad_inc = {e: c for e, c in incidences.items() if c not in (1, 2)}
    if bad_inc:
        planar_ok = False
        issues.append(f"nonmanifold edge incidences: {bad_inc}")
    if observed_boundary != expected_boundary_set:
        planar_ok = False
        issues.append(
            "incidence-one boundary edges do not match independent hull boundary edges"
        )
        planar_notes.append("boundary_mismatch")

    # Coverage: every input point appears in some triangle (for n>=3 triangulation)
    covered = set()
    for t in simplices:
        covered.update(t)
    if n >= 3 and covered != set(range(n)):
        planar_ok = False
        missing = sorted(set(range(n)) - covered)
        issues.append(f"uncovered input points: {missing}")

    # Vertex-on-open-edge degeneracy (T-junction / edge-touch without shared index).
    edge_touch = 0
    for e in incidences:
        a, b = points[e[0]], points[e[1]]
        for v in range(n):
            if v == e[0] or v == e[1]:
                continue
            p = points[v]
            if orient2d(a, b, p) != 0:
                continue
            on_x = min(a[0], b[0]) <= p[0] <= max(a[0], b[0])
            on_y = min(a[1], b[1]) <= p[1] <= max(a[1], b[1])
            if on_x and on_y and p != a and p != b:
                edge_touch += 1
    if edge_touch:
        planar_ok = False
        issues.append(f"{edge_touch} vertex-on-edge degeneracy(ies)")

    # Noncrossing non-shared edges (proper crossings and collinear overlaps).
    boundary_or_all = list(incidences.keys())
    crossings = 0
    for i in range(len(boundary_or_all)):
        for j in range(i + 1, len(boundary_or_all)):
            e1, e2 = boundary_or_all[i], boundary_or_all[j]
            if set(e1) & set(e2):
                continue
            if _segments_properly_intersect(
                points[e1[0]], points[e1[1]], points[e2[0]], points[e2[1]]
            ):
                crossings += 1
    if crossings:
        planar_ok = False
        issues.append(f"{crossings} nonincident edge crossing(s)")

    # Triangle interior overlaps
    overlaps = 0
    for i in range(len(simplices)):
        for j in range(i + 1, len(simplices)):
            if _triangles_overlap_interior(points, simplices[i], simplices[j]):
                overlaps += 1
    if overlaps:
        planar_ok = False
        issues.append(f"{overlaps} overlapping triangle pair(s)")

    # Area partition vs hull (exact Fraction)
    hull_area2 = Fraction(0)
    if len(extreme) >= 3:
        for i in range(len(extreme)):
            a = points[extreme[i]]
            b = points[extreme[(i + 1) % len(extreme)]]
            hull_area2 += a[0] * b[1] - b[0] * a[1]
        if hull_area2 < 0:
            hull_area2 = -hull_area2
    face_area2 = Fraction(0)
    for t in simplices:
        face_area2 += abs(_orient_value(points[t[0]], points[t[1]], points[t[2]]))
    # For a true partition, sum of face areas equals hull area.
    if simplices and hull_area2 != face_area2:
        # Note: equality can hold even with overlaps (Hermes square); keep as soft evidence.
        planar_notes.append("area_sum_vs_hull_mismatch_or_balance")
        # Do not alone decide planar_ok; crossings/overlaps already catch the square.

    diagnostics.append(
        LayerDiagnostic(
            layer=ClaimLayer.PLANAR_HULL_TRIANGULATION.value,
            status="holds" if planar_ok else "fails",
            ok=planar_ok,
            detail="planar straight-line triangulation of convex hull"
            if planar_ok
            else "planar/hull triangulation checks failed",
            evidence={
                "n_extreme_hull": len(extreme),
                "n_boundary_vertices": len(boundary_cycle),
                "n_boundary_edges": len(observed_boundary),
                "n_interior_edges": len(interior),
                "crossings": crossings,
                "overlaps": overlaps,
                "vertex_on_edge": edge_touch,
                "hull_area_twice": str(hull_area2),
                "face_area_sum_twice": str(face_area2),
                "notes": planar_notes,
                "note": (
                    "Positive areas, Euler counts, D1@D0==0, and area-sum equality "
                    "are not sufficient proofs of a valid planar embedding."
                ),
            },
        )
    )

    # --- Layer 3: Delaunay empty circle ---
    if not check_delaunay:
        diagnostics.append(
            LayerDiagnostic(
                layer=ClaimLayer.DELAUNAY_EMPTY_CIRCLE.value,
                status="skipped",
                ok=True,
                detail="Delaunay check not requested",
                evidence={},
            )
        )
        delaunay_ok = True
    else:
        strict_violations = 0
        cocircular_incidents = 0
        for t in simplices:
            if orient2d(points[t[0]], points[t[1]], points[t[2]]) == 0:
                continue
            for p_idx in range(n):
                if p_idx in t:
                    continue
                sign = incircle(points[t[0]], points[t[1]], points[t[2]], points[p_idx])
                if sign > 0:
                    strict_violations += 1
                elif sign == 0:
                    cocircular_incidents += 1
        if strict_violations:
            delaunay_ok = False
            issues.append(f"{strict_violations} strict empty-circle violation(s)")
            status = "fails"
            detail = "point strictly inside a circumcircle"
        elif cocircular_incidents and degeneracy_policy is DegeneracyPolicy.REJECT:
            delaunay_ok = False
            issues.append(
                f"{cocircular_incidents} exact cocircular incident(s); degeneracy_policy=reject"
            )
            status = "fails"
            detail = "exact cocircularity rejected by policy"
        elif cocircular_incidents:
            delaunay_ok = True
            status = "holds"
            detail = (
                "weak Delaunay: no strict interior circumcircle points; "
                "exact cocircularity present (lexicographic_tiebreak)"
            )
        else:
            delaunay_ok = True
            status = "holds"
            detail = "strict empty-circumcircle condition satisfied"
        diagnostics.append(
            LayerDiagnostic(
                layer=ClaimLayer.DELAUNAY_EMPTY_CIRCLE.value,
                status=status,
                ok=delaunay_ok,
                detail=detail,
                evidence={
                    "strict_violations": strict_violations,
                    "exact_cocircular_incidents": cocircular_incidents,
                },
            )
        )

    overall = chain_ok and planar_ok and delaunay_ok and not any(
        "out-of-range" in x or "degenerate in indices" in x for x in issues
    )
    return overall, diagnostics, issues, incidences, extreme, boundary_cycle


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _classify_failure_kind(
    *,
    ok: bool,
    diagnostics: Sequence[LayerDiagnostic],
    issues: Sequence[str],
) -> str:
    """Map layer outcomes to a single structured failure_kind.

    Priority: malformed_input > invalid_planar_embedding > delaunay_policy_failure.
    Abstract-chain success alone never yields ``none`` when planar embedding fails.
    """
    if ok:
        return FailureKind.NONE.value
    by_layer = {d.layer: d for d in diagnostics}
    input_diag = by_layer.get(ClaimLayer.INPUT_VALIDATION.value)
    planar_diag = by_layer.get(ClaimLayer.PLANAR_HULL_TRIANGULATION.value)
    delaunay_diag = by_layer.get(ClaimLayer.DELAUNAY_EMPTY_CIRCLE.value)

    malformed_markers = (
        "out-of-range index",
        "degenerate in indices",
        "floating-point simplex index",
        "boolean is not a valid simplex index",
        "boolean is not a geometric coordinate",
        "non-finite",
        "duplicate coordinates",
        "globally collinear",
        "rank-deficient",
        "need at least 3",
        "must have shape",
        "must be a sequence",
        "zero/degenerate area",
        "could not be parsed",
        "unsupported coordinate",
        "repeated vertices",
        "simplex index must be an integer",
        "must contain exactly three",
    )
    if input_diag is not None and not input_diag.ok:
        return FailureKind.MALFORMED_INPUT.value
    if any(any(m in issue for m in malformed_markers) for issue in issues):
        return FailureKind.MALFORMED_INPUT.value
    if planar_diag is not None and not planar_diag.ok:
        return FailureKind.INVALID_PLANAR_EMBEDDING.value
    if delaunay_diag is not None and delaunay_diag.status == "fails":
        return FailureKind.DELAUNAY_POLICY_FAILURE.value
    # Build-time cocircular / cavity failures with only input_validation present.
    if any("cocircular" in issue or "empty-circle" in issue for issue in issues):
        return FailureKind.DELAUNAY_POLICY_FAILURE.value
    return FailureKind.MALFORMED_INPUT.value


def _empty_result(
    *,
    status: str,
    policy: DegeneracyPolicy,
    n_points: int,
    diagnostics: Sequence[LayerDiagnostic],
    issues: Sequence[str],
    notes: Sequence[str] = (),
    failure_kind: str | None = None,
) -> PlanarTriangulationResult:
    kind = failure_kind or _classify_failure_kind(
        ok=False, diagnostics=diagnostics, issues=issues
    )
    return PlanarTriangulationResult(
        schema_version=SCHEMA_VERSION,
        ok=False,
        status=status,
        project_status=PROJECT_STATUS,
        data_policy=DATA_POLICY,
        scientific_pass=False,
        degeneracy_policy=policy.value,
        failure_kind=kind,
        n_points=n_points,
        simplices=(),
        hull_cycle=(),
        hull_boundary_cycle=(),
        edge_incidences={},
        diagnostics=tuple(diagnostics),
        issues=tuple(issues),
        notes=tuple(notes),
    )


def triangulate_2d(
    coords: Sequence[Sequence[Any]],
    *,
    degeneracy_policy: str | DegeneracyPolicy = DegeneracyPolicy.REJECT,
    require_delaunay: bool = True,
) -> PlanarTriangulationResult:
    """Triangulate a 2D point set with robust exact-sign predicates.

    Parameters
    ----------
    coords:
        Sequence of ``(x, y)`` points. Floats are interpreted as exact binary
        values via ``Fraction.from_float``.
    degeneracy_policy:
        ``\"reject\"`` or ``\"lexicographic_tiebreak\"`` (see module docstring).
    require_delaunay:
        If True, run and require the empty-circle diagnostic layer and apply
        cocircular degeneracy policy. If False, a valid planar triangulation
        is accepted even when the point set is cocircular / non-unique Delaunay.

    Returns
    -------
    PlanarTriangulationResult
        Engineering result only; never a scientific PASS.
    """
    if isinstance(degeneracy_policy, str):
        policy = DegeneracyPolicy(degeneracy_policy)
    else:
        policy = degeneracy_policy

    notes = (
        "HOLD / SYNTHETIC_ONLY: discrete geometry only; not cortical topology.",
        "Floats use represented-input exact-sign policy (Fraction.from_float).",
        "Finite jitter is not Simulation of Simplicity.",
        "D1@D0==0 is an incidence identity only; planar embedding is checked separately.",
    )

    try:
        points = _parse_coords(coords)
    except ValueError as exc:
        diag = LayerDiagnostic(
            layer=ClaimLayer.INPUT_VALIDATION.value,
            status="fails",
            ok=False,
            detail=str(exc),
        )
        return _empty_result(
            status="rejected",
            policy=policy,
            n_points=0,
            diagnostics=[diag],
            issues=[str(exc)],
            notes=notes,
        )

    n = len(points)
    input_issues: list[str] = []

    # Non-finite already rejected in parse.
    # Duplicates
    seen: dict[Point, int] = {}
    for i, p in enumerate(points):
        if p in seen:
            input_issues.append(f"duplicate coordinates at indices {seen[p]} and {i}")
        else:
            seen[p] = i

    # Rank / collinearity
    extreme = convex_hull_extreme(points)
    if n >= 3 and len(extreme) < 3:
        input_issues.append("rank-deficient / globally collinear point set")

    if n < 3:
        input_issues.append("need at least 3 non-collinear points to triangulate")

    if input_issues:
        diag = LayerDiagnostic(
            layer=ClaimLayer.INPUT_VALIDATION.value,
            status="fails",
            ok=False,
            detail="; ".join(input_issues),
            evidence={"n_points": n, "n_extreme_hull": len(extreme)},
        )
        return _empty_result(
            status="rejected",
            policy=policy,
            n_points=n,
            diagnostics=[diag],
            issues=input_issues,
            notes=notes,
        )

    input_diag = LayerDiagnostic(
        layer=ClaimLayer.INPUT_VALIDATION.value,
        status="holds",
        ok=True,
        detail="shape/finite/unique/non-collinear checks passed",
        evidence={"n_points": n, "n_extreme_hull": len(extreme)},
    )

    reject_cocircular = require_delaunay and policy is DegeneracyPolicy.REJECT
    simplices, build_issues = _bowyer_watson(
        points, reject_exact_cocircular=reject_cocircular
    )
    if build_issues and not simplices:
        return _empty_result(
            status="rejected",
            policy=policy,
            n_points=n,
            diagnostics=[input_diag],
            issues=build_issues,
            notes=notes,
        )

    ok, layer_diags, issues, incidences, hull_ext, hull_bound = validate_layers(
        points,
        simplices,
        check_delaunay=require_delaunay,
        degeneracy_policy=policy,
    )
    all_diags = (input_diag, *layer_diags)
    all_issues = tuple(issues + build_issues)
    status = "ok" if ok else "rejected"
    return PlanarTriangulationResult(
        schema_version=SCHEMA_VERSION,
        ok=ok,
        status=status,
        project_status=PROJECT_STATUS,
        data_policy=DATA_POLICY,
        scientific_pass=False,
        degeneracy_policy=policy.value,
        failure_kind=_classify_failure_kind(
            ok=ok, diagnostics=all_diags, issues=all_issues
        ),
        n_points=n,
        simplices=tuple(simplices),
        hull_cycle=tuple(hull_ext),
        hull_boundary_cycle=tuple(hull_bound),
        edge_incidences=dict(sorted(incidences.items())),
        diagnostics=all_diags,
        issues=all_issues,
        notes=notes,
    )


def validate_planar_mesh(
    coords: Sequence[Sequence[Any]],
    simplices: Sequence[Sequence[int]],
    *,
    check_delaunay: bool = False,
    degeneracy_policy: str | DegeneracyPolicy = DegeneracyPolicy.REJECT,
) -> PlanarTriangulationResult:
    """Validate a *supplied* triangle mesh (does not claim the triangulator produced it).

    Use this for adversarial leads such as overlapping diagonal meshes. A failure
    means the supplied mesh is not a valid planar hull triangulation (and/or not
    Delaunay when requested)—not that ``triangulate_2d`` emitted that mesh.
    """
    if isinstance(degeneracy_policy, str):
        policy = DegeneracyPolicy(degeneracy_policy)
    else:
        policy = degeneracy_policy

    notes = (
        "HOLD / SYNTHETIC_ONLY",
        "Validating a supplied mesh; not asserting production origin of simplices.",
    )
    try:
        points = _parse_coords(coords)
        tris = _parse_simplices(simplices, n_points=len(points))
    except (TypeError, ValueError) as exc:
        diag = LayerDiagnostic(
            layer=ClaimLayer.INPUT_VALIDATION.value,
            status="fails",
            ok=False,
            detail=str(exc),
        )
        return _empty_result(
            status="rejected",
            policy=policy,
            n_points=0,
            diagnostics=[diag],
            issues=[str(exc)],
            notes=notes,
        )

    # Reject zero-area triangles before orientation normalization.
    area_issues: list[str] = []
    for ti, t in enumerate(tris):
        if orient2d(points[t[0]], points[t[1]], points[t[2]]) == 0:
            area_issues.append(f"simplex[{ti}] has zero/degenerate area")
    if area_issues:
        diag = LayerDiagnostic(
            layer=ClaimLayer.INPUT_VALIDATION.value,
            status="fails",
            ok=False,
            detail="; ".join(area_issues),
        )
        return _empty_result(
            status="rejected",
            policy=policy,
            n_points=len(points),
            diagnostics=[diag],
            issues=area_issues,
            notes=notes,
        )

    # Normalize orientation for consistent checks (indices already validated).
    oriented = [_canonicalize_ccw(points, *t) for t in tris]
    input_diag = LayerDiagnostic(
        layer=ClaimLayer.INPUT_VALIDATION.value,
        status="holds",
        ok=True,
        detail="coordinates and index lists parsed",
        evidence={"n_points": len(points), "n_simplices": len(oriented)},
    )
    ok, layer_diags, issues, incidences, hull_ext, hull_bound = validate_layers(
        points,
        oriented,
        check_delaunay=check_delaunay,
        degeneracy_policy=policy,
    )
    all_diags = (input_diag, *layer_diags)
    return PlanarTriangulationResult(
        schema_version=SCHEMA_VERSION,
        ok=ok,
        status="ok" if ok else "rejected",
        project_status=PROJECT_STATUS,
        data_policy=DATA_POLICY,
        scientific_pass=False,
        degeneracy_policy=policy.value,
        failure_kind=_classify_failure_kind(
            ok=ok, diagnostics=all_diags, issues=issues
        ),
        n_points=len(points),
        simplices=tuple(oriented),
        hull_cycle=tuple(hull_ext),
        hull_boundary_cycle=tuple(hull_bound),
        edge_incidences=dict(sorted(incidences.items())),
        diagnostics=all_diags,
        issues=tuple(issues),
        notes=notes,
    )


# ---------------------------------------------------------------------------
# Built-in synthetic self-checks (not Antigravity's adversarial suite)
# ---------------------------------------------------------------------------


def _self_check() -> None:
    """Minimal engineering smoke checks for local verification."""
    square = [(0, 0), (1, 0), (1, 1), (0, 1)]
    # Cocircular square is a valid planar triangulation when Delaunay is not required.
    planar_only = triangulate_2d(
        square, degeneracy_policy="reject", require_delaunay=False
    )
    assert planar_only.ok and planar_only.scientific_pass is False
    assert planar_only.project_status == PROJECT_STATUS

    # Same input under Delaunay+reject still fails represented cocircularity.
    delaunay_reject = triangulate_2d(
        square, degeneracy_policy="reject", require_delaunay=True
    )
    assert not delaunay_reject.ok

    # Counterexample B lead: overlapping square mesh must fail planar embedding.
    bad = validate_planar_mesh(square, [(0, 1, 2), (0, 1, 3)], check_delaunay=False)
    assert not bad.ok
    planar = next(d for d in bad.diagnostics if d.layer == "planar_hull_triangulation")
    assert planar.ok is False

    # Malformed indices must not raise IndexError / wrap negatives.
    for bad_faces in (
        [(0, 1, True)],
        [(0, 1, -1)],
        [(0, 1, 99)],
        [(0, 1, 0.5)],
        [(0, 1, 1)],
    ):
        rep = validate_planar_mesh(square[:3], bad_faces)
        assert not rep.ok

    col = triangulate_2d([(0, 0), (1, 0), (2, 0)])
    assert not col.ok
    dup = triangulate_2d([(0, 0), (1, 0), (0, 1), (0, 0)])
    assert not dup.ok
    chain = next(d for d in planar_only.diagnostics if d.layer == "abstract_chain")
    assert chain.ok

    print("planar_triangulation self-check: OK (HOLD / SYNTHETIC_ONLY)")


if __name__ == "__main__":
    _self_check()
