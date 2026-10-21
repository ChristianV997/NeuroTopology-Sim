"""Finite simplicial chain complex — independent oracle model.

Chain convention (homology, not cohomology):
  C3 --∂3→ C2 --∂2→ C1 --∂1→ C0
  ∂k : C_k → C_{k-1}, matrix shape (dim C_{k-1}) × (dim C_k)
  Exactness check: ∂k @ ∂_{k+1} = 0

Proposal naming map (for audit notes only):
  d0 ↔ ∂1, d1 ↔ ∂2, d2 ↔ ∂3
  Standard matrix product is d0 @ d1 = 0 and d1 @ d2 = 0.
  A candidate that checks ``d1 @ d0 = 0`` is using transposed / reverse
  operand order relative to this oracle and must be reconciled explicitly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction
from typing import Iterable, Sequence

from tools.batch2_chain_complex_audit.errors import (
    CellSpecError,
    DuplicateError,
    EndpointError,
    FaceSpecError,
    OrientationError,
)
from tools.batch2_chain_complex_audit.rank import exact_rank


def _canon_edge(a: int, b: int) -> tuple[int, int]:
    return (a, b) if a < b else (b, a)


def _edge_sign_in_oriented(u: int, v: int, edge: tuple[int, int]) -> int:
    """Sign of oriented edge (u→v) relative to stored undirected edge (lo, hi)."""
    lo, hi = edge
    if {u, v} != {lo, hi}:
        raise FaceSpecError(f"vertices ({u},{v}) do not match edge {edge}")
    if u == lo and v == hi:
        return +1
    if u == hi and v == lo:
        return -1
    raise FaceSpecError(f"cannot orient ({u},{v}) on edge {edge}")


@dataclass(frozen=True)
class FiniteChainComplex:
    """Validated finite simplicial complex up to dimension 3.

    Edges are stored as oriented pairs ``(src, dst)`` with ``src != dst``.
    Faces are triples of vertex indices ``(a,b,c)`` with induced boundary
    ``ab + bc + ca`` relative to the edge list.
    Cells (3-simplices) are 4-tuples of vertex indices with the standard
    alternating face boundary.
    """

    n_vertices: int
    edges: tuple[tuple[int, int], ...]
    faces: tuple[tuple[int, int, int], ...] = ()
    cells: tuple[tuple[int, int, int, int], ...] = ()

    # Cached index maps built in __post_init__ via object.__setattr__
    _edge_index: dict[tuple[int, int], int] = field(init=False, repr=False, compare=False)
    _face_index: dict[tuple[int, int, int], int] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self.n_vertices < 0:
            raise EndpointError("n_vertices must be non-negative")
        object.__setattr__(self, "edges", tuple(self.edges))
        object.__setattr__(self, "faces", tuple(self.faces))
        object.__setattr__(self, "cells", tuple(self.cells))
        self._validate_edges()
        edge_index = {_canon_edge(*e): i for i, e in enumerate(self.edges)}
        object.__setattr__(self, "_edge_index", edge_index)
        self._validate_faces()
        face_index = {tuple(sorted(f)): i for i, f in enumerate(self.faces)}
        object.__setattr__(self, "_face_index", face_index)
        self._validate_cells()

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def _validate_edges(self) -> None:
        seen: set[tuple[int, int]] = set()
        for i, (a, b) in enumerate(self.edges):
            if not isinstance(a, int) or not isinstance(b, int):
                raise EndpointError(f"edge {i}: endpoints must be int")
            if a < 0 or b < 0:
                raise EndpointError(f"edge {i}: negative endpoint {(a, b)}")
            if a >= self.n_vertices or b >= self.n_vertices:
                raise EndpointError(
                    f"edge {i}: out-of-range endpoint {(a, b)} "
                    f"for n_vertices={self.n_vertices}"
                )
            if a == b:
                raise EndpointError(f"edge {i}: self-loop {(a, b)}")
            key = _canon_edge(a, b)
            if key in seen:
                raise DuplicateError(f"duplicate edge {key}")
            seen.add(key)

    def _validate_faces(self) -> None:
        seen: set[tuple[int, int, int]] = set()
        for i, face in enumerate(self.faces):
            if len(face) != 3:
                raise FaceSpecError(f"face {i}: expected 3 vertices, got {face}")
            a, b, c = face
            for v in (a, b, c):
                if not isinstance(v, int):
                    raise FaceSpecError(f"face {i}: non-int vertex")
                if v < 0 or v >= self.n_vertices:
                    raise EndpointError(
                        f"face {i}: vertex {v} out of range "
                        f"[0, {self.n_vertices})"
                    )
            if len({a, b, c}) != 3:
                raise FaceSpecError(f"face {i}: repeated vertices {face}")
            key = tuple(sorted(face))
            if key in seen:
                raise DuplicateError(f"duplicate face {key}")
            seen.add(key)
            # Every oriented boundary edge must exist in the 1-skeleton.
            for u, v in ((a, b), (b, c), (c, a)):
                ck = _canon_edge(u, v)
                if ck not in self._edge_index:
                    raise FaceSpecError(
                        f"face {i}: missing edge {ck} in 1-skeleton"
                    )

    def _validate_cells(self) -> None:
        seen: set[tuple[int, int, int, int]] = set()
        for i, cell in enumerate(self.cells):
            if len(cell) != 4:
                raise CellSpecError(f"cell {i}: expected 4 vertices, got {cell}")
            verts = tuple(cell)
            for v in verts:
                if not isinstance(v, int):
                    raise CellSpecError(f"cell {i}: non-int vertex")
                if v < 0 or v >= self.n_vertices:
                    raise EndpointError(
                        f"cell {i}: vertex {v} out of range "
                        f"[0, {self.n_vertices})"
                    )
            if len(set(verts)) != 4:
                raise CellSpecError(f"cell {i}: repeated vertices {cell}")
            key = tuple(sorted(verts))
            if key in seen:
                raise DuplicateError(f"duplicate cell {key}")
            seen.add(key)
            # All four faces must exist.
            for face in _tet_faces(verts):
                fk = tuple(sorted(face))
                if fk not in self._face_index:
                    raise CellSpecError(
                        f"cell {i}: missing face {fk} in 2-skeleton"
                    )

    # ------------------------------------------------------------------
    # Boundary matrices (Fraction entries)
    # ------------------------------------------------------------------

    def boundary_1(self) -> list[list[Fraction]]:
        """∂1 : C1 → C0, shape (n_vertices, n_edges)."""
        n0, n1 = self.n_vertices, len(self.edges)
        m = [[Fraction(0) for _ in range(n1)] for _ in range(n0)]
        for j, (a, b) in enumerate(self.edges):
            # Oriented edge a→b : ∂ = b - a
            m[b][j] += Fraction(1)
            m[a][j] -= Fraction(1)
        return m

    def boundary_2(self) -> list[list[Fraction]]:
        """∂2 : C2 → C1, shape (n_edges, n_faces)."""
        n1, n2 = len(self.edges), len(self.faces)
        m = [[Fraction(0) for _ in range(n2)] for _ in range(n1)]
        for j, (a, b, c) in enumerate(self.faces):
            for u, v in ((a, b), (b, c), (c, a)):
                ck = _canon_edge(u, v)
                ei = self._edge_index[ck]
                stored = self.edges[ei]
                # Contribution relative to stored orientation of the edge.
                # Stored edge is (src, dst); canon may differ from stored.
                sign = _incidence_sign(stored, u, v)
                m[ei][j] += Fraction(sign)
        return m

    def boundary_3(self) -> list[list[Fraction]]:
        """∂3 : C3 → C2, shape (n_faces, n_cells)."""
        n2, n3 = len(self.faces), len(self.cells)
        m = [[Fraction(0) for _ in range(n3)] for _ in range(n2)]
        for j, cell in enumerate(self.cells):
            for face, sign in _tet_face_incidences(cell):
                fk = tuple(sorted(face))
                fi = self._face_index[fk]
                # Adjust for stored face orientation vs tet face orientation.
                stored = self.faces[fi]
                orient = _triangle_orient_sign(stored, face)
                m[fi][j] += Fraction(sign * orient)
        return m

    def composition_zero(self) -> dict[str, bool]:
        """Check ∂1∂2 = 0 and ∂2∂3 = 0 as exact Fraction matrix products."""
        d1 = self.boundary_1()
        d2 = self.boundary_2()
        d3 = self.boundary_3()
        return {
            "d1_d2": _mat_is_zero(_matmul(d1, d2)),
            "d2_d3": _mat_is_zero(_matmul(d2, d3)),
        }

    def betti(self) -> tuple[int, int, int, int]:
        """Return (β0, β1, β2, β3) from exact ranks and matrix dimensions.

        Formulas (finite complex, no 4-cells):
          r1 = rank(∂1), r2 = rank(∂2), r3 = rank(∂3)
          β0 = n0 - r1
          β1 = n1 - r1 - r2
          β2 = n2 - r2 - r3
          β3 = n3 - r3
        """
        n0 = self.n_vertices
        n1 = len(self.edges)
        n2 = len(self.faces)
        n3 = len(self.cells)
        r1 = exact_rank(self.boundary_1()) if n0 and n1 else 0
        r2 = exact_rank(self.boundary_2()) if n1 and n2 else 0
        r3 = exact_rank(self.boundary_3()) if n2 and n3 else 0
        # Empty-complex / empty-degree edge cases handled by zero dims.
        b0 = n0 - r1
        b1 = n1 - r1 - r2
        b2 = n2 - r2 - r3
        b3 = n3 - r3
        return (b0, b1, b2, b3)

    def ranks(self) -> dict[str, int]:
        return {
            "rank_d1": exact_rank(self.boundary_1()) if self.edges else 0,
            "rank_d2": exact_rank(self.boundary_2()) if self.faces else 0,
            "rank_d3": exact_rank(self.boundary_3()) if self.cells else 0,
            "n0": self.n_vertices,
            "n1": len(self.edges),
            "n2": len(self.faces),
            "n3": len(self.cells),
        }


def _incidence_sign(stored_edge: tuple[int, int], u: int, v: int) -> int:
    """+1 if (u→v) agrees with stored (src→dst), else -1."""
    src, dst = stored_edge
    if (u, v) == (src, dst):
        return +1
    if (u, v) == (dst, src):
        return -1
    raise FaceSpecError(f"({u},{v}) not incident to stored edge {stored_edge}")


def _triangle_orient_sign(
    stored: tuple[int, int, int], oriented: tuple[int, int, int]
) -> int:
    """+1 if oriented is an even perm of stored, -1 if odd; error if different set."""
    if set(stored) != set(oriented):
        raise FaceSpecError(f"{oriented} != {stored} as unordered faces")
    # Map oriented into stored positions and take permutation parity.
    pos = {v: i for i, v in enumerate(stored)}
    perm = [pos[v] for v in oriented]
    # Bubble-count inversions
    inv = 0
    p = list(perm)
    for i in range(len(p)):
        for j in range(i + 1, len(p)):
            if p[i] > p[j]:
                inv += 1
    return +1 if inv % 2 == 0 else -1


def _tet_faces(
    verts: Sequence[int],
) -> tuple[tuple[int, int, int], ...]:
    a, b, c, d = verts
    # Standard ordered faces of tet [a,b,c,d] (geometric, before signs):
    return (
        (b, c, d),
        (a, d, c),
        (a, b, d),
        (a, c, b),
    )


def _tet_face_incidences(
    verts: Sequence[int],
) -> list[tuple[tuple[int, int, int], int]]:
    """Faces of oriented tetrahedron [a,b,c,d] with boundary signs.

    ∂[a,b,c,d] = [b,c,d] - [a,c,d] + [a,b,d] - [a,b,c]
               = +(b,c,d) + (a,d,c) + (a,b,d) + (a,c,b)
    """
    a, b, c, d = verts
    return [
        ((b, c, d), +1),
        ((a, c, d), -1),
        ((a, b, d), +1),
        ((a, b, c), -1),
    ]


def _matmul(
    a: list[list[Fraction]], b: list[list[Fraction]]
) -> list[list[Fraction]]:
    if not a or not b:
        return []
    n, k = len(a), len(a[0])
    k2, m = len(b), len(b[0]) if b else 0
    if k != k2:
        raise ValueError(f"incompatible shapes ({n}x{k}) @ ({k2}x{m})")
    out = [[Fraction(0) for _ in range(m)] for _ in range(n)]
    for i in range(n):
        for j in range(m):
            s = Fraction(0)
            for t in range(k):
                s += a[i][t] * b[t][j]
            out[i][j] = s
    return out


def _mat_is_zero(m: list[list[Fraction]]) -> bool:
    return all(x == 0 for row in m for x in row)


def validate_orientation_signs(signs: Iterable[int]) -> None:
    """Reject orientation signs outside {-1, +1}."""
    for s in signs:
        if s not in (-1, 1):
            raise OrientationError(f"invalid orientation sign {s!r}")


def signed_edge_boundary_of_faces(
    face_edge_incidences: Sequence[Sequence[tuple[int, int]]],
    *,
    n_edges: int,
) -> list[int]:
    """Sum signed edge incidences over a collection of oriented faces.

    ``face_edge_incidences[f]`` is a list of ``(edge_index, sign)``.
    Returns length-``n_edges`` integer vector (the ∂2 column-sum / 3-cell
    edge shadow). Used to show that absolute double coverage is not enough.
    """
    total = [0] * n_edges
    for incidences in face_edge_incidences:
        seen_in_face: set[int] = set()
        for ei, sign in incidences:
            if sign not in (-1, 1):
                raise OrientationError(f"invalid sign {sign}")
            if ei < 0 or ei >= n_edges:
                raise EndpointError(f"edge index {ei} out of range")
            if ei in seen_in_face:
                raise FaceSpecError(f"duplicate edge {ei} inside one face")
            seen_in_face.add(ei)
            total[ei] += sign
    return total


def absolute_edge_counts(
    face_edge_incidences: Sequence[Sequence[tuple[int, int]]],
    *,
    n_edges: int,
) -> list[int]:
    """Absolute incidence counts (the insufficient 'appears twice' check)."""
    total = [0] * n_edges
    for incidences in face_edge_incidences:
        for ei, _sign in incidences:
            if ei < 0 or ei >= n_edges:
                raise EndpointError(f"edge index {ei} out of range")
            total[ei] += 1
    return total


def assert_signed_cell_boundary_cancels(
    face_edge_incidences: Sequence[Sequence[tuple[int, int]]],
    *,
    n_edges: int,
) -> None:
    """Require every edge coefficient in the signed sum to be zero."""
    signed = signed_edge_boundary_of_faces(
        face_edge_incidences, n_edges=n_edges
    )
    if any(v != 0 for v in signed):
        raise CellSpecError(
            f"signed edge boundary does not cancel: {signed}"
        )
