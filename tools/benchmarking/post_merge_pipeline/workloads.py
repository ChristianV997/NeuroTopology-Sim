"""Eight post-merge targets wrapping live planning/recovery paths read-only.

Baseline and candidate return the same deterministic checksum. Production
modules are never edited. Remote datasets and AWS are never contacted.
"""
from __future__ import annotations

import hashlib
import json
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Dict, List

from .adapters import load_optional, production_available
from .fixtures import make_fixture
from tools.benchmarking.pipeline_efficiency.telemetry import dir_size_bytes


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


def _input_size(n_items: int, n_bytes: int | None = None) -> Dict[str, Any]:
    return {"n_items": n_items, "bytes": n_bytes}


def _meta(target: str, extra: Dict[str, Any]) -> Dict[str, Any]:
    extra.setdefault("production_available", production_available(target))
    extra.setdefault("worker_count", 1)
    return extra


def _write_tree(root: Path, files: List[Dict[str, Any]]) -> None:
    for row in files:
        dest = root / row["path"]
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(row["content"], encoding="utf-8")


def _inventory(root: Path) -> List[Dict[str, Any]]:
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
    return entries


# --------------------------------------------------------------------------- #
# 1. Metadata planning (policy scanner over synthetic sources)
# --------------------------------------------------------------------------- #
def _metadata_payload(entries: List[Dict[str, Any]]) -> Any:
    return sorted((e["relative_path"], e["sha256"], int(e["size_bytes"])) for e in entries)


def _metadata_baseline(fx: Dict[str, Any]) -> Dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_tree(root, fx["files"])
        entries = _inventory(root)
        disk = dir_size_bytes(root)
    return _meta(
        "metadata_planning",
        {
            "checksum": _stable_hash(_metadata_payload(entries)),
            "feature_count": len(entries),
            "disk_bytes": disk,
            "input_size": _input_size(len(fx["files"])),
            "production_module": "tools.data_access.policy_enforcement.scanner.scan_paths",
        },
    )


def _metadata_candidate(fx: Dict[str, Any]) -> Dict[str, Any]:
    scanner = load_optional("tools.data_access.policy_enforcement.scanner")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_tree(root, fx["files"])
        entries = _inventory(root)
        if scanner is not None:
            scanner.scan_paths([root], repository_root=root)
        disk = dir_size_bytes(root)
    return _meta(
        "metadata_planning",
        {
            "checksum": _stable_hash(_metadata_payload(entries)),
            "feature_count": len(entries),
            "disk_bytes": disk,
            "input_size": _input_size(len(fx["files"])),
            "production_module": "tools.data_access.policy_enforcement.scanner.scan_paths",
            "production_available": scanner is not None,
        },
    )


# --------------------------------------------------------------------------- #
# 2. Bounded cache operations (plan only, MockTransferAdapter, no fetch)
# --------------------------------------------------------------------------- #
def _cache_policy(items: List[Dict[str, Any]], capacity: int, n_cached: int) -> Dict[str, Any]:
    cached = items[:n_cached]
    uncached = items[n_cached:]
    cached_bytes = sum(int(it["size"]) for it in cached)
    download = sum(int(it["size"]) for it in uncached)
    headroom = max(0, int(capacity) - cached_bytes)
    return {
        "n_requested": len(items),
        "n_cached": n_cached,
        "n_to_download": len(uncached),
        "total_download_bytes": download,
        "eviction_required_bytes": max(0, download - headroom),
        "paths": sorted(it["bids_path"] for it in items),
    }


def _plant_cached(cache, dataset_id: str, items: List[Dict[str, Any]], n_cached: int) -> None:
    for it in items[:n_cached]:
        dest = cache.cache_root / dataset_id / PurePosixPath(it["bids_path"])
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"x" * int(it["size"]))
    for it in items:
        cache.register_manifest_item(
            dataset_id=dataset_id,
            bids_path=it["bids_path"],
            source_uri=f"file:///local/synthetic/{dataset_id}/{it['bids_path']}",
            size_bytes=int(it["size"]),
        )


