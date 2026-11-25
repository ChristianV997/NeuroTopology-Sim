"""Deterministic synthetic fixtures for pipeline-efficiency targets.

Local metadata only. No OpenNeuro/AWS/DANDI/remote access. Seeded and
byte-reproducible for a given (target, seed, size).
"""
from __future__ import annotations

import hashlib
import json
import random
from typing import Any, Dict


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _norm_record(*, seed: int, index: int, **overrides: Any) -> Dict[str, Any]:
    rec = {
        "schema_version": "1.0",
        "benchmark_id": "pipeline-efficiency-synth",
        "source_commit": "local-synth",
        "branch": "local",
        "host": "host-a",
        "platform": "linux",
        "python_version": "3.12.3",
        "backend": "numpy",
        "input_shape": {"channels": 8, "samples": 64 + index, "dtype": "float64"},
        "chunk_size": 16,
        "repetitions": 3,
        "checksum": 1.0 + (index % 7) * 0.01,
        "correctness_status": "ok",
        "runtime_s": 0.050 + (index % 5) * 0.001,
        "wall_best_s": 0.048 + (index % 5) * 0.001,
        "wall_mean_s": 0.050 + (index % 5) * 0.001,
        "tracemalloc_peak_bytes": 8_000_000 + index * 10,
        "child_rss_bytes": 210_000_000,
        "parent_sampled_rss_bytes": 212_000_000,
        "timeout_status": False,
        "process_exit_status": 0,
        "optional_dependency_state": None,
        "evidence_class": "performance_only",
        "synthetic": True,
        "raw_outcome": "pass",
        "seed": seed,
    }
    rec.update(overrides)
    return rec


