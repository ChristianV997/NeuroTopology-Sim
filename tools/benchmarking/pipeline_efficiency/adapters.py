"""Read-only probes and adapters for live production planning paths.

This package never modifies production modules. Imports are fail-closed:
unavailable modules are recorded as ``production_available=False`` and the
workload falls back to a local synthetic contract with the same checksum
policy. Awareness Studio is never imported. Network adapters are never used.
"""
from __future__ import annotations

import importlib
from typing import Any, Callable, Dict, List, Optional, Tuple

PRODUCTION_MODULES: Dict[str, Tuple[str, ...]] = {
    "manifest_planning": ("tools.integration_bridge.artifact_manifest",),
    "bounded_cache_planning": ("tools.data_access.chunk_cache.cache_engine",),
    "artifact_manifest_scanning": ("tools.simulation_artifacts.extractor",),
    "duplicate_detection": ("tools.simulation_artifacts.extractor",),
    "evidence_graph_projection": ("tools.research_record.graph",),
    "release_evidence_evaluation": (
        "tools.performance.release_evidence_gate",
        "tools.research_cycle_release.evaluator",
    ),
    "checkpoint_recovery_planning": ("tools.streaming.checkpoints",),
    "simulation_runner_overhead": ("tools.streaming.process_runner",),
}

# Never imported from this package (owned by other agents / forbidden).
BLOCKED_IMPORT_PREFIXES: Tuple[str, ...] = (
    "apps.awareness_studio",
    "awareness_studio",
    "dataset_acquisition",
)


def probe_module(module_name: str) -> Dict[str, Any]:
    """Attempt a read-only import. Never imports blocked namespaces."""
    for prefix in BLOCKED_IMPORT_PREFIXES:
        if module_name == prefix or module_name.startswith(prefix + "."):
            return {
                "module": module_name,
                "available": False,
                "blocked": True,
                "error": "blocked_namespace",
            }
    try:
        importlib.import_module(module_name)
        return {"module": module_name, "available": True, "blocked": False, "error": None}
    except Exception as exc:  # pragma: no cover - depends on checkout
        return {
            "module": module_name,
            "available": False,
            "blocked": False,
            "error": f"{type(exc).__name__}: {exc}",
        }


def probe_all() -> Dict[str, Any]:
    """Probe every production module referenced by the eight targets."""
    results: List[Dict[str, Any]] = []
    by_target: Dict[str, List[Dict[str, Any]]] = {}
    for target, modules in sorted(PRODUCTION_MODULES.items()):
        rows = [probe_module(name) for name in modules]
        by_target[target] = rows
        results.extend(rows)
    return {
        "targets": by_target,
        "all_available": all(row["available"] for row in results),
        "available_count": sum(1 for row in results if row["available"]),
        "probed_count": len(results),
        "blocked_imports": 0,
        "network_used": False,
        "remote_data_accessed": False,
    }


def production_available(target: str) -> bool:
    modules = PRODUCTION_MODULES.get(target, ())
    return all(probe_module(name)["available"] for name in modules) if modules else False


def load_optional(module_name: str) -> Any:
    if not probe_module(module_name)["available"]:
        return None
    return importlib.import_module(module_name)
