"""TDA backend adapters and availability probes.

Uniformly adapts:
1. ReferenceSimplicialEngine (pure NumPy ground truth, zero external dependencies)
2. Ripser (optional, MIT license)
3. GUDHI Rips & Cubical (optional, MIT license)
4. CubicalRipser (optional, LGPL license)
5. Repository internal modules:
   - core.topology (cubical persistence, betti_curve, persistence_landscape)
   - core.persistence_export (JSON-safe serialization)
   - analysis.connectivity_topology (compute_beta1, compute_persistence_diagram)
   - dual_engine.spectral_tda (spectral_landscape)

Guardrail: Missing optional dependencies are probed cleanly and report
`is_available = False` or `BACKEND_UNAVAILABLE` without crashing or failing.
"""
from __future__ import annotations

import importlib
import math
import time
from typing import Any, Sequence
import numpy as np

from .models import (
    BackendExecutionResult,
    BackendMetadata,
    CoefficientField,
    ConformanceExecutionConfig,
    FiltrationType,
    MetricConvention,
    PersistenceBar,
)
from .reference_engine import compute_vietoris_rips_reference


def is_module_installed(module_name: str) -> bool:
    """Check if a Python module is importable without raising exceptions."""
    try:
        importlib.import_module(module_name)
        return True
    except (ImportError, Exception):
        return False


def get_module_version(module_name: str) -> str | None:
    """Retrieve module version string if available."""
    try:
        mod = importlib.import_module(module_name)
        return getattr(mod, "__version__", getattr(mod, "VERSION", "unknown"))
    except Exception:
        return None


class BaseTDAAdapter:
    """Base class for all TDA adapters."""
    backend_id: str
    license_type: str
    supported_filtrations: list[FiltrationType]
    supported_dimensions: list[int]

    def get_metadata(self) -> BackendMetadata:
        available = self.is_available()
        ver = get_module_version(self.backend_id) if available else None
        return BackendMetadata(
            backend_id=self.backend_id,
            is_available=available,
            version=ver,
            license_type=self.license_type,
            supported_filtrations=self.supported_filtrations,
            supported_dimensions=self.supported_dimensions,
        )

    def is_available(self) -> bool:
        return True

    def compute(
        self,
        data: np.ndarray,
        config: ConformanceExecutionConfig,
    ) -> BackendExecutionResult:
        raise NotImplementedError


class ReferenceSimplicialAdapter(BaseTDAAdapter):
    """Pure NumPy zero-dependency Vietoris-Rips simplicial persistence engine."""
    backend_id = "reference_simplicial"
    license_type = "Repository Built-in (MIT)"
    supported_filtrations = [FiltrationType.VIETORIS_RIPS]
    supported_dimensions = [0, 1, 2]

    def is_available(self) -> bool:
        return True

    def compute(
        self,
        data: np.ndarray,
        config: ConformanceExecutionConfig,
    ) -> BackendExecutionResult:
        start_time = time.perf_counter()
        meta = self.get_metadata()
        try:
            bars_by_dim = compute_vietoris_rips_reference(
                distance_matrix=data,
                max_dimension=config.max_dimension,
                threshold=config.threshold,
            )
            elapsed = time.perf_counter() - start_time
            return BackendExecutionResult(
                backend_meta=meta,
                config=config,
                success=True,
                diagrams=bars_by_dim,
                runtime_seconds=elapsed,
            )
        except Exception as exc:
            elapsed = time.perf_counter() - start_time
            return BackendExecutionResult(
                backend_meta=meta,
                config=config,
                success=False,
                error_message=f"{type(exc).__name__}: {str(exc)}",
                runtime_seconds=elapsed,
            )


class RipserAdapter(BaseTDAAdapter):
    """Adapter for Ulrich Bauer / Christopher Tralie's Ripser (MIT license)."""
    backend_id = "ripser"
    license_type = "MIT"
    supported_filtrations = [FiltrationType.VIETORIS_RIPS]
    supported_dimensions = [0, 1, 2]

    def is_available(self) -> bool:
        return is_module_installed("ripser")

    def compute(
        self,
        data: np.ndarray,
        config: ConformanceExecutionConfig,
    ) -> BackendExecutionResult:
        meta = self.get_metadata()
        if not self.is_available():
            return BackendExecutionResult(
                backend_meta=meta,
                config=config,
                success=False,
                error_message="Optional backend 'ripser' is not installed.",
            )

        start_time = time.perf_counter()
        try:
            import ripser
            thresh = float(config.threshold) if config.threshold is not None else float("inf")
            res = ripser.ripser(
                data,
                distance_matrix=True,
                maxdim=config.max_dimension,
                thresh=thresh,
            )
            dgms = res.get("dgms", [])
            diagrams: dict[int, list[PersistenceBar]] = {}

            for dim, dgm in enumerate(dgms):
                if dim > config.max_dimension:
                    break
                bars: list[PersistenceBar] = []
                for row in dgm:
                    b = float(row[0])
                    d_raw = float(row[1])
                    d = None if (math.isinf(d_raw) or np.isinf(d_raw) or (config.threshold is not None and d_raw >= thresh)) else d_raw
                    bars.append(PersistenceBar.from_pair(dim, b, d))
                # Canonical sort
                bars.sort(key=lambda x: (round(x.birth, 8), round(x.death, 8) if x.death is not None else float("inf")))
                diagrams[dim] = bars

            elapsed = time.perf_counter() - start_time
            return BackendExecutionResult(
                backend_meta=meta,
                config=config,
                success=True,
                diagrams=diagrams,
                runtime_seconds=elapsed,
            )
        except Exception as exc:
            elapsed = time.perf_counter() - start_time
            return BackendExecutionResult(
                backend_meta=meta,
                config=config,
                success=False,
                error_message=f"{type(exc).__name__}: {str(exc)}",
                runtime_seconds=elapsed,
            )


