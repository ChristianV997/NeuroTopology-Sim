"""Bounded finite-direction discovery for the local SU(2) principal-symbol screen.

A scan can find sampled counterexamples or unresolved directions. It cannot
certify real characteristics, strong hyperbolicity, or solver well-posedness.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from numbers import Integral
from typing import Literal

import numpy as np

from .local_symbol import analyze_local_skyrme_principal_symbol


MAX_DIRECTIONS_HARD_LIMIT = 4096
MAX_REFINEMENT_LEVELS_HARD_LIMIT = 12
_SCOPE = "finite_nested_icosphere_discovery_only"


@dataclass(frozen=True)
class DirectionScanSample:
    """One evaluated unit covector and the existing analyzer's classification."""

    direction: tuple[float, float, float]
    status: Literal[
        "real_roots_at_sampled_direction",
        "nonreal_roots_detected",
        "numerically_unresolved",
    ]
    characteristic_speeds: tuple[complex, ...]
    root_classification_tolerance: float
    eigenvector_condition_number: float | None
    eigenvector_condition_warning: bool


@dataclass(frozen=True)
class DirectionScanResult:
    """Finite scan output; no status in this record is a global certification."""

    scope: Literal["finite_nested_icosphere_discovery_only"]
    status: Literal[
        "nonreal_roots_sampled",
        "numerically_unresolved_samples",
        "no_nonreal_roots_sampled",
    ]
    samples: tuple[DirectionScanSample, ...]
    max_directions: int
    max_refinement_levels: int
    refinement_levels_completed: int
    termination_reason: Literal[
        "no_suspicious_faces",
        "refinement_level_limit",
        "direction_budget_exhausted",
    ]
    nonreal_sample_count: int
    unresolved_sample_count: int
    condition_warning_sample_count: int

    @property
    def sample_count(self) -> int:
        return len(self.samples)


def _unit(vector: tuple[float, float, float]) -> np.ndarray:
    norm = math.hypot(*(float(value) for value in vector))
    if not math.isfinite(norm) or norm == 0.0:
        raise ValueError("icosphere construction produced an invalid direction")
    return np.asarray(vector, dtype=np.float64) / norm


def _initial_icosphere() -> tuple[list[np.ndarray], list[tuple[int, int, int]]]:
    """Return a fixed, antipodally symmetric icosahedron direction mesh."""
    phi = (1.0 + math.sqrt(5.0)) / 2.0
    raw = (
        (-1.0, phi, 0.0), (1.0, phi, 0.0),
        (-1.0, -phi, 0.0), (1.0, -phi, 0.0),
        (0.0, -1.0, phi), (0.0, 1.0, phi),
        (0.0, -1.0, -phi), (0.0, 1.0, -phi),
        (phi, 0.0, -1.0), (phi, 0.0, 1.0),
        (-phi, 0.0, -1.0), (-phi, 0.0, 1.0),
    )
    vertices = [_unit(point) for point in raw]
    faces = [
        (0, 11, 5), (0, 5, 1), (0, 1, 7), (0, 7, 10), (0, 10, 11),
        (1, 5, 9), (5, 11, 4), (11, 10, 2), (10, 7, 6), (7, 1, 8),
        (3, 9, 4), (3, 4, 2), (3, 2, 6), (3, 6, 8), (3, 8, 9),
        (4, 9, 5), (2, 4, 11), (6, 2, 10), (8, 6, 7), (9, 8, 1),
    ]
    return vertices, faces


def _marked_faces(
    faces: list[tuple[int, int, int]],
    samples: list[DirectionScanSample],
) -> set[int]:
    """Refine only faces touching nonreal, unresolved, or warned samples."""
    return {
        face_index
        for face_index, face in enumerate(faces)
        if any(
            samples[vertex].status != "real_roots_at_sampled_direction"
            or samples[vertex].eigenvector_condition_warning
            for vertex in face
        )
    }


def _ordered_refinement_edges(
    faces: list[tuple[int, int, int]],
    marked: set[int],
) -> list[tuple[int, int]]:
    seen: set[tuple[int, int]] = set()
    ordered: list[tuple[int, int]] = []
    for face_index, face in enumerate(faces):
        if face_index not in marked:
            continue
        a, b, c = face
        for left, right in ((a, b), (b, c), (c, a)):
            edge = (left, right) if left < right else (right, left)
            if edge not in seen:
                seen.add(edge)
                ordered.append(edge)
    return ordered


