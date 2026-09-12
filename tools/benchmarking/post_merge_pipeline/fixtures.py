"""Deterministic synthetic fixtures for post-merge pipeline targets.

Local metadata only. No OpenNeuro/AWS/DANDI/remote access.
"""
from __future__ import annotations

import hashlib
import json
import random
from typing import Any, Dict, List


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _norm_record(*, seed: int, index: int, **overrides: Any) -> Dict[str, Any]:
    rec = {
        "schema_version": "1.0",
        "benchmark_id": "post-merge-pipeline-synth",
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


def _cache_items(seed: int, size: int) -> List[Dict[str, Any]]:
    rng = random.Random(seed)
    items = []
    for i in range(size):
        sub = f"sub-{i:04d}"
        items.append(
            {
                "id": f"c{i:06d}",
                "bids_path": f"{sub}/eeg/{sub}_task-rest_eeg.edf",
                "size": 256 + (i * 97) % 2048,
                "last_access": rng.randrange(0, 1_000_000),
            }
        )
    return items


def make_fixture(target: str, seed: int = 0, size: int = 64) -> Dict[str, Any]:
    if size < 1:
        raise ValueError("size must be >= 1")
    rng = random.Random(seed)

    if target == "metadata_planning":
        files = []
        for i in range(size):
            if i % 7 == 0:
                body = "import json\n\ndef plan_metadata(items):\n    return sorted(items)\n"
            elif i % 7 == 1:
                body = (
                    "def list_local_prefixes(names):\n"
                    "    return [n for n in names if n.startswith('sub-')]\n"
                )
            else:
                body = f"# synthetic module {seed}:{i}\nVALUE = {i}\n"
            files.append({"path": f"pkg/mod_{i:04d}.py", "content": body})
        return {"files": files, "n_items": size}

    if target in ("bounded_cache_operations", "cache_eviction"):
        items = _cache_items(seed, size)
        total = sum(it["size"] for it in items)
        return {
            "dataset_id": "ds000000",
            "items": items,
            "capacity": max(total // 2, 1),
            "evict_bytes": max(total // 3, 1),
            "n_items": size,
        }

    if target == "manifest_recovery":
        processed = {f"sub-{i:04d}": {"n_rows": i, "ok": True} for i in range(size)}
        failed = {f"sub-{size:04d}": "transient"} if size > 2 else {}
        return {
            "manifest": {"processed_subjects": processed, "failed_subjects": failed},
            "n_items": size,
        }

    if target == "artifact_scanning":
        files = []
        for i in range(size):
            body: Dict[str, Any] = {"idx": i, "seed": seed, "token": _sha(f"{seed}:scan:{i}")[:16]}
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
        return {"files": files, "n_items": size}

    if target == "literature_evidence_validation":
        records = []
        for i in range(size):
            kind = i % 5
            if kind == 0:
                rec = {
                    "source_id": f"src-{i:04d}",
                    "identifier": "",
                    "identifier_type": "doi",
                    "publication_type": "preprint",
                    "review_status": "unreviewed",
                    "evidence_class": "review_required",
                    "expected_state": "rejected_missing_identity",
                }
            elif kind == 1:
                rec = {
                    "source_id": f"src-{i:04d}",
                    "identifier": "not-a-doi",
                    "identifier_type": "doi",
                    "publication_type": "preprint",
                    "review_status": "unreviewed",
                    "evidence_class": "review_required",
                    "expected_state": "rejected_fabricated_identifier",
                }
            elif kind == 2:
                rec = {
                    "source_id": f"src-{i:04d}",
                    "identifier": f"10.1234/synth.{seed}.{i}",
                    "identifier_type": "doi",
                    "publication_type": "not_a_type",
                    "review_status": "unreviewed",
                    "evidence_class": "review_required",
                    "expected_state": "rejected_unsupported_publication_status",
                }
            else:
                rec = {
                    "source_id": f"src-{i:04d}",
                    "identifier": f"10.1234/synth.{seed}.{i}",
                    "identifier_type": "doi",
                    "publication_type": "preprint",
                    "review_status": "unreviewed",
                    "evidence_class": "review_required",
                    "expected_state": "valid",
                }
            records.append(rec)
        return {"records": records, "n_items": size}

    if target == "research_cycle_smoke_execution":
        names = [
            "complete_valid_engineering",
            "synthetic_only",
            "timeout",
            "incomplete_source",
        ]
        n = max(1, min(size, len(names)))
        return {"scenario_ids": names[:n], "n_items": n}

    if target == "release_evidence_evaluation":
        pairs = []
        for i in range(size):
            base = _norm_record(seed=seed, index=i)
            cand = _norm_record(seed=seed, index=i, runtime_s=base["runtime_s"] + 0.001)
            if i % 11 == 0:
                cand = _norm_record(
                    seed=seed, index=i, timeout_status=True, raw_outcome="timeout", process_exit_status=124
                )
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

    raise ValueError(f"unknown target: {target!r}")