def make_fixture(target: str, seed: int = 0, size: int = 64) -> Dict[str, Any]:
    """Return a deterministic fixture dict for ``target``."""
    if size < 1:
        raise ValueError("size must be >= 1")
    rng = random.Random(seed)

    if target == "manifest_planning":
        artifacts = []
        for i in range(size):
            payload = f"{seed}:artifact:{i}:{rng.randrange(10_000)}".encode("utf-8")
            artifacts.append(
                {
                    "path": f"artifacts/dir{i % 8}/file_{i:06d}.bin",
                    "content": payload,
                    "size": len(payload),
                }
            )
        return {"artifacts": artifacts, "run_id": f"synth-{seed:04d}", "n_items": size}

    if target == "bounded_cache_planning":
        items = []
        for i in range(size):
            sub = f"sub-{i:04d}"
            items.append(
                {
                    "id": f"c{i:06d}",
                    "bids_path": f"{sub}/eeg/{sub}_task-rest_eeg.edf",
                    "size": 512 + (i * 101) % 8192,
                    "last_access": rng.randrange(0, 1_000_000),
                }
            )
        total = sum(it["size"] for it in items)
        return {
            "dataset_id": "ds000000",
            "items": items,
            "capacity": max(total // 2, 1),
            "n_items": size,
        }

    if target in ("artifact_manifest_scanning", "duplicate_detection"):
        files = []
        for i in range(size):
            body = {
                "idx": i,
                "seed": seed,
                "token": _sha(f"{seed}:scan:{i}")[:16],
            }
            name = f"extra_{i:04d}.json"
            if i == 0:
                name = "RunRecord.json"
                body = {
                    "run_id": f"run-{seed:04d}",
                    "run_kind": "synthetic_benchmark",
                    "created_at": "2026-09-11T00:00:00Z",
                    "source": "local synthetic fixture",
                    "data_mode": "synthetic",
                    "synthetic": True,
                    "claim_scope": "computational_artifact",
                    "evidence_class": "performance_only",
                    "input": {"seed": seed, "size": size},
                    "dependencies": {"python": "3.x"},
                }
            elif i == 1:
                name = "summary.json"
                body = {"status": "complete", "parent": "RunRecord.json", "n": size}
            elif i == 2:
                name = "metrics.json"
                body = {"loss": 0.25, "finite": True}
            elif i % 5 == 0 and i > 2:
                body = files[i - 5]["payload"]
            files.append({"name": name, "payload": body})
        return {"files": files, "n_items": size, "include_duplicate": True}

    if target == "evidence_graph_projection":
        n_nodes = max(4, size // 2)
        nodes = []
        for i in range(n_nodes):
            parent = None if i == 0 else (i - 1 if i % 4 != 0 else None)
            nodes.append(
                {
                    "number": 1000 + i,
                    "branch": f"cursor/synth-{i:03d}",
                    "base_branch": "main" if parent is None else f"cursor/synth-{parent:03d}",
                    "parent_pr": (1000 + parent) if parent is not None else None,
                    "merge_status": "open" if i % 7 != 0 else "merged",
                    "status_category": "READY",
                    "is_draft": False,
                    "is_ancestor_of_target": False,
                    "mergeable": True,
                    "ci_status": "passed" if i % 11 != 0 else "failed",
                    "superseded_by_pr": None,
                    "duplicate_of_pr": None,
                    "depends_on": [1000 + parent] if parent is not None else [],
                }
            )
        return {"nodes": nodes, "n_items": n_nodes}

    if target == "release_evidence_evaluation":
        pairs = []
        for i in range(size):
            base = _norm_record(seed=seed, index=i)
            cand = _norm_record(seed=seed, index=i, runtime_s=base["runtime_s"] + 0.001)
            if i % 11 == 0:
                cand = _norm_record(seed=seed, index=i, timeout_status=True, raw_outcome="timeout", process_exit_status=124)
            elif i % 13 == 0:
                cand = _norm_record(seed=seed, index=i, checksum=9.999)
            pairs.append({"baseline": base, "candidate": cand})
        cycle = {
            "bundle_schema": "research_cycle_release_bundle.v1",
            "cycle_id": f"cycle-synth-{seed:04d}",
            "source_manifest_present": True,
            "source_manifest_path": "manifest.json",
            "checksums_present": True,
            "checksum_entries": [{"id": "src", "sha256": _sha(f"{seed}:src")[:16]}],
            "configuration_locked": True,
            "code_commit": "local-synth",
            "seed": seed,
            "input_provenance_complete": True,
            "input_provenance_missing": [],
            "outputs_finite": True,
            "non_finite_metric_paths": [],
            "metrics": {"score": 1.25},
            "work_units": [
                {
                    "id": "u1",
                    "status": "completed",
                    "partial": False,
                    "output_checksums": ["out1"],
                    "input_checksums": ["in1"],
                }
            ],
            "all_work_units_terminal": True,
            "partial_runs_explicitly_marked": True,
            "artifact_lineage_complete": True,
            "artifact_lineage_missing": [],
            "validation_report_present": True,
            "validation_status": "ok",
            "null_metadata_applicable": False,
            "null_metadata_present": None,
            "multiplicity_metadata_applicable": False,
            "multiplicity_metadata_present": None,
            "forecasting_applicable": False,
            "resource_budgets_respected": True,
            "full_dataset_download": False,
            "network_policy_recorded": True,
            "network_policy_violated": False,
            "evidence_classes": ["performance_only"],
            "evidence_classes_consistent": True,
            "synthetic_only": True,
            "proxy_only": False,
            "empirical_present": False,
            "report_metadata_text": "engineering operational summary",
            "infrastructure_blocked": False,
            "comparable": True,
            "comparability_notes": [],
        }
        return {"pairs": pairs, "cycle": cycle, "n_items": size}

    if target == "checkpoint_recovery_planning":
        configs = [{"id": f"sim{i:05d}", "n_steps": 10 + (i % 50), "grid_n": 8 + (i % 24)} for i in range(size)]
        completed = [c["id"] for i, c in enumerate(configs) if i % 3 == 0]
        cfg = {
            "chunk_size": 16,
            "overlap": 0,
            "dtype": "float64",
            "n_channels": 4,
            "n_samples": max(32, size * 4),
            "backend": "numpy",
            "check_finite": True,
        }
        return {
            "configs": configs,
            "completed": completed,
            "checkpoint_interval": 16,
            "config": cfg,
            "n_items": size,
        }

    if target == "simulation_runner_overhead":
        payload = {
            "checksum": float(size),
            "correctness_ok": True,
            "tracemalloc_peak_bytes": 1024,
            "peak_rss_bytes": 1024,
            "evidence_class": "performance_only",
            "synthetic": True,
        }
        return {
            "child_payload": payload,
            "timeout_s": 8.0,
            "n_items": 1,
            "input_bytes": len(json.dumps(payload, sort_keys=True)),
        }

    raise ValueError(f"unknown target: {target!r}")