class GudhiRipsAdapter(BaseTDAAdapter):
    """Adapter for GUDHI RipsComplex (MIT license)."""
    backend_id = "gudhi_rips"
    license_type = "MIT"
    supported_filtrations = [FiltrationType.VIETORIS_RIPS]
    supported_dimensions = [0, 1, 2]

    def is_available(self) -> bool:
        return is_module_installed("gudhi")

    def compute(
        self,
        data: np.ndarray,
        config: ConformanceExecutionConfig,
    ) -> BackendExecutionResult:
        meta = self.get_metadata()
        if not self.is_available():
            return BackendExecutionResult(
                backend_meta=meta,
                config=config,
                success=False,
                error_message="Optional backend 'gudhi' is not installed.",
            )

        start_time = time.perf_counter()
        try:
            import gudhi
            max_edge = float(config.threshold) if config.threshold is not None else float(np.max(data)) if data.size > 0 else 1.0
            rc = gudhi.RipsComplex(distance_matrix=data, max_edge_length=max_edge)
            st = rc.create_simplex_tree(max_dimension=config.max_dimension + 1)
            st.compute_persistence()
            raw_pairs = st.persistence()

            diagrams: dict[int, list[PersistenceBar]] = {d: [] for d in range(config.max_dimension + 1)}
            for dim, (b_raw, d_raw) in raw_pairs:
                if dim <= config.max_dimension:
                    b = float(b_raw)
                    d = None if (math.isinf(d_raw) or np.isinf(d_raw)) else float(d_raw)
                    diagrams[dim].append(PersistenceBar.from_pair(dim, b, d))

            for dim in diagrams:
                diagrams[dim].sort(key=lambda x: (round(x.birth, 8), round(x.death, 8) if x.death is not None else float("inf")))

            elapsed = time.perf_counter() - start_time
            return BackendExecutionResult(
                backend_meta=meta,
                config=config,
                success=True,
                diagrams=diagrams,
                runtime_seconds=elapsed,
            )
        except Exception as exc:
            elapsed = time.perf_counter() - start_time
            return BackendExecutionResult(
                backend_meta=meta,
                config=config,
                success=False,
                error_message=f"{type(exc).__name__}: {str(exc)}",
                runtime_seconds=elapsed,
            )


class GudhiCubicalAdapter(BaseTDAAdapter):
    """Adapter for GUDHI CubicalComplex (sublevel persistence on grids)."""
    backend_id = "gudhi_cubical"
    license_type = "MIT"
    supported_filtrations = [FiltrationType.CUBICAL_SUBLEVEL]
    supported_dimensions = [0, 1, 2]

    def is_available(self) -> bool:
        return is_module_installed("gudhi")

    def compute(
        self,
        data: np.ndarray,
        config: ConformanceExecutionConfig,
    ) -> BackendExecutionResult:
        meta = self.get_metadata()
        if not self.is_available():
            return BackendExecutionResult(
                backend_meta=meta,
                config=config,
                success=False,
                error_message="Optional backend 'gudhi' is not installed.",
            )

        start_time = time.perf_counter()
        try:
            import gudhi
            arr = np.asarray(data, dtype=float)
            cc = gudhi.CubicalComplex(top_dimensional_cells=arr)
            cc.persistence()

            diagrams: dict[int, list[PersistenceBar]] = {}
            for dim in range(min(config.max_dimension, arr.ndim) + 1):
                intervals = cc.persistence_intervals_in_dimension(dim)
                bars: list[PersistenceBar] = []
                for row in intervals:
                    b = float(row[0])
                    d_raw = float(row[1])
                    d = None if (math.isinf(d_raw) or np.isinf(d_raw)) else d_raw
                    bars.append(PersistenceBar.from_pair(dim, b, d))
                bars.sort(key=lambda x: (round(x.birth, 8), round(x.death, 8) if x.death is not None else float("inf")))
                diagrams[dim] = bars

            elapsed = time.perf_counter() - start_time
            return BackendExecutionResult(
                backend_meta=meta,
                config=config,
                success=True,
                diagrams=diagrams,
                runtime_seconds=elapsed,
            )
        except Exception as exc:
            elapsed = time.perf_counter() - start_time
            return BackendExecutionResult(
                backend_meta=meta,
                config=config,
                success=False,
                error_message=f"{type(exc).__name__}: {str(exc)}",
                runtime_seconds=elapsed,
            )


def get_all_adapters() -> dict[str, BaseTDAAdapter]:
    """Return dictionary of all configured TDA adapters."""
    return {
        "reference_simplicial": ReferenceSimplicialAdapter(),
        "ripser": RipserAdapter(),
        "gudhi_rips": GudhiRipsAdapter(),
        "gudhi_cubical": GudhiCubicalAdapter(),
    }
