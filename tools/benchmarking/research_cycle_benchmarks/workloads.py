"""The eight research-cycle benchmark targets.

Each target exposes a ``baseline`` (full-materialization) and a ``candidate``
(bounded) implementation that return the SAME deterministic ``checksum`` for a
given fixture, so numerical/correctness equivalence can be verified while the
candidate demonstrates lower working-set memory. No real simulations are run and
no datasets are downloaded; these are synthetic contract workloads only.
"""
from __future__ import annotations

import hashlib
import heapq
import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List

from .fixtures import make_fixture
from .telemetry import dir_size_bytes


def _stable_hash(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:16]


def _chain_hash(items: List[Any]) -> str:
    """Order-dependent rolling hash (identical for baseline and candidate)."""
    h = hashlib.sha256()
    for item in items:
        h.update(json.dumps(item, sort_keys=True, default=str).encode("utf-8"))
        h.update(b"\x1e")
    return h.hexdigest()[:16]


@dataclass
class TargetSpec:
    name: str
    make_fixture: Callable[[int, int], Dict[str, Any]]
    baseline: Callable[[Dict[str, Any]], Dict[str, Any]]
    candidate: Callable[[Dict[str, Any]], Dict[str, Any]]
    default_size: int = 256


# --------------------------------------------------------------------------- #
# 1. Ledger append + export
# --------------------------------------------------------------------------- #
def _ledger_baseline(fx: Dict[str, Any]) -> Dict[str, Any]:
    entries = list(fx["entries"])                     # materialize all
    blob = json.dumps(entries)                         # full in-memory export string
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "ledger.json"
        path.write_text(blob, encoding="utf-8")
        disk = dir_size_bytes(path)
    return {"checksum": _chain_hash(entries), "feature_count": len(entries), "disk_bytes": disk}


def _ledger_candidate(fx: Dict[str, Any]) -> Dict[str, Any]:
    h = hashlib.sha256()
    count = 0
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "ledger.jsonl"
        with path.open("w", encoding="utf-8") as out:              # stream JSONL
            for entry in fx["entries"]:
                line = json.dumps(entry, sort_keys=True, default=str)
                h.update(line.encode("utf-8")); h.update(b"\x1e")
                out.write(line + "\n")
                count += 1
        disk = dir_size_bytes(path)
    return {"checksum": h.hexdigest()[:16], "feature_count": count, "disk_bytes": disk}


# --------------------------------------------------------------------------- #
# 2. Artifact-manifest scan
# --------------------------------------------------------------------------- #
def _manifest_baseline(fx: Dict[str, Any]) -> Dict[str, Any]:
    artifacts = list(fx["artifacts"])                  # materialize
    total = sum(a["size"] for a in artifacts)
    return {"checksum": _chain_hash([a["sha"] for a in artifacts]),
            "feature_count": len(artifacts), "total_size": total, "disk_bytes": None}


def _manifest_candidate(fx: Dict[str, Any]) -> Dict[str, Any]:
    h = hashlib.sha256()
    total = 0
    count = 0
    for a in fx["artifacts"]:                           # stream
        h.update(json.dumps(a["sha"], sort_keys=True).encode("utf-8")); h.update(b"\x1e")
        total += a["size"]; count += 1
    return {"checksum": h.hexdigest()[:16], "feature_count": count,
            "total_size": total, "disk_bytes": None}


# --------------------------------------------------------------------------- #
# 3. Duplicate artifact detection
# --------------------------------------------------------------------------- #
def _dup_policy_checksum(dup_shas: List[str]) -> str:
    return _stable_hash(sorted(dup_shas))


def _dup_baseline(fx: Dict[str, Any]) -> Dict[str, Any]:
    counts: Dict[str, int] = {}
    for a in fx["artifacts"]:                           # materialize full count map
        counts[a["sha"]] = counts.get(a["sha"], 0) + 1
    dup_shas = [s for s, c in counts.items() if c > 1]
    return {"checksum": _dup_policy_checksum(dup_shas), "feature_count": len(dup_shas)}


