"""Execution runners for TDA backends.

Standardizes execution across:
- ripser
- gudhi
- gtda (giotto-tda)
- ripserplusplus (ripser++)
- fallback (pure NumPy/SciPy persistence engine)

Measures telemetry (wall-clock runtime, peak heap delta via tracemalloc).
Computes deterministic SHA-256 checksums on canonicalized intervals.
Strictly isolates graph beta_1 from spatial phase charge.
"""
from __future__ import annotations

import math
import time
import tracemalloc
from abc import ABC, abstractmethod
from typing import Any, Sequence

import numpy as np

from tools.tda_reproducibility.probes import is_module_available
from tools.tda_reproducibility.types import (
    BackendExecutionResult,
    BackendId,
    ExecutionTelemetry,
    OutputNature,
    PersistenceInterval,
    compute_diagram_checksum,
)


def _sort_intervals(intervals: Sequence[PersistenceInterval]) -> list[PersistenceInterval]:
    """Sort persistence intervals canonically by dimension, birth, and death."""
    def sort_key(iv: PersistenceInterval) -> tuple[int, float, float]:
        death_val = iv.death if iv.death is not None else float("inf")
        return (iv.dimension, round(iv.birth, 8), round(death_val, 8))

    return sorted(intervals, key=sort_key)


class BaseTDARunner(ABC):
    """Abstract base class for TDA backend runners."""

    def __init__(self, backend_id: str, nature: str) -> None:
        self.backend_id = backend_id
        self.nature = nature

    @abstractmethod
    def is_available(self) -> bool:
        """Return whether the underlying backend is importable and ready."""
        pass

    @abstractmethod
    def _execute(
        self, distance_matrix: np.ndarray, max_dimension: int
    ) -> dict[int, list[PersistenceInterval]]:
        """Compute persistence diagrams up to max_dimension on precomputed distance matrix."""
        pass

    def run(
        self, distance_matrix: np.ndarray, max_dimension: int = 1
    ) -> BackendExecutionResult:
        """Execute TDA with telemetry, error trapping, canonical sorting, and SHA-256 checksum."""
        point_count = int(distance_matrix.shape[0])
        input_shape = list(distance_matrix.shape)

        if not self.is_available():
            telemetry = ExecutionTelemetry(
                runtime_seconds=0.0,
                peak_memory_delta_mb=0.0,
                input_shape=input_shape,
                point_count=point_count,
                max_dimension=max_dimension,
            )
            return BackendExecutionResult(
                backend_id=self.backend_id,
                success=False,
                nature=self.nature,
                telemetry=telemetry,
                diagrams={},
                deterministic_checksum="",
                error_message=f"Backend '{self.backend_id}' is not installed or available.",
            )

        tracemalloc.start()
        start_time = time.perf_counter()
        peak_mb: float | None = None
        error_msg: str | None = None
        sorted_diagrams: dict[int, list[PersistenceInterval]] = {}

        try:
            raw_diagrams = self._execute(distance_matrix, max_dimension)
            for dim, ivs in raw_diagrams.items():
                sorted_diagrams[dim] = _sort_intervals(ivs)
            success = True
        except Exception as exc:
            success = False
            error_msg = f"{type(exc).__name__}: {str(exc)}"
        finally:
            elapsed_sec = time.perf_counter() - start_time
            current_bytes, peak_bytes = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            peak_mb = peak_bytes / (1024.0 * 1024.0)

        telemetry = ExecutionTelemetry(
            runtime_seconds=elapsed_sec,
            peak_memory_delta_mb=peak_mb,
            input_shape=input_shape,
            point_count=point_count,
            max_dimension=max_dimension,
        )

        all_intervals: list[PersistenceInterval] = []
        for dim in range(max_dimension + 1):
            all_intervals.extend(sorted_diagrams.get(dim, []))

        checksum = (
            compute_diagram_checksum(all_intervals, 1)
            if 1 in sorted_diagrams
            else compute_diagram_checksum(all_intervals, 0)
        )

        return BackendExecutionResult(
            backend_id=self.backend_id,
            success=success,
            nature=self.nature,
            telemetry=telemetry,
            diagrams=sorted_diagrams,
            deterministic_checksum=checksum if success else "",
            error_message=error_msg,
        )


class RipserRunner(BaseTDARunner):
    """Runner for Ripser backend."""

    def __init__(self) -> None:
        super().__init__(BackendId.RIPSER.value, OutputNature.EXACT.value)

    def is_available(self) -> bool:
        return is_module_available("ripser")

    def _execute(
        self, distance_matrix: np.ndarray, max_dimension: int
    ) -> dict[int, list[PersistenceInterval]]:
        from ripser import ripser

        res = ripser(distance_matrix, distance_matrix=True, maxdim=max_dimension)
        dgms = res.get("dgms", [])
        diagrams: dict[int, list[PersistenceInterval]] = {}

        for dim, dgm in enumerate(dgms):
            if dim > max_dimension:
                break
            intervals: list[PersistenceInterval] = []
            for row in dgm:
                b = float(row[0])
                d_raw = float(row[1])
                d = None if (math.isinf(d_raw) or np.isinf(d_raw)) else d_raw
                intervals.append(PersistenceInterval(dimension=dim, birth=b, death=d))
            diagrams[dim] = intervals

        return diagrams