def _refine_marked_faces(
    vertices: list[np.ndarray],
    faces: list[tuple[int, int, int]],
    marked: set[int],
    edges: list[tuple[int, int]],
) -> tuple[list[tuple[int, int, int]], list[np.ndarray]]:
    """Bisect marked triangles at normalized edge midpoints in stable order."""
    midpoint_index: dict[tuple[int, int], int] = {}
    new_vertices: list[np.ndarray] = []
    for edge in edges:
        left, right = edge
        midpoint = vertices[left] + vertices[right]
        norm = math.hypot(*(float(value) for value in midpoint))
        if not math.isfinite(norm) or norm == 0.0:
            raise ValueError("icosphere refinement encountered an antipodal edge")
        midpoint /= norm
        midpoint_index[edge] = len(vertices) + len(new_vertices)
        new_vertices.append(midpoint)

    refined: list[tuple[int, int, int]] = []
    for face_index, face in enumerate(faces):
        if face_index not in marked:
            refined.append(face)
            continue
        a, b, c = face
        ab = midpoint_index[(a, b) if a < b else (b, a)]
        bc = midpoint_index[(b, c) if b < c else (c, b)]
        ca = midpoint_index[(c, a) if c < a else (a, c)]
        refined.extend(((a, ab, ca), (ab, b, bc), (ca, bc, c), (ab, bc, ca)))
    return refined, new_vertices


def _validate_budgets(max_directions: object, max_refinement_levels: object) -> tuple[int, int]:
    if (
        isinstance(max_directions, bool)
        or not isinstance(max_directions, Integral)
        or not 12 <= int(max_directions) <= MAX_DIRECTIONS_HARD_LIMIT
    ):
        raise ValueError(
            f"max_directions must be an integer from 12 to {MAX_DIRECTIONS_HARD_LIMIT}"
        )
    if (
        isinstance(max_refinement_levels, bool)
        or not isinstance(max_refinement_levels, Integral)
        or not 0 <= int(max_refinement_levels) <= MAX_REFINEMENT_LEVELS_HARD_LIMIT
    ):
        raise ValueError(
            "max_refinement_levels must be an integer from 0 to "
            f"{MAX_REFINEMENT_LEVELS_HARD_LIMIT}"
        )
    return int(max_directions), int(max_refinement_levels)


def scan_local_skyrme_principal_symbol_directions(
    field: object,
    velocity: object,
    spatial_gradients: object,
    *,
    f_pi: object,
    e: object,
    max_directions: int = 642,
    max_refinement_levels: int = 3,
) -> DirectionScanResult:
    """Scan a deterministic, bounded set of spatial covector directions.

    The initial mesh is a fixed 12-vertex icosphere. Refinement adds normalized
    edge midpoints only to faces touching an analyzer-reported nonreal,
    unresolved, or ill-conditioned sample. If the complete next refinement
    would exceed the direction budget, it is not partially applied.

    Inputs and each directional result are validated by the canonical
    one-direction analyzer. Its exceptions propagate; failed evaluations are
    never dropped or counted as successful samples. The returned statuses
    summarize only evaluated directions and never certify all-direction
    hyperbolicity.
    """
    direction_budget, level_budget = _validate_budgets(
        max_directions, max_refinement_levels
    )
    vertices, faces = _initial_icosphere()
    samples: list[DirectionScanSample] = []

    def evaluate(index: int) -> DirectionScanSample:
        direction = vertices[index]
        diagnostic = analyze_local_skyrme_principal_symbol(
            field,
            velocity,
            spatial_gradients,
            direction,
            f_pi=f_pi,
            e=e,
        )
        return DirectionScanSample(
            direction=tuple(float(value) for value in direction),
            status=diagnostic.status,
            characteristic_speeds=diagnostic.characteristic_speeds,
            root_classification_tolerance=diagnostic.root_classification_tolerance,
            eigenvector_condition_number=diagnostic.eigenvector_condition_number,
            eigenvector_condition_warning=diagnostic.eigenvector_condition_warning,
        )

    for index in range(len(vertices)):
        samples.append(evaluate(index))

    completed_levels = 0
    termination_reason = "no_suspicious_faces"
    while True:
        marked = _marked_faces(faces, samples)
        if not marked:
            termination_reason = "no_suspicious_faces"
            break
        if completed_levels >= level_budget:
            termination_reason = "refinement_level_limit"
            break
        edges = _ordered_refinement_edges(faces, marked)
        if len(samples) + len(edges) > direction_budget:
            termination_reason = "direction_budget_exhausted"
            break

        faces, new_vertices = _refine_marked_faces(vertices, faces, marked, edges)
        first_new_index = len(vertices)
        vertices.extend(new_vertices)
        for index in range(first_new_index, len(vertices)):
            samples.append(evaluate(index))
        completed_levels += 1

    nonreal_count = sum(sample.status == "nonreal_roots_detected" for sample in samples)
    unresolved_count = sum(sample.status == "numerically_unresolved" for sample in samples)
    warning_count = sum(sample.eigenvector_condition_warning for sample in samples)
    if nonreal_count:
        status = "nonreal_roots_sampled"
    elif unresolved_count:
        status = "numerically_unresolved_samples"
    else:
        status = "no_nonreal_roots_sampled"

    return DirectionScanResult(
        scope=_SCOPE,
        status=status,
        samples=tuple(samples),
        max_directions=direction_budget,
        max_refinement_levels=level_budget,
        refinement_levels_completed=completed_levels,
        termination_reason=termination_reason,
        nonreal_sample_count=nonreal_count,
        unresolved_sample_count=unresolved_count,
        condition_warning_sample_count=warning_count,
    )