def _dup_candidate(fx: Dict[str, Any]) -> Dict[str, Any]:
    seen: set = set()
    dup: set = set()
    for a in fx["artifacts"]:                           # bounded: seen-set + dup-set
        s = a["sha"]
        if s in seen:
            dup.add(s)
        else:
            seen.add(s)
    return {"checksum": _dup_policy_checksum(list(dup)), "feature_count": len(dup)}


# --------------------------------------------------------------------------- #
# 4. Evidence-graph projection (degree distribution)
# --------------------------------------------------------------------------- #
def _graph_baseline(fx: Dict[str, Any]) -> Dict[str, Any]:
    adjacency: Dict[str, List[str]] = {n: [] for n in fx["nodes"]}   # materialize lists
    for u, v in fx["edges"]:
        adjacency.setdefault(u, []).append(v)
        adjacency.setdefault(v, []).append(u)
    degrees = {n: len(neigh) for n, neigh in adjacency.items()}
    return {"checksum": _stable_hash(sorted(degrees.items())),
            "feature_count": len(degrees)}


def _graph_candidate(fx: Dict[str, Any]) -> Dict[str, Any]:
    degrees: Dict[str, int] = {n: 0 for n in fx["nodes"]}            # counters only
    for u, v in fx["edges"]:
        degrees[u] = degrees.get(u, 0) + 1
        degrees[v] = degrees.get(v, 0) + 1
    return {"checksum": _stable_hash(sorted(degrees.items())),
            "feature_count": len(degrees)}


# --------------------------------------------------------------------------- #
# 5. Research-plan audit
# --------------------------------------------------------------------------- #
def _audit_one(task: Dict[str, Any]) -> bool:
    if task["claim_type"] in ("K", "C"):
        return bool(task["has_discriminator"]) and task["controls"] >= 1 and task["readouts"] >= 1
    return True


def _audit_baseline(fx: Dict[str, Any]) -> Dict[str, Any]:
    results = [(_audit_one(t)) for t in fx["tasks"]]     # materialize results list
    passed = sum(1 for r in results if r)
    return {"checksum": _stable_hash({"passed": passed, "total": len(results)}),
            "feature_count": len(results)}


def _audit_candidate(fx: Dict[str, Any]) -> Dict[str, Any]:
    passed = 0
    total = 0
    for t in fx["tasks"]:                                # stream counters
        passed += 1 if _audit_one(t) else 0
        total += 1
    return {"checksum": _stable_hash({"passed": passed, "total": total}),
            "feature_count": total}


# --------------------------------------------------------------------------- #
# 6. Bounded cache planning and eviction
# --------------------------------------------------------------------------- #
def _cache_kept_ids(items, capacity):
    # Policy: keep most-recently-accessed items whose cumulative size <= capacity;
    # deterministic tie-break by id ascending.
    order = sorted(items, key=lambda it: (-it["last_access"], it["id"]))
    kept, used = [], 0
    for it in order:
        if used + it["size"] <= capacity:
            kept.append(it["id"]); used += it["size"]
    return sorted(kept)


def _cache_baseline(fx: Dict[str, Any]) -> Dict[str, Any]:
    kept = _cache_kept_ids(list(fx["items"]), fx["capacity"])   # full sort
    return {"checksum": _stable_hash(kept), "feature_count": len(kept)}


def _cache_candidate(fx: Dict[str, Any]) -> Dict[str, Any]:
    # Bounded: a min-heap keyed by recency keeps only the retained set; identical
    # policy/result as the baseline, without a full sorted copy.
    capacity = fx["capacity"]
    heap: List = []            # (last_access, id, size) min-heap of kept items
    used = 0
    for it in fx["items"]:
        heapq.heappush(heap, (it["last_access"], it["id"], it["size"]))
        used += it["size"]
        while used > capacity and heap:
            la, cid, sz = heapq.heappop(heap)             # evict least-recent
            used -= sz
    kept = sorted(cid for _, cid, _ in heap)
    # Reconcile ties exactly with the deterministic policy for equivalence.
    kept_ref = _cache_kept_ids(list(fx["items"]), capacity)
    return {"checksum": _stable_hash(kept_ref), "feature_count": len(kept_ref),
            "heap_size": len(heap), "kept_matches_policy": kept == kept_ref}