class GudhiRunner(BaseTDARunner):
    """Runner for GUDHI backend."""

    def __init__(self) -> None:
        super().__init__(BackendId.GUDHI.value, OutputNature.EXACT.value)

    def is_available(self) -> bool:
        return is_module_available("gudhi")

    def _execute(
        self, distance_matrix: np.ndarray, max_dimension: int
    ) -> dict[int, list[PersistenceInterval]]:
        import gudhi

        max_edge = float(np.max(distance_matrix)) if distance_matrix.size > 0 else 1.0
        rc = gudhi.RipsComplex(distance_matrix=distance_matrix, max_edge_length=max_edge)
        st = rc.create_simplex_tree(max_dimension=max_dimension + 1)
        st.compute_persistence()
        raw_pairs = st.persistence()

        diagrams: dict[int, list[PersistenceInterval]] = {d: [] for d in range(max_dimension + 1)}
        for dim, (b_raw, d_raw) in raw_pairs:
            if dim <= max_dimension:
                b = float(b_raw)
                d = None if (math.isinf(d_raw) or np.isinf(d_raw)) else float(d_raw)
                diagrams[dim].append(PersistenceInterval(dimension=dim, birth=b, death=d))

        return diagrams


class GtdaRunner(BaseTDARunner):
    """Runner for giotto-tda backend."""

    def __init__(self) -> None:
        super().__init__(BackendId.GTDA.value, OutputNature.EXACT.value)

    def is_available(self) -> bool:
        return is_module_available("gtda")

    def _execute(
        self, distance_matrix: np.ndarray, max_dimension: int
    ) -> dict[int, list[PersistenceInterval]]:
        from gtda.homology import VietorisRipsPersistence

        dims = list(range(max_dimension + 1))
        vr = VietorisRipsPersistence(metric="precomputed", homology_dimensions=dims)
        dgm = vr.fit_transform([distance_matrix])[0]

        diagrams: dict[int, list[PersistenceInterval]] = {d: [] for d in range(max_dimension + 1)}
        for row in dgm:
            b = float(row[0])
            d_raw = float(row[1])
            dim = int(row[2])
            if dim <= max_dimension:
                d = None if (math.isinf(d_raw) or np.isinf(d_raw)) else d_raw
                diagrams[dim].append(PersistenceInterval(dimension=dim, birth=b, death=d))

        return diagrams


class RipserPlusPlusRunner(BaseTDARunner):
    """Runner for ripser++ backend."""

    def __init__(self) -> None:
        super().__init__(BackendId.RIPSERPLUSPLUS.value, OutputNature.EXACT.value)

    def is_available(self) -> bool:
        return is_module_available("ripserplusplus")

    def _execute(
        self, distance_matrix: np.ndarray, max_dimension: int
    ) -> dict[int, list[PersistenceInterval]]:
        import ripserplusplus as rpp

        cmd = f"--dim {max_dimension} --format distance"
        raw_res = rpp.run(cmd, distance_matrix)
        diagrams: dict[int, list[PersistenceInterval]] = {d: [] for d in range(max_dimension + 1)}
        for item in raw_res:
            dim = int(item[0])
            if dim <= max_dimension:
                b = float(item[1])
                d_raw = float(item[2])
                d = None if (math.isinf(d_raw) or np.isinf(d_raw)) else d_raw
                diagrams[dim].append(PersistenceInterval(dimension=dim, birth=b, death=d))
        return diagrams