def _bounded_baseline(fx: Dict[str, Any]) -> Dict[str, Any]:
    n_cached = max(1, len(fx["items"]) // 4)
    policy = _cache_policy(fx["items"], fx["capacity"], n_cached)
    return _meta(
        "bounded_cache_operations",
        {
            "checksum": _stable_hash(policy),
            "feature_count": policy["n_requested"],
            "disk_bytes": None,
            "input_size": _input_size(len(fx["items"]), sum(it["size"] for it in fx["items"])),
            "production_module": "tools.data_access.chunk_cache.cache_engine.BoundedChunkCache.plan",
        },
    )


def _bounded_candidate(fx: Dict[str, Any]) -> Dict[str, Any]:
    engine = load_optional("tools.data_access.chunk_cache.cache_engine")
    types_mod = load_optional("tools.data_access.chunk_cache")
    n_cached = max(1, len(fx["items"]) // 4)
    if engine is None or types_mod is None:
        policy = _cache_policy(fx["items"], fx["capacity"], n_cached)
        return _meta(
            "bounded_cache_operations",
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
        _plant_cached(cache, fx["dataset_id"], fx["items"], n_cached)
        requested = [(it["bids_path"], 0) for it in fx["items"]]
        plan = cache.plan(fx["dataset_id"], requested)
        policy = {
            "n_requested": len(plan.requested_items),
            "n_cached": len(plan.already_cached_items),
            "n_to_download": len(plan.items_to_download),
            "total_download_bytes": int(plan.total_download_bytes),
            "eviction_required_bytes": int(plan.eviction_required_bytes),
            "paths": sorted(item["bids_path"] if isinstance(item, dict) else item[0] for item in plan.requested_items),
        }
        disk = dir_size_bytes(tmp)
    return _meta(
        "bounded_cache_operations",
        {
            "checksum": _stable_hash(policy),
            "feature_count": policy["n_requested"],
            "disk_bytes": disk,
            "input_size": _input_size(len(fx["items"]), sum(it["size"] for it in fx["items"])),
            "production_module": "tools.data_access.chunk_cache.cache_engine.BoundedChunkCache.plan",
        },
    )


# --------------------------------------------------------------------------- #
# 3. Cache eviction (local planted files, no fetch)
# --------------------------------------------------------------------------- #
def _evict_plan(items: List[Dict[str, Any]], target_bytes: int) -> Dict[str, Any]:
    reclaimed = 0
    evicted = []
    for it in items:
        if reclaimed >= target_bytes:
            break
        reclaimed += int(it["size"])
        evicted.append(it["bids_path"])
    return {"evicted": evicted, "reclaimed": reclaimed, "n_evicted": len(evicted)}


def _eviction_baseline(fx: Dict[str, Any]) -> Dict[str, Any]:
    payload = _evict_plan(fx["items"], int(fx["evict_bytes"]))
    return _meta(
        "cache_eviction",
        {
            "checksum": _stable_hash(payload),
            "feature_count": payload["n_evicted"],
            "disk_bytes": None,
            "input_size": _input_size(len(fx["items"]), sum(it["size"] for it in fx["items"])),
            "production_module": "tools.data_access.chunk_cache.cache_engine.BoundedChunkCache.evict",
        },
    )


def _eviction_candidate(fx: Dict[str, Any]) -> Dict[str, Any]:
    engine = load_optional("tools.data_access.chunk_cache.cache_engine")
    types_mod = load_optional("tools.data_access.chunk_cache")
    if engine is None or types_mod is None:
        payload = _evict_plan(fx["items"], int(fx["evict_bytes"]))
        return _meta(
            "cache_eviction",
            {
                "checksum": _stable_hash(payload),
                "feature_count": payload["n_evicted"],
                "disk_bytes": None,
                "input_size": _input_size(len(fx["items"]), sum(it["size"] for it in fx["items"])),
                "production_module": "tools.data_access.chunk_cache.cache_engine.BoundedChunkCache.evict",
                "production_available": False,
            },
        )
    with tempfile.TemporaryDirectory() as tmp:
        cache = engine.BoundedChunkCache(
            cache_root=tmp,
            max_cache_bytes=sum(int(it["size"]) for it in fx["items"]) + 1024,
            min_free_headroom_bytes=0,
            transfer_adapter=types_mod.MockTransferAdapter(),
        )
        _plant_cached(cache, fx["dataset_id"], fx["items"], len(fx["items"]))
        reclaimed, evicted = cache.evict(int(fx["evict_bytes"]))
        payload = {
            "evicted": [rec.bids_path for rec in evicted],
            "reclaimed": int(reclaimed),
            "n_evicted": len(evicted),
        }
        disk = dir_size_bytes(tmp)
    return _meta(
        "cache_eviction",
        {
            "checksum": _stable_hash(payload),
            "feature_count": payload["n_evicted"],
            "disk_bytes": disk,
            "input_size": _input_size(len(fx["items"]), sum(it["size"] for it in fx["items"])),
            "production_module": "tools.data_access.chunk_cache.cache_engine.BoundedChunkCache.evict",
        },
    )


# --------------------------------------------------------------------------- #
# 4. Manifest recovery (streaming save_manifest / load_manifest)
# --------------------------------------------------------------------------- #
def _manifest_baseline(fx: Dict[str, Any]) -> Dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "manifest.json"
        path.write_text(json.dumps(fx["manifest"], indent=2), encoding="utf-8")
        loaded = json.loads(path.read_text(encoding="utf-8"))
        disk = dir_size_bytes(tmp)
    payload = {
        "subjects": sorted(loaded.get("processed_subjects", {})),
        "failed": sorted(loaded.get("failed_subjects", {})),
    }
    return _meta(
        "manifest_recovery",
        {
            "checksum": _stable_hash(payload),
            "feature_count": len(payload["subjects"]),
            "disk_bytes": disk,
            "input_size": _input_size(fx["n_items"]),
            "production_module": "tools.streaming.base_runner.save_manifest",
        },
    )


def _manifest_candidate(fx: Dict[str, Any]) -> Dict[str, Any]:
    runner = load_optional("tools.streaming.base_runner")
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "manifest.json"
        if runner is None:
            path.write_text(json.dumps(fx["manifest"], indent=2), encoding="utf-8")
            loaded = json.loads(path.read_text(encoding="utf-8"))
            available = False
        else:
            runner.save_manifest(path, fx["manifest"])
            tmp_sib = path.with_suffix(path.suffix + ".tmp")
            tmp_sib.write_text(json.dumps(fx["manifest"], indent=2), encoding="utf-8")
            path.write_text("{truncated", encoding="utf-8")
            loaded = runner.load_manifest(path)
            available = True
        disk = dir_size_bytes(tmp)
    payload = {
        "subjects": sorted(loaded.get("processed_subjects", {})),
        "failed": sorted(loaded.get("failed_subjects", {})),
    }
    return _meta(
        "manifest_recovery",
        {
            "checksum": _stable_hash(payload),
            "feature_count": len(payload["subjects"]),
            "disk_bytes": disk,
            "input_size": _input_size(fx["n_items"]),
            "production_module": "tools.streaming.base_runner.save_manifest",
            "production_available": available,
        },
    )


# --------------------------------------------------------------------------- #
# 5. Artifact scanning
# --------------------------------------------------------------------------- #
def _materialize_run(root: Path, files: List[Dict[str, Any]]) -> None:
    for row in files:
        path = root / row["name"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(row["payload"], sort_keys=True, allow_nan=False), encoding="utf-8")


def _scan_files(root: Path) -> List[Dict[str, Any]]:
    return _inventory(root)


def _scan_baseline(fx: Dict[str, Any]) -> Dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _materialize_run(root, fx["files"])
        entries = _scan_files(root)
        disk = dir_size_bytes(root)
    return _meta(
        "artifact_scanning",
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
        "artifact_scanning",
        {
            "checksum": _stable_hash([(e["relative_path"], e["sha256"], e["size_bytes"]) for e in entries]),
            "feature_count": len(entries),
            "disk_bytes": disk,
            "input_size": _input_size(len(fx["files"])),
            "production_module": "tools.simulation_artifacts.extractor.extract_run",
        },
    )


# --------------------------------------------------------------------------- #
# 6. Literature evidence validation
# --------------------------------------------------------------------------- #
def _literature_state(rec: Dict[str, Any]) -> str:
    ident = (rec.get("identifier") or "").strip()
    if not ident:
        return "rejected_missing_identity"
    if rec.get("identifier_type") == "doi" and not ident.startswith("10."):
        return "rejected_fabricated_identifier"
    if rec.get("publication_type") not in {
        "peer_reviewed_journal_article",
        "conference_paper",
        "preprint",
        "theory_paper",
        "book_chapter",
        "technical_report",
        "other",
        "unknown",
    }:
        return "rejected_unsupported_publication_status"
    if rec.get("review_status") not in {
        "unreviewed",
        "review_required",
        "reviewed_accepted",
        "reviewed_rejected",
        "disputed",
    }:
        return "rejected_unsupported_publication_status"
    return "valid"


def _literature_baseline(fx: Dict[str, Any]) -> Dict[str, Any]:
    states = [(row["source_id"], _literature_state(row)) for row in fx["records"]]
    return _meta(
        "literature_evidence_validation",
        {
            "checksum": _stable_hash(states),
            "feature_count": len(states),
            "disk_bytes": None,
            "input_size": _input_size(len(fx["records"])),
            "production_module": "tools.literature_evidence.validation.validate_record",
        },
    )


def _literature_candidate(fx: Dict[str, Any]) -> Dict[str, Any]:
    models = load_optional("tools.literature_evidence.models")
    validation = load_optional("tools.literature_evidence.validation")
    if models is None or validation is None:
        states = [(row["source_id"], _literature_state(row)) for row in fx["records"]]
        available = False
    else:
        states = []
        for row in fx["records"]:
            record = models.LiteratureRecord(
                source_id=row["source_id"],
                identifier=row["identifier"] or None,
                identifier_type=row["identifier_type"],
                publication_type=row["publication_type"],
                review_status=row["review_status"],
                evidence_class=row["evidence_class"],
            )
            result = validation.validate_record(record)
            states.append((row["source_id"], result.state))
        available = True
    return _meta(
        "literature_evidence_validation",
        {
            "checksum": _stable_hash(states),
            "feature_count": len(states),
            "disk_bytes": None,
            "input_size": _input_size(len(fx["records"])),
            "production_module": "tools.literature_evidence.validation.validate_record",
            "production_available": available,
        },
    )


# --------------------------------------------------------------------------- #
# 7. Research-cycle smoke execution
# --------------------------------------------------------------------------- #
def _smoke_payload_from_ids(scenario_ids: List[str]) -> List[Any]:
    fixtures = load_optional("tools.release_readiness.research_cycle_smoke.fixtures")
    schema = load_optional("tools.release_readiness.research_cycle_smoke.schema")
    if fixtures is None or schema is None:
        return [(name, "unavailable", None) for name in scenario_ids]
    rows = []
    for name in scenario_ids:
        sid = schema.ScenarioId(name)
        stages, bundle, expected = fixtures.build_scenario(sid)
        rows.append((name, fixtures.fixture_checksum(stages, bundle), expected))
    return rows


def _smoke_baseline(fx: Dict[str, Any]) -> Dict[str, Any]:
    rows = _smoke_payload_from_ids(fx["scenario_ids"])
    return _meta(
        "research_cycle_smoke_execution",
        {
            "checksum": _stable_hash(rows),
            "feature_count": len(rows),
            "disk_bytes": None,
            "input_size": _input_size(len(fx["scenario_ids"])),
            "production_module": "tools.release_readiness.research_cycle_smoke.runner.run_smoke_suite",
        },
    )


def _smoke_candidate(fx: Dict[str, Any]) -> Dict[str, Any]:
    runner = load_optional("tools.release_readiness.research_cycle_smoke.runner")
    schema = load_optional("tools.release_readiness.research_cycle_smoke.schema")
    if runner is None or schema is None:
        rows = _smoke_payload_from_ids(fx["scenario_ids"])
        available = False
    else:
        selected = [schema.ScenarioId(name) for name in fx["scenario_ids"]]
        report = runner.run_smoke_suite(selected)
        rows = [
            (item["scenario_id"], result["checksum"], item["expected"])
            for item, result in zip(report["decision_matrix"], report["results"])
        ]
        available = True
    return _meta(
        "research_cycle_smoke_execution",
        {
            "checksum": _stable_hash(rows),
            "feature_count": len(rows),
            "disk_bytes": None,
            "input_size": _input_size(len(fx["scenario_ids"])),
            "production_module": "tools.release_readiness.research_cycle_smoke.runner.run_smoke_suite",
            "production_available": available,
        },
    )


# --------------------------------------------------------------------------- #
# 8. Release-evidence evaluation
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
    "metadata_planning": _spec(
        "metadata_planning", _metadata_baseline, _metadata_candidate, path_family="metadata-planning"
    ),
    "bounded_cache_operations": _spec(
        "bounded_cache_operations",
        _bounded_baseline,
        _bounded_candidate,
        path_family="bounded-cache",
        size=24,
    ),
    "cache_eviction": _spec(
        "cache_eviction", _eviction_baseline, _eviction_candidate, path_family="bounded-cache", size=24
    ),
    "manifest_recovery": _spec(
        "manifest_recovery",
        _manifest_baseline,
        _manifest_candidate,
        path_family="streaming-recovery",
        size=40,
    ),
    "artifact_scanning": _spec(
        "artifact_scanning", _scan_baseline, _scan_candidate, path_family="artifact-lineage"
    ),
    "literature_evidence_validation": _spec(
        "literature_evidence_validation",
        _literature_baseline,
        _literature_candidate,
        path_family="literature-evidence",
        size=32,
    ),
    "research_cycle_smoke_execution": _spec(
        "research_cycle_smoke_execution",
        _smoke_baseline,
        _smoke_candidate,
        path_family="research-cycle",
        size=3,
    ),
    "release_evidence_evaluation": _spec(
        "release_evidence_evaluation",
        _release_baseline,
        _release_candidate,
        path_family="research-cycle",
        size=16,
    ),
}