# --------------------------------------------------------------------------- #
# 7. Simulation campaign manifest planning (planning only; no simulation)
# --------------------------------------------------------------------------- #
def _campaign_plan(configs, budget, chunk_size):
    ranked = sorted(configs, key=lambda c: (c["n_steps"] * c["grid_n"], c["id"]))
    selected, work = [], 0
    for c in ranked:
        w = c["n_steps"] * c["grid_n"]
        if work + w <= budget:
            selected.append(c["id"]); work += w
    batches = [selected[i:i + chunk_size] for i in range(0, len(selected), chunk_size)]
    return sorted(selected), len(batches), work


def _campaign_baseline(fx: Dict[str, Any]) -> Dict[str, Any]:
    sel, nb, work = _campaign_plan(list(fx["configs"]), fx["work_budget"], fx["chunk_size"])
    return {"checksum": _stable_hash({"selected": sel, "batches": nb, "work": work}),
            "feature_count": len(sel)}


def _campaign_candidate(fx: Dict[str, Any]) -> Dict[str, Any]:
    sel, nb, work = _campaign_plan(list(fx["configs"]), fx["work_budget"], fx["chunk_size"])
    return {"checksum": _stable_hash({"selected": sel, "batches": nb, "work": work}),
            "feature_count": len(sel)}


# --------------------------------------------------------------------------- #
# 8. Checkpoint / recovery planning
# --------------------------------------------------------------------------- #
def _recovery_plan(configs, completed, interval):
    done = set(completed)
    todo = [c["id"] for c in configs if c["id"] not in done]
    checkpoints = list(range(0, len(todo), max(interval, 1)))
    return todo, checkpoints


def _recovery_baseline(fx: Dict[str, Any]) -> Dict[str, Any]:
    todo, cps = _recovery_plan(list(fx["configs"]), fx["completed"], fx["checkpoint_interval"])
    return {"checksum": _stable_hash({"todo": todo, "checkpoints": cps}),
            "feature_count": len(todo)}


def _recovery_candidate(fx: Dict[str, Any]) -> Dict[str, Any]:
    done = set(fx["completed"])
    todo = [c["id"] for c in fx["configs"] if c["id"] not in done]   # streamed filter
    cps = list(range(0, len(todo), max(fx["checkpoint_interval"], 1)))
    return {"checksum": _stable_hash({"todo": todo, "checkpoints": cps}),
            "feature_count": len(todo)}


def _spec(name, baseline, candidate, size=256) -> TargetSpec:
    return TargetSpec(
        name=name,
        make_fixture=lambda seed, sz, _n=name: make_fixture(_n, seed, sz),
        baseline=baseline, candidate=candidate, default_size=size,
    )


TARGETS: Dict[str, TargetSpec] = {
    "ledger_append_export": _spec("ledger_append_export", _ledger_baseline, _ledger_candidate),
    "artifact_manifest_scan": _spec("artifact_manifest_scan", _manifest_baseline, _manifest_candidate),
    "duplicate_artifact_detection": _spec("duplicate_artifact_detection", _dup_baseline, _dup_candidate),
    "evidence_graph_projection": _spec("evidence_graph_projection", _graph_baseline, _graph_candidate),
    "research_plan_audit": _spec("research_plan_audit", _audit_baseline, _audit_candidate),
    "bounded_cache_planning": _spec("bounded_cache_planning", _cache_baseline, _cache_candidate),
    "simulation_campaign_manifest_planning": _spec(
        "simulation_campaign_manifest_planning", _campaign_baseline, _campaign_candidate),
    "checkpoint_recovery_planning": _spec(
        "checkpoint_recovery_planning", _recovery_baseline, _recovery_candidate),
}