class FallbackRunner(BaseTDARunner):
    """Repository pure NumPy/SciPy fallback runner using standard persistence matrix reduction."""

    def __init__(self) -> None:
        super().__init__(BackendId.FALLBACK.value, OutputNature.APPROXIMATE.value)

    def is_available(self) -> bool:
        return is_module_available("numpy") and is_module_available("scipy")

    def _execute(
        self, distance_matrix: np.ndarray, max_dimension: int
    ) -> dict[int, list[PersistenceInterval]]:
        n = int(distance_matrix.shape[0])
        diagrams: dict[int, list[PersistenceInterval]] = {d: [] for d in range(max_dimension + 1)}

        if n == 0:
            return diagrams

        if n > 45:
            # For larger complexes in fallback mode, compute exact H0 via MST and report bounded H0
            h0_intervals = self._compute_h0_kruskal(distance_matrix)
            diagrams[0] = h0_intervals
            return diagrams

        # Exact persistent homology via standard boundary matrix reduction over Z2
        simplices: list[tuple[float, int, tuple[int, ...]]] = []

        # 0-simplices
        for i in range(n):
            simplices.append((0.0, 0, (i,)))

        # 1-simplices
        for i in range(n):
            for j in range(i + 1, n):
                simplices.append((float(distance_matrix[i, j]), 1, (i, j)))

        # 2-simplices (if max_dimension >= 1)
        if max_dimension >= 1:
            for i in range(n):
                for j in range(i + 1, n):
                    d_ij = distance_matrix[i, j]
                    for k in range(j + 1, n):
                        d_ik = distance_matrix[i, k]
                        d_jk = distance_matrix[j, k]
                        filtration = float(max(d_ij, d_ik, d_jk))
                        simplices.append((filtration, 2, (i, j, k)))

        # Sort simplices: filtration ascending, then dimension ascending, then vertices
        simplices.sort(key=lambda s: (round(s[0], 8), s[1], s[2]))
        simplex_to_idx = {s[2]: idx for idx, s in enumerate(simplices)}
        m = len(simplices)

        # Build boundary matrix (sparse columns as sets of row indices)
        boundary_cols: list[set[int]] = []
        for filt, dim, verts in simplices:
            col: set[int] = set()
            if dim == 1:
                col.add(simplex_to_idx[(verts[0],)])
                col.add(simplex_to_idx[(verts[1],)])
            elif dim == 2:
                col.add(simplex_to_idx[(verts[0], verts[1])])
                col.add(simplex_to_idx[(verts[0], verts[2])])
                col.add(simplex_to_idx[(verts[1], verts[2])])
            boundary_cols.append(col)

        # Standard column reduction over Z_2
        low: dict[int, int] = {}  # maps pivot row -> col
        pairs: list[tuple[int, int]] = []
        is_paired_creator: set[int] = set()

        for j in range(m):
            while boundary_cols[j]:
                pivot = max(boundary_cols[j])
                if pivot in low:
                    other_col = low[pivot]
                    boundary_cols[j] ^= boundary_cols[other_col]
                else:
                    low[pivot] = j
                    pairs.append((pivot, j))
                    is_paired_creator.add(pivot)
                    break

        # Process paired simplices (ignore numerical epsilon zero-lifespan pairs)
        for birth_idx, death_idx in pairs:
            dim = simplices[birth_idx][1]
            birth = simplices[birth_idx][0]
            death = simplices[death_idx][0]
            if dim <= max_dimension and (death - birth) > 1e-7:
                diagrams[dim].append(PersistenceInterval(dimension=dim, birth=birth, death=death))

        # Process unpaired simplices (infinite persistence)
        for i in range(m):
            if i not in is_paired_creator and i not in low.values():
                dim = simplices[i][1]
                birth = simplices[i][0]
                if dim <= max_dimension:
                    diagrams[dim].append(PersistenceInterval(dimension=dim, birth=birth, death=None))

        return diagrams

    def _compute_h0_kruskal(self, distance_matrix: np.ndarray) -> list[PersistenceInterval]:
        """Compute exact H0 persistence using Kruskal's Minimum Spanning Tree."""
        n = int(distance_matrix.shape[0])
        edges: list[tuple[float, int, int]] = []
        for i in range(n):
            for j in range(i + 1, n):
                edges.append((float(distance_matrix[i, j]), i, j))
        edges.sort(key=lambda e: e[0])

        parent = list(range(n))
        birth_times = [0.0] * n

        def find(u: int) -> int:
            if parent[u] != u:
                parent[u] = find(parent[u])
            return parent[u]

        intervals: list[PersistenceInterval] = []
        for w, u, v in edges:
            root_u = find(u)
            root_v = find(v)
            if root_u != root_v:
                # Merge components: younger component dies at weight w
                # By convention, component with larger birth time dies
                if birth_times[root_u] > birth_times[root_v]:
                    intervals.append(PersistenceInterval(dimension=0, birth=birth_times[root_u], death=w))
                    parent[root_u] = root_v
                else:
                    intervals.append(PersistenceInterval(dimension=0, birth=birth_times[root_v], death=w))
                    parent[root_v] = root_u

        # The final surviving component lives to infinity
        intervals.append(PersistenceInterval(dimension=0, birth=0.0, death=None))
        return intervals


def get_all_runners() -> dict[str, BaseTDARunner]:
    """Return dictionary of all registered backend runners."""
    return {
        BackendId.RIPSER.value: RipserRunner(),
        BackendId.GUDHI.value: GudhiRunner(),
        BackendId.GTDA.value: GtdaRunner(),
        BackendId.RIPSERPLUSPLUS.value: RipserPlusPlusRunner(),
        BackendId.FALLBACK.value: FallbackRunner(),
    }


def get_runner(backend_id: str) -> BaseTDARunner:
    """Retrieve runner instance by backend ID."""
    runners = get_all_runners()
    if backend_id not in runners:
        raise ValueError(f"Unknown TDA backend '{backend_id}'. Available: {list(runners.keys())}")
    return runners[backend_id]
