"""Read-only probes for live production paths. Never modifies those modules."""
from __future__ import annotations

import importlib
from typing import Any, Dict, List, Tuple

PRODUCTION_MODULES: Dict[str, Tuple[str, ...]] = {
    "metadata_planning": ("tools.data_access.policy_enforcement.scanner",),
    "bounded_cache_operations": ("tools.data_access.chunk_cache.cache_engine",),
    "cache_eviction": (
        "tools.data_access.chunk_cache.cache_engine",
        "tools.data_access.chunk_cache.eviction",
    ),
    "manifest_recovery": ("tools.streaming.base_runner",),
    "artifact_scanning": ("tools.simulation_artifacts.extractor",),
    "literature_evidence_validation": ("tools.literature_evidence.validation",),
    "research_cycle_smoke_execution": ("tools.release_readiness.research_cycle_smoke.runner",),
    "release_evidence_evaluation": (
        "tools.performance.release_evidence_gate",
        "tools.research_cycle_release.evaluator",
    ),
}

BLOCKED_IMPORT_PREFIXES: Tuple[str, ...] = (
    "apps.awareness_studio",
    "awareness_studio",
    "dataset_acquisition",
)


def probe_module(module_name: str) -> Dict[str, Any]:
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
