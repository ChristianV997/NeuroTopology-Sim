"""Concrete persistent-homology backend adapters with lazy imports.

All backends adhere to:
- Lazy dynamic imports (never imported at module load time).
- No auto-installations or external downloads.
- Explicit capability probing (available, missing, incompatible, disabled_offline, failed).
- Strict shape handling for point clouds (N, D) and distance matrices (N, N).
- Null serialization for infinite death times.
- Strict cohomology scientific status.
"""
from __future__ import annotations

import os
from typing import Any
import numpy as np

from .base import BaseTDABackend
from .types import (
    BackendCapability,
    BackendCapabilityStatus,
    BackendName,
    InputKind,
    PersistenceInterval,
    PersistencePair,
    ScientificStatus,
    TDAConfig,
)


class RipserBackend(BaseTDABackend):
    """Adapter for the Ripser C++ persistent cohomology engine."""

    @property
    def name(self) -> str:
        return BackendName.RIPSER.value

    def get_capability(self) -> BackendCapability:
        if os.environ.get("NEUROTOPO_DISABLE_RIPSER", "").lower() in ("1", "true", "yes"):
            return BackendCapability(
                name=self.name,
                status=BackendCapabilityStatus.DISABLED_OFFLINE,
                description="Ripser persistent cohomology backend (disabled via environment variable).",
            )
        try:
            import ripser  # noqa: F401
            return BackendCapability(
                name=self.name,
                status=BackendCapabilityStatus.AVAILABLE,
                description="Fast persistent cohomology backend based on Ripser.",
                supported_inputs=[InputKind.POINT_CLOUD, InputKind.DISTANCE_MATRIX],
                max_dimension_supported=2,
                supports_exact_pairs=False,
                details="C++ Ripser bindings via python-ripser.",
            )
        except ImportError:
            return BackendCapability(
                name=self.name,
                status=BackendCapabilityStatus.MISSING,
                description="Ripser persistent cohomology backend (not installed).",
            )
        except Exception as exc:
            return BackendCapability(
                name=self.name,
                status=BackendCapabilityStatus.FAILED,
                description="Ripser persistent cohomology backend failed to initialize.",
                details=str(exc),
            )

    def _compute_intervals_and_pairs(
        self,
        data: np.ndarray,
        input_kind: InputKind,
        config: TDAConfig,
    ) -> tuple[list[PersistenceInterval], list[PersistenceInterval], list[PersistencePair], tuple[float, float | None]]:
        try:
            from ripser import ripser
        except ImportError as exc:
            raise RuntimeError(f"Backend '{self.name}' is missing. Install 'ripser' to use this backend.") from exc

        is_dm = (input_kind == InputKind.DISTANCE_MATRIX)
        thresh = config.max_edge_length if config.max_edge_length is not None else np.inf

        res = ripser(
            data,
            distance_matrix=is_dm,
            maxdim=config.max_dimension,
            thresh=thresh,
        )

        dgms = res.get("dgms", [])
        b0_intervals: list[PersistenceInterval] = []
        b1_intervals: list[PersistenceInterval] = []
        pairs: list[PersistencePair] = []

        if len(dgms) > 0 and len(dgms[0]) > 0:
            for row in dgms[0]:
                birth, death = float(row[0]), float(row[1])
                d_val = None if (np.isinf(death) or death == thresh) else death
                p_val = max(0.0, d_val - birth) if d_val is not None else None
                b0_intervals.append(PersistenceInterval(dimension=0, birth=birth, death=d_val, persistence=p_val))
                pairs.append(PersistencePair(dimension=0, birth=birth, death=d_val))

        if len(dgms) > 1 and len(dgms[1]) > 0:
            for row in dgms[1]:
                birth, death = float(row[0]), float(row[1])
                d_val = None if (np.isinf(death) or death == thresh) else death
                p_val = max(0.0, d_val - birth) if d_val is not None else None
                b1_intervals.append(PersistenceInterval(dimension=1, birth=birth, death=d_val, persistence=p_val))
                pairs.append(PersistencePair(dimension=1, birth=birth, death=d_val))

        b0_intervals.sort(key=lambda iv: (iv.birth, iv.death if iv.death is not None else float("inf")))
        b1_intervals.sort(key=lambda iv: (iv.birth, iv.death if iv.death is not None else float("inf")))

        filt_max = config.max_edge_length
        return b0_intervals, b1_intervals, pairs, (0.0, filt_max)


