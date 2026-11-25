"""Backend availability and capability probes for TDA libraries.

Probes the 5 targeted backends:
1. ripser
2. gudhi
3. gtda (giotto-tda)
4. ripserplusplus (ripser++)
5. fallback (repository NumPy/SciPy fallback)

Strictly non-intrusive: never executes live network calls or automatic installations.
"""
from __future__ import annotations

import importlib.util
from typing import Sequence

from tools.tda_reproducibility.types import (
    BackendId,
    BackendProbeReport,
    BackendStatus,
)


def is_module_available(module_name: str) -> bool:
    """Check if a module is importable without triggering heavy initialization."""
    try:
        spec = importlib.util.find_spec(module_name)
        return spec is not None
    except (ImportError, AttributeError, ValueError):
        return False


def get_module_version(module_name: str) -> str | None:
    """Safely obtain module version if available."""
    try:
        mod = __import__(module_name)
        version = getattr(mod, "__version__", None)
        return str(version) if version is not None else None
    except Exception:
        return None


def probe_ripser() -> BackendProbeReport:
    """Probe ripser availability and capabilities."""
    avail = is_module_available("ripser")
    version = get_module_version("ripser") if avail else None
    status = BackendStatus.AVAILABLE.value if avail else BackendStatus.MISSING.value
    notes = "Installed and functional for H0 and H1 cohomology." if avail else "ripser package not installed in environment."
    return BackendProbeReport(
        backend_id=BackendId.RIPSER.value,
        status=status,
        is_available=avail,
        version=version,
        max_dimension_supported=2,
        supports_distance_matrix=True,
        supports_point_cloud=True,
        is_exact=True,
        notes=notes,
    )


def probe_gudhi() -> BackendProbeReport:
    """Probe GUDHI availability and capabilities."""
    avail = is_module_available("gudhi")
    version = get_module_version("gudhi") if avail else None
    status = BackendStatus.AVAILABLE.value if avail else BackendStatus.MISSING.value
    notes = "GUDHI RipsComplex / SimplexTree available." if avail else "gudhi package not installed in environment."
    return BackendProbeReport(
        backend_id=BackendId.GUDHI.value,
        status=status,
        is_available=avail,
        version=version,
        max_dimension_supported=3,
        supports_distance_matrix=True,
        supports_point_cloud=True,
        is_exact=True,
        notes=notes,
    )


def probe_gtda() -> BackendProbeReport:
    """Probe giotto-tda availability and capabilities."""
    avail = is_module_available("gtda")
    version = get_module_version("gtda") if avail else None
    status = BackendStatus.AVAILABLE.value if avail else BackendStatus.MISSING.value
    notes = "giotto-tda VietorisRipsPersistence available." if avail else "gtda (giotto-tda) package not installed."
    return BackendProbeReport(
        backend_id=BackendId.GTDA.value,
        status=status,
        is_available=avail,
        version=version,
        max_dimension_supported=2,
        supports_distance_matrix=True,
        supports_point_cloud=True,
        is_exact=True,
        notes=notes,
    )


def probe_ripserplusplus() -> BackendProbeReport:
    """Probe ripser++ availability and capabilities."""
    avail = is_module_available("ripserplusplus")
    version = get_module_version("ripserplusplus") if avail else None
    status = BackendStatus.AVAILABLE.value if avail else BackendStatus.MISSING.value
    notes = "ripser++ GPU/multicore engine available." if avail else "ripserplusplus package not installed in environment."
    return BackendProbeReport(
        backend_id=BackendId.RIPSERPLUSPLUS.value,
        status=status,
        is_available=avail,
        version=version,
        max_dimension_supported=2,
        supports_distance_matrix=True,
        supports_point_cloud=True,
        is_exact=True,
        notes=notes,
    )


def probe_fallback() -> BackendProbeReport:
    """Probe repository pure NumPy/SciPy fallback availability."""
    numpy_avail = is_module_available("numpy")
    scipy_avail = is_module_available("scipy")
    avail = numpy_avail and scipy_avail
    version = get_module_version("numpy") if avail else None
    status = BackendStatus.AVAILABLE.value if avail else BackendStatus.MISSING.value
    notes = "Pure NumPy/SciPy bounded Vietoris-Rips / graph persistence fallback."
    return BackendProbeReport(
        backend_id=BackendId.FALLBACK.value,
        status=status,
        is_available=avail,
        version=version,
        max_dimension_supported=1,
        supports_distance_matrix=True,
        supports_point_cloud=True,
        is_exact=False,
        notes=notes,
    )


def has_tda_adapters_module() -> bool:
    """Check whether topo_monitor.tda_adapters is present and importable."""
    return is_module_available("topo_monitor.tda_adapters")


def probe_all_backends() -> list[BackendProbeReport]:
    """Probe all 5 target TDA backends and return standardized probe reports."""
    return [
        probe_ripser(),
        probe_gudhi(),
        probe_gtda(),
        probe_ripserplusplus(),
        probe_fallback(),
    ]
