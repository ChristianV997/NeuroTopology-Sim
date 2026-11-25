"""Eight pipeline-efficiency targets wrapping live planning paths.

Each target exposes a naive ``baseline`` and a live or bounded ``candidate``.
Both return the same deterministic ``checksum`` for a fixture. Production
modules are imported read-only; Awareness Studio and remote data are never
used. When a production module is unavailable, a local synthetic contract
is used and ``production_available`` is False.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .adapters import load_optional, production_available
from .fixtures import make_fixture
from .telemetry import dir_size_bytes


def _stable_hash(obj: Any) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, default=str, allow_nan=False).encode("utf-8")
    ).hexdigest()[:16]


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(64 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _input_size(n_items: int, n_bytes: Optional[int] = None) -> Dict[str, Any]:
    return {"n_items": n_items, "bytes": n_bytes}


def _meta(target: str, extra: Dict[str, Any]) -> Dict[str, Any]:
    extra.setdefault("production_available", production_available(target))
    extra.setdefault("worker_count", 1)
    return extra


# --------------------------------------------------------------------------- #
# 1. Manifest planning (integration_bridge.build_manifest)
# --------------------------------------------------------------------------- #
def _write_artifacts(root: Path, artifacts: List[Dict[str, Any]]) -> List[str]:
    paths: List[str] = []
    for art in artifacts:
        rel = art["path"]
        dest = root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(art["content"] if isinstance(art["content"], bytes) else str(art["content"]).encode("utf-8"))
        paths.append(rel)
    return paths


def _manifest_payload(entries: List[Dict[str, Any]]) -> Any:
    return sorted((e["relative_path"], e["sha256"], int(e["size_bytes"])) for e in entries)


def _manifest_baseline(fx: Dict[str, Any]) -> Dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        rels = _write_artifacts(root, fx["artifacts"])
        entries = []
        for rel in rels:
            path = root / rel
            data = path.read_bytes()
            entries.append(
                {
                    "relative_path": rel,
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "size_bytes": len(data),
                }
            )
        disk = dir_size_bytes(root)
    return _meta(
        "manifest_planning",
        {
            "checksum": _stable_hash(_manifest_payload(entries)),
            "feature_count": len(entries),
            "disk_bytes": disk,
            "input_size": _input_size(len(fx["artifacts"]), sum(a["size"] for a in fx["artifacts"])),
            "production_module": "tools.integration_bridge.artifact_manifest.build_manifest",
        },
    )


def _manifest_candidate(fx: Dict[str, Any]) -> Dict[str, Any]:
    mod = load_optional("tools.integration_bridge.artifact_manifest")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        rels = _write_artifacts(root, fx["artifacts"])
        if mod is None:
            entries = []
            for rel in rels:
                data = (root / rel).read_bytes()
                entries.append(
                    {
                        "relative_path": rel,
                        "sha256": hashlib.sha256(data).hexdigest(),
                        "size_bytes": len(data),
                    }
                )
        else:
            manifest = mod.build_manifest(
                run_id=fx["run_id"],
                output_dir=root,
                artifact_relative_paths=rels,
                metadata={"synthetic": True, "evidence_class": "performance_only"},
            )
            payload = manifest.to_dict()
            entries = [
                {
                    "relative_path": row["relative_path"],
                    "sha256": row["sha256"],
                    "size_bytes": row["size_bytes"],
                }
                for row in payload["artifacts"]
            ]
        disk = dir_size_bytes(root)
    return _meta(
        "manifest_planning",
        {
            "checksum": _stable_hash(_manifest_payload(entries)),
            "feature_count": len(entries),
            "disk_bytes": disk,
            "input_size": _input_size(len(fx["artifacts"]), sum(a["size"] for a in fx["artifacts"])),
            "production_module": "tools.integration_bridge.artifact_manifest.build_manifest",
        },
    )


# --------------------------------------------------------------------------- #
# 2. Bounded-cache planning (BoundedChunkCache.plan, no fetch)
# --------------------------------------------------------------------------- #
def _cache_policy(items: List[Dict[str, Any]], capacity: int) -> Dict[str, Any]:
    total = sum(int(it["size"]) for it in items)
    eviction_needed = max(0, total - capacity)
    is_executable = total <= capacity
    return {
        "n_requested": len(items),
        "n_to_download": len(items),
        "total_download_bytes": total,
        "eviction_required_bytes": eviction_needed,
        "is_executable": is_executable,
        "paths": sorted(it["bids_path"] for it in items),
    }


def _cache_baseline(fx: Dict[str, Any]) -> Dict[str, Any]:
    policy = _cache_policy(fx["items"], fx["capacity"])
    return _meta(
        "bounded_cache_planning",
        {
            "checksum": _stable_hash(policy),
            "feature_count": policy["n_requested"],
            "disk_bytes": None,
            "input_size": _input_size(len(fx["items"]), sum(it["size"] for it in fx["items"])),
            "production_module": "tools.data_access.chunk_cache.cache_engine.BoundedChunkCache.plan",
        },
    )


def _cache_candidate(fx: Dict[str, Any]) -> Dict[str, Any]:
    engine = load_optional("tools.data_access.chunk_cache.cache_engine")
    types_mod = load_optional("tools.data_access.chunk_cache")
    if engine is None or types_mod is None:
        policy = _cache_policy(fx["items"], fx["capacity"])
        return _meta(
            "bounded_cache_planning",
            {
                "checksum": _stable_hash(policy),
                "feature_count": policy["n_requested"],
                "disk_bytes": None,
                "input_size": _input_size(len(fx["items"]), sum(it["size"] for it in fx["items"])),
                "production_module": "tools.data_access.chunk_cache.cache_engine.BoundedChunkCache.plan",
                "production_available": False,
            },
        )
    with tempfile.TemporaryDirectory() as tmp:
        cache = engine.BoundedChunkCache(
            cache_root=tmp,
            max_cache_bytes=int(fx["capacity"]),
            min_free_headroom_bytes=0,
            transfer_adapter=types_mod.MockTransferAdapter(),
        )
        requested = []
        for it in fx["items"]:
            cache.register_manifest_item(
                dataset_id=fx["dataset_id"],
                bids_path=it["bids_path"],
                source_uri=f"file:///local/synthetic/{fx['dataset_id']}/{it['bids_path']}",
                size_bytes=int(it["size"]),
            )
            requested.append((it["bids_path"], 0))
        plan = cache.plan(fx["dataset_id"], requested)
        policy = {
            "n_requested": len(plan.requested_items),
            "n_to_download": len(plan.items_to_download),
            "total_download_bytes": int(plan.total_download_bytes),
            "eviction_required_bytes": int(plan.eviction_required_bytes),
            "is_executable": bool(plan.is_executable),
            "paths": sorted(item["bids_path"] for item in plan.requested_items),
        }
        disk = dir_size_bytes(tmp)
    return _meta(
        "bounded_cache_planning",
        {
            "checksum": _stable_hash(policy),
            "feature_count": policy["n_requested"],
            "disk_bytes": disk,
            "input_size": _input_size(len(fx["items"]), sum(it["size"] for it in fx["items"])),
            "production_module": "tools.data_access.chunk_cache.cache_engine.BoundedChunkCache.plan",
        },
    )


# --------------------------------------------------------------------------- #
# 3–4. Artifact lineage scan + duplicate detection
# --------------------------------------------------------------------------- #
def _materialize_run(root: Path, files: List[Dict[str, Any]]) -> None:
    for row in files:
        path = root / row["name"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(row["payload"], sort_keys=True, allow_nan=False), encoding="utf-8")


def _scan_files(root: Path) -> List[Dict[str, Any]]:
    entries = []
    for path in sorted(root.rglob("*")):
        if path.is_file():
            rel = path.relative_to(root).as_posix()
            entries.append(
                {
                    "relative_path": rel,
                    "sha256": _file_sha256(path),
                    "size_bytes": path.stat().st_size,
                }
            )
    return sorted(entries, key=lambda e: e["relative_path"])


def _dup_from_entries(entries: List[Dict[str, Any]]) -> List[str]:
    by_hash: Dict[str, List[str]] = {}
    for entry in entries:
        by_hash.setdefault(entry["sha256"], []).append(entry["relative_path"])
    return sorted(digest for digest, paths in by_hash.items() if len(paths) > 1)


def _scan_baseline(fx: Dict[str, Any]) -> Dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _materialize_run(root, fx["files"])
        entries = _scan_files(root)
        disk = dir_size_bytes(root)
    return _meta(
        "artifact_manifest_scanning",
        {
            "checksum": _stable_hash([(e["relative_path"], e["sha256"], e["size_bytes"]) for e in entries]),
            "feature_count": len(entries),
            "disk_bytes": disk,
            "input_size": _input_size(len(fx["files"])),
            "production_module": "tools.simulation_artifacts.extractor.extract_run",
        },
    )


def _scan_candidate(fx: Dict[str, Any]) -> Dict[str, Any]:
    extractor = load_optional("tools.simulation_artifacts.extractor")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _materialize_run(root, fx["files"])
        if extractor is None:
            entries = _scan_files(root)
        else:
            report = extractor.extract_run(root)
            entries = [
                {
                    "relative_path": item["relative_path"],
                    "sha256": item["sha256"],
                    "size_bytes": item["size_bytes"],
                }
                for item in report["artifact_manifest"]["artifacts"]
            ]
        disk = dir_size_bytes(root)
    return _meta(
        "artifact_manifest_scanning",
        {
            "checksum": _stable_hash([(e["relative_path"], e["sha256"], e["size_bytes"]) for e in entries]),
            "feature_count": len(entries),
            "disk_bytes": disk,
            "input_size": _input_size(len(fx["files"])),
            "production_module": "tools.simulation_artifacts.extractor.extract_run",
        },
    )


def _dup_baseline(fx: Dict[str, Any]) -> Dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _materialize_run(root, fx["files"])
        dups = _dup_from_entries(_scan_files(root))
        disk = dir_size_bytes(root)
    return _meta(
        "duplicate_detection",
        {
            "checksum": _stable_hash(dups),
            "feature_count": len(dups),
            "disk_bytes": disk,
            "input_size": _input_size(len(fx["files"])),
            "production_module": "tools.simulation_artifacts.extractor.extract_run",
        },
    )


def _dup_candidate(fx: Dict[str, Any]) -> Dict[str, Any]:
    extractor = load_optional("tools.simulation_artifacts.extractor")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _materialize_run(root, fx["files"])
        if extractor is None:
            dups = _dup_from_entries(_scan_files(root))
        else:
            report = extractor.extract_run(root)
            dups = sorted(item["sha256"] for item in report["artifact_manifest"]["duplicate_content"])
        disk = dir_size_bytes(root)
    return _meta(
        "duplicate_detection",
        {
            "checksum": _stable_hash(dups),
            "feature_count": len(dups),
            "disk_bytes": disk,
            "input_size": _input_size(len(fx["files"])),
            "production_module": "tools.simulation_artifacts.extractor.extract_run",
        },
    )


# --------------------------------------------------------------------------- #
# 5. Evidence-graph projection (research_record.graph, not Awareness Studio)
# --------------------------------------------------------------------------- #
def _graph_checksum_from_nodes(nodes_raw: List[Dict[str, Any]]) -> Dict[str, Any]:
    graph = load_optional("tools.research_record.graph")
    if graph is None:
        open_ids = sorted(
            n["number"]
            for n in nodes_raw
            if n["merge_status"] == "open" and n["ci_status"] != "failed"
        )
        return {"ordered": open_ids, "excluded": sorted(n["number"] for n in nodes_raw if n["number"] not in open_ids)}
    nodes = [
        graph.PRNode(
            number=int(n["number"]),
            branch=n.get("branch"),
            base_branch=n.get("base_branch"),
            parent_pr=n.get("parent_pr"),
            merge_status=str(n["merge_status"]),
            status_category=str(n["status_category"]),
            is_draft=n.get("is_draft"),
            is_ancestor_of_target=n.get("is_ancestor_of_target"),
            mergeable=n.get("mergeable"),
            ci_status=str(n["ci_status"]),
            superseded_by_pr=n.get("superseded_by_pr"),
            duplicate_of_pr=n.get("duplicate_of_pr"),
            depends_on=tuple(n.get("depends_on") or ()),
        )
        for n in nodes_raw
    ]
    ordered, excluded = graph.recommended_merge_order(nodes)
    return {"ordered": list(ordered), "excluded": sorted((int(k), str(v)) for k, v in excluded.items())}


def _graph_baseline(fx: Dict[str, Any]) -> Dict[str, Any]:
    copied = json.loads(json.dumps(fx["nodes"]))
    payload = _graph_checksum_from_nodes(copied)
    return _meta(
        "evidence_graph_projection",
        {
            "checksum": _stable_hash(payload),
            "feature_count": len(fx["nodes"]),
            "disk_bytes": None,
            "input_size": _input_size(len(fx["nodes"])),
            "production_module": "tools.research_record.graph.recommended_merge_order",
        },
    )


def _graph_candidate(fx: Dict[str, Any]) -> Dict[str, Any]:
    payload = _graph_checksum_from_nodes(fx["nodes"])
    return _meta(
        "evidence_graph_projection",
        {
            "checksum": _stable_hash(payload),
            "feature_count": len(fx["nodes"]),
            "disk_bytes": None,
            "input_size": _input_size(len(fx["nodes"])),
            "production_module": "tools.research_record.graph.recommended_merge_order",
        },
    )


# --------------------------------------------------------------------------- #
# 6. Release-evidence evaluation
# --------------------------------------------------------------------------- #
def _release_decisions(fx: Dict[str, Any], *, materialize: bool) -> Dict[str, Any]:
    gate = load_optional("tools.performance.release_evidence_gate")
    cycle_mod = load_optional("tools.research_cycle_release.evaluator")
    decisions: List[str] = []
    reports: List[Dict[str, Any]] = []
    if gate is None:
        for pair in fx["pairs"]:
            cand = pair["candidate"]
            if cand.get("timeout_status"):
                decisions.append("TIMEOUT_FAILURE")
            elif cand.get("checksum") != pair["baseline"].get("checksum"):
                decisions.append("CORRECTNESS_FAILURE")
            else:
                decisions.append("EVIDENCE_READY")
    else:
        for pair in fx["pairs"]:
            report = gate.evaluate_release_evidence(pair["baseline"], pair["candidate"])
            decisions.append(report.decision.value)
            if materialize:
                reports.append(report.to_dict())
    cycle_decision = None
    if cycle_mod is not None:
        cycle_report = cycle_mod.evaluate_research_cycle_release(fx["cycle"], adapter_hint="generic")
        cycle_decision = cycle_report.decision.value
        if materialize:
            reports.append(cycle_report.to_dict())
    return {"decisions": decisions, "cycle_decision": cycle_decision, "n_reports": len(reports)}


def _release_baseline(fx: Dict[str, Any]) -> Dict[str, Any]:
    payload = _release_decisions(fx, materialize=True)
    return _meta(
        "release_evidence_evaluation",
        {
            "checksum": _stable_hash({"decisions": payload["decisions"], "cycle": payload["cycle_decision"]}),
            "feature_count": len(payload["decisions"]),
            "disk_bytes": None,
            "input_size": _input_size(len(fx["pairs"])),
            "production_module": "tools.performance.release_evidence_gate.evaluate_release_evidence",
        },
    )


def _release_candidate(fx: Dict[str, Any]) -> Dict[str, Any]:
    payload = _release_decisions(fx, materialize=False)
    return _meta(
        "release_evidence_evaluation",
        {
            "checksum": _stable_hash({"decisions": payload["decisions"], "cycle": payload["cycle_decision"]}),
            "feature_count": len(payload["decisions"]),
            "disk_bytes": None,
            "input_size": _input_size(len(fx["pairs"])),
            "production_module": "tools.performance.release_evidence_gate.evaluate_release_evidence",
        },
    )


# --------------------------------------------------------------------------- #
# 7. Checkpoint / recovery planning
# --------------------------------------------------------------------------- #
def _config_hash_stdlib(cfg: Dict[str, Any]) -> str:
    payload = {
        "backend": str(cfg["backend"]),
        "check_finite": bool(cfg["check_finite"]),
        "chunk_size": int(cfg["chunk_size"]),
        "dtype": str(cfg["dtype"]),
        "n_channels": int(cfg["n_channels"]),
        "n_samples": int(cfg["n_samples"]),
        "overlap": int(cfg["overlap"]),
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _recovery_plan(fx: Dict[str, Any], cfg_hash: str) -> Dict[str, Any]:
    done = set(fx["completed"])
    todo = [c["id"] for c in fx["configs"] if c["id"] not in done]
    interval = max(int(fx["checkpoint_interval"]), 1)
    checkpoints = list(range(0, len(todo), interval))
    return {"cfg": cfg_hash, "todo": todo, "checkpoints": checkpoints}


def _recovery_baseline(fx: Dict[str, Any]) -> Dict[str, Any]:
    payload = _recovery_plan(fx, _config_hash_stdlib(fx["config"]))
    return _meta(
        "checkpoint_recovery_planning",
        {
            "checksum": _stable_hash(payload),
            "feature_count": len(payload["todo"]),
            "disk_bytes": None,
            "input_size": _input_size(len(fx["configs"])),
            "production_module": "tools.streaming.checkpoints.compute_configuration_hash",
        },
    )


def _recovery_candidate(fx: Dict[str, Any]) -> Dict[str, Any]:
    ckpt = load_optional("tools.streaming.checkpoints")
    if ckpt is None:
        cfg_hash = _config_hash_stdlib(fx["config"])
        available = False
    else:
        cfg_hash = ckpt.compute_configuration_hash(**fx["config"])
        available = True
    payload = _recovery_plan(fx, cfg_hash)
    return _meta(
        "checkpoint_recovery_planning",
        {
            "checksum": _stable_hash(payload),
            "feature_count": len(payload["todo"]),
            "disk_bytes": None,
            "input_size": _input_size(len(fx["configs"])),
            "production_module": "tools.streaming.checkpoints.compute_configuration_hash",
            "production_available": available,
        },
    )


# --------------------------------------------------------------------------- #
# 8. Bounded simulation-runner overhead (process_runner.run_one, trivial child)
# --------------------------------------------------------------------------- #
def _child_argv(payload: Dict[str, Any]) -> List[str]:
    blob = json.dumps(payload, sort_keys=True, allow_nan=False)
    return [sys.executable, "-c", f"import json; print({blob!r})"]


def _runner_baseline(fx: Dict[str, Any]) -> Dict[str, Any]:
    argv = _child_argv(fx["child_payload"])
    proc = subprocess.run(argv, capture_output=True, text=True, timeout=fx["timeout_s"], check=False)
    line = (proc.stdout or "").strip().splitlines()[-1] if proc.stdout.strip() else "{}"
    parsed = json.loads(line)
    payload = {
        "exit_code": proc.returncode,
        "checksum": parsed.get("checksum"),
        "correctness_ok": parsed.get("correctness_ok"),
    }
    return _meta(
        "simulation_runner_overhead",
        {
            "checksum": _stable_hash(payload),
            "feature_count": 1,
            "disk_bytes": None,
            "input_size": _input_size(1, fx.get("input_bytes")),
            "production_module": "tools.streaming.process_runner.run_one",
            "worker_count": 1,
        },
    )


def _runner_candidate(fx: Dict[str, Any]) -> Dict[str, Any]:
    runner = load_optional("tools.streaming.process_runner")
    argv = _child_argv(fx["child_payload"])
    if runner is None:
        return _runner_baseline(fx)
    result = runner.run_one(
        argv,
        {"target": "simulation_runner_overhead", "synthetic": True},
        timeout_s=float(fx["timeout_s"]),
        required_metrics=("checksum",),
        sample_rss=False,
    )
    payload = {
        "exit_code": result.exit_code,
        "checksum": result.checksum,
        "correctness_ok": result.correctness_ok,
    }
    return _meta(
        "simulation_runner_overhead",
        {
            "checksum": _stable_hash(payload),
            "feature_count": 1,
            "disk_bytes": None,
            "input_size": _input_size(1, fx.get("input_bytes")),
            "production_module": "tools.streaming.process_runner.run_one",
            "worker_count": 1,
        },
    )


@dataclass
class TargetSpec:
    name: str
    make_fixture: Callable[[int, int], Dict[str, Any]]
    baseline: Callable[[Dict[str, Any]], Dict[str, Any]]
    candidate: Callable[[Dict[str, Any]], Dict[str, Any]]
    default_size: int = 48
    path_family: str = ""


def _spec(name: str, baseline, candidate, *, size: int = 48, path_family: str = "") -> TargetSpec:
    return TargetSpec(
        name=name,
        make_fixture=lambda seed, sz, _n=name: make_fixture(_n, seed, sz),
        baseline=baseline,
        candidate=candidate,
        default_size=size,
        path_family=path_family,
    )


TARGETS: Dict[str, TargetSpec] = {
    "manifest_planning": _spec(
        "manifest_planning",
        _manifest_baseline,
        _manifest_candidate,
        path_family="simulation-planning",
    ),
    "bounded_cache_planning": _spec(
        "bounded_cache_planning",
        _cache_baseline,
        _cache_candidate,
        path_family="bounded-cache",
        size=32,
    ),
    "artifact_manifest_scanning": _spec(
        "artifact_manifest_scanning",
        _scan_baseline,
        _scan_candidate,
        path_family="artifact-lineage",
    ),
    "duplicate_detection": _spec(
        "duplicate_detection",
        _dup_baseline,
        _dup_candidate,
        path_family="artifact-lineage",
    ),
    "evidence_graph_projection": _spec(
        "evidence_graph_projection",
        _graph_baseline,
        _graph_candidate,
        path_family="research-cycle",
    ),
    "release_evidence_evaluation": _spec(
        "release_evidence_evaluation",
        _release_baseline,
        _release_candidate,
        path_family="research-cycle",
        size=24,
    ),
    "checkpoint_recovery_planning": _spec(
        "checkpoint_recovery_planning",
        _recovery_baseline,
        _recovery_candidate,
        path_family="research-cycle",
    ),
    "simulation_runner_overhead": _spec(
        "simulation_runner_overhead",
        _runner_baseline,
        _runner_candidate,
        path_family="simulation-planning",
        size=8,
    ),
}