class GudhiBackend(BaseTDABackend):
    """Adapter for the GUDHI simplicial and persistent homology library."""

    @property
    def name(self) -> str:
        return BackendName.GUDHI.value

    def get_capability(self) -> BackendCapability:
        if os.environ.get("NEUROTOPO_DISABLE_GUDHI", "").lower() in ("1", "true", "yes"):
            return BackendCapability(
                name=self.name,
                status=BackendCapabilityStatus.DISABLED_OFFLINE,
                description="GUDHI TDA backend (disabled via environment variable).",
            )
        try:
            import gudhi  # noqa: F401
            return BackendCapability(
                name=self.name,
                status=BackendCapabilityStatus.AVAILABLE,
                description="GUDHI geometric understanding in higher dimensions.",
                supported_inputs=[InputKind.POINT_CLOUD, InputKind.DISTANCE_MATRIX],
                max_dimension_supported=3,
                supports_exact_pairs=True,
                details="GUDHI SimplexTree and RipsComplex engine.",
            )
        except ImportError:
            return BackendCapability(
                name=self.name,
                status=BackendCapabilityStatus.MISSING,
                description="GUDHI backend (not installed).",
            )
        except Exception as exc:
            return BackendCapability(
                name=self.name,
                status=BackendCapabilityStatus.FAILED,
                description="GUDHI backend failed to initialize.",
                details=str(exc),
            )

    def _compute_intervals_and_pairs(
        self,
        data: np.ndarray,
        input_kind: InputKind,
        config: TDAConfig,
    ) -> tuple[list[PersistenceInterval], list[PersistenceInterval], list[PersistencePair], tuple[float, float | None]]:
        try:
            import gudhi
        except ImportError as exc:
            raise RuntimeError(f"Backend '{self.name}' is missing. Install 'gudhi' to use this backend.") from exc

        thresh = config.max_edge_length if config.max_edge_length is not None else float("inf")

        if input_kind == InputKind.DISTANCE_MATRIX:
            rips = gudhi.RipsComplex(distance_matrix=data, max_edge_length=thresh)
        else:
            rips = gudhi.RipsComplex(points=data, max_edge_length=thresh)

        st = rips.create_simplex_tree(max_dimension=config.max_dimension + 1)
        st.compute_persistence()
        persistence_list = st.persistence()

        b0_intervals: list[PersistenceInterval] = []
        b1_intervals: list[PersistenceInterval] = []
        pairs: list[PersistencePair] = []

        for dim, (birth, death) in persistence_list:
            b_val = float(birth)
            d_val = None if (np.isinf(death) or death == thresh) else float(death)
            p_val = max(0.0, d_val - b_val) if d_val is not None else None

            if dim == 0:
                b0_intervals.append(PersistenceInterval(dimension=0, birth=b_val, death=d_val, persistence=p_val))
                pairs.append(PersistencePair(dimension=0, birth=b_val, death=d_val))
            elif dim == 1:
                b1_intervals.append(PersistenceInterval(dimension=1, birth=b_val, death=d_val, persistence=p_val))
                pairs.append(PersistencePair(dimension=1, birth=b_val, death=d_val))

        b0_intervals.sort(key=lambda iv: (iv.birth, iv.death if iv.death is not None else float("inf")))
        b1_intervals.sort(key=lambda iv: (iv.birth, iv.death if iv.death is not None else float("inf")))

        filt_max = config.max_edge_length
        return b0_intervals, b1_intervals, pairs, (0.0, filt_max)


class RipserPlusPlusBackend(BaseTDABackend):
    """Adapter for GPU-accelerated Ripser++ persistent homology."""

    @property
    def name(self) -> str:
        return BackendName.RIPSER_PLUS_PLUS.value

    def get_capability(self) -> BackendCapability:
        if os.environ.get("NEUROTOPO_DISABLE_RIPSERPLUSPLUS", "").lower() in ("1", "true", "yes"):
            return BackendCapability(
                name=self.name,
                status=BackendCapabilityStatus.DISABLED_OFFLINE,
                description="Ripser++ backend (disabled via environment variable).",
            )
        try:
            import ripserplusplus  # noqa: F401
            return BackendCapability(
                name=self.name,
                status=BackendCapabilityStatus.AVAILABLE,
                description="GPU/CPU accelerated Ripser++ persistent homology.",
                supported_inputs=[InputKind.POINT_CLOUD, InputKind.DISTANCE_MATRIX],
                max_dimension_supported=2,
            )
        except ImportError:
            return BackendCapability(
                name=self.name,
                status=BackendCapabilityStatus.MISSING,
                description="Ripser++ backend (ripserplusplus module not installed).",
            )
        except Exception as exc:
            return BackendCapability(
                name=self.name,
                status=BackendCapabilityStatus.INCOMPATIBLE,
                description="Ripser++ backend found but incompatible with current hardware/environment.",
                details=str(exc),
            )

    def _compute_intervals_and_pairs(
        self,
        data: np.ndarray,
        input_kind: InputKind,
        config: TDAConfig,
    ) -> tuple[list[PersistenceInterval], list[PersistenceInterval], list[PersistencePair], tuple[float, float | None]]:
        try:
            import ripserplusplus
        except ImportError as exc:
            raise RuntimeError(f"Backend '{self.name}' is missing. Install 'ripserplusplus' to use this backend.") from exc

        thresh = config.max_edge_length if config.max_edge_length is not None else -1.0
        # ripserplusplus accepts point clouds or distance matrices depending on bindings
        raw = ripserplusplus.run(
            data,
            dim=config.max_dimension,
            threshold=thresh,
            metric="precomputed" if input_kind == InputKind.DISTANCE_MATRIX else "euclidean",
        )

        b0_intervals: list[PersistenceInterval] = []
        b1_intervals: list[PersistenceInterval] = []
        pairs: list[PersistencePair] = []

        # Parse output format
        if isinstance(raw, dict):
            for dim, dgm in raw.items():
                for row in dgm:
                    b, d = float(row[0]), float(row[1])
                    d_val = None if (np.isinf(d) or d == thresh) else d
                    p_val = max(0.0, d_val - b) if d_val is not None else None
                    if int(dim) == 0:
                        b0_intervals.append(PersistenceInterval(dimension=0, birth=b, death=d_val, persistence=p_val))
                    elif int(dim) == 1:
                        b1_intervals.append(PersistenceInterval(dimension=1, birth=b, death=d_val, persistence=p_val))
                    pairs.append(PersistencePair(dimension=int(dim), birth=b, death=d_val))

        filt_max = config.max_edge_length
        return b0_intervals, b1_intervals, pairs, (0.0, filt_max)


class GiottoTDABackend(BaseTDABackend):
    """Adapter for giotto-tda scikit-learn compatible TDA library."""

    @property
    def name(self) -> str:
        return BackendName.GIOTTO_TDA.value

    def get_capability(self) -> BackendCapability:
        if os.environ.get("NEUROTOPO_DISABLE_GIOTTO", "").lower() in ("1", "true", "yes"):
            return BackendCapability(
                name=self.name,
                status=BackendCapabilityStatus.DISABLED_OFFLINE,
                description="giotto-tda backend (disabled via environment variable).",
            )
        try:
            import gtda  # noqa: F401
            return BackendCapability(
                name=self.name,
                status=BackendCapabilityStatus.AVAILABLE,
                description="giotto-tda scikit-learn compatible persistence library.",
                supported_inputs=[InputKind.POINT_CLOUD, InputKind.DISTANCE_MATRIX],
                max_dimension_supported=2,
            )
        except ImportError:
            return BackendCapability(
                name=self.name,
                status=BackendCapabilityStatus.MISSING,
                description="giotto-tda backend (gtda module not installed).",
            )
        except Exception as exc:
            return BackendCapability(
                name=self.name,
                status=BackendCapabilityStatus.INCOMPATIBLE,
                description="giotto-tda backend incompatible with current python version or packages.",
                details=str(exc),
            )

    def _compute_intervals_and_pairs(
        self,
        data: np.ndarray,
        input_kind: InputKind,
        config: TDAConfig,
    ) -> tuple[list[PersistenceInterval], list[PersistenceInterval], list[PersistencePair], tuple[float, float | None]]:
        try:
            from gtda.homology import VietorisRipsPersistence
        except ImportError as exc:
            raise RuntimeError(f"Backend '{self.name}' is missing. Install 'giotto-tda' to use this backend.") from exc

        metric = "precomputed" if input_kind == InputKind.DISTANCE_MATRIX else "euclidean"
        max_edge = config.max_edge_length if config.max_edge_length is not None else np.inf

        vr = VietorisRipsPersistence(
            metric=metric,
            max_edge_length=max_edge,
            homology_dimensions=list(range(config.max_dimension + 1)),
        )

        batch_input = data[None, :, :]
        dgms = vr.fit_transform(batch_input)[0]  # (K, 3) where [birth, death, dim]

        b0_intervals: list[PersistenceInterval] = []
        b1_intervals: list[PersistenceInterval] = []
        pairs: list[PersistencePair] = []

        for row in dgms:
            b, d, dim = float(row[0]), float(row[1]), int(row[2])
            d_val = None if (np.isinf(d) or d == max_edge) else d
            p_val = max(0.0, d_val - b) if d_val is not None else None
            if dim == 0:
                b0_intervals.append(PersistenceInterval(dimension=0, birth=b, death=d_val, persistence=p_val))
            elif dim == 1:
                b1_intervals.append(PersistenceInterval(dimension=1, birth=b, death=d_val, persistence=p_val))
            pairs.append(PersistencePair(dimension=dim, birth=b, death=d_val))

        filt_max = config.max_edge_length
        return b0_intervals, b1_intervals, pairs, (0.0, filt_max)
