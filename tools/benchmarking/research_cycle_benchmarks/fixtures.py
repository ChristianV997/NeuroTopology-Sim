"""Deterministic, synthetic fixtures for the research-cycle benchmark targets.

Pure stdlib and fully seeded, so every fixture is byte-reproducible for a given
(target, seed, size). These are synthetic performance fixtures only -- they carry
no scientific meaning and produce no scientific evidence.
"""
from __future__ import annotations

import hashlib
import random
from typing import Any, Dict


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def make_fixture(target: str, seed: int = 0, size: int = 256) -> Dict[str, Any]:
    """Return a deterministic fixture dict for ``target``."""
    if size < 1:
        raise ValueError("size must be >= 1")
    rng = random.Random(seed)

    if target == "ledger_append_export":
        kinds = ["run", "claim", "artifact", "note"]
        entries = [
            {
                "seq": i,
                "kind": kinds[i % len(kinds)],
                "run_id": f"run-{rng.randrange(10_000):05d}",
                "payload_hash": _sha(f"{seed}:{i}:{rng.random()}")[:32],
                "ts": 1_700_000_000 + i,
            }
            for i in range(size)
        ]
        return {"entries": entries}

    if target in ("artifact_manifest_scan", "duplicate_artifact_detection"):
        # Deterministic manifest; ~1 in 5 artifacts duplicates an earlier sha.
        artifacts = []
        shas = []
        for i in range(size):
            if shas and i % 5 == 0:
                sha = shas[rng.randrange(len(shas))]
            else:
                sha = _sha(f"{seed}:artifact:{i}")[:40]
                shas.append(sha)
            artifacts.append({
                "path": f"artifacts/dir{i % 8}/file_{i:06d}.bin",
                "size": 1024 + (i * 37) % 65536,
                "sha": sha,
            })
        return {"artifacts": artifacts}

    if target == "evidence_graph_projection":
        n_nodes = max(3, size // 4)
        nodes = [f"n{i}" for i in range(n_nodes)]
        n_edges = size
        edges = []
        for _ in range(n_edges):
            u = rng.randrange(n_nodes)
            v = rng.randrange(n_nodes)
            if u != v:
                edges.append((f"n{u}", f"n{v}"))
        return {"nodes": nodes, "edges": edges}

    if target == "research_plan_audit":
        claim_types = ["M", "K", "C"]
        tasks = []
        for i in range(size):
            ct = claim_types[i % 3]
            tasks.append({
                "id": f"HYP-{i:05d}",
                "claim_type": ct,
                "has_discriminator": (i % 4 != 0),
                "controls": rng.randrange(0, 3),
                "readouts": rng.randrange(0, 3),
            })
        return {"tasks": tasks}

    if target == "bounded_cache_planning":
        items = [
            {"id": f"c{i:06d}", "size": 512 + (i * 101) % 8192,
             "last_access": rng.randrange(0, 1_000_000)}
            for i in range(size)
        ]
        total = sum(it["size"] for it in items)
        return {"items": items, "capacity": total // 2}

    if target == "simulation_campaign_manifest_planning":
        configs = [
            {"id": f"sim{i:05d}", "n_steps": 10 + (i % 50), "grid_n": 8 + (i % 24)}
            for i in range(size)
        ]
        total_work = sum(c["n_steps"] * c["grid_n"] for c in configs)
        return {"configs": configs, "work_budget": total_work // 2, "chunk_size": 8}

    if target == "checkpoint_recovery_planning":
        configs = [{"id": f"sim{i:05d}", "n_steps": 10 + (i % 50)} for i in range(size)]
        completed = {c["id"] for i, c in enumerate(configs) if i % 3 == 0}
        return {"configs": configs, "completed": sorted(completed), "checkpoint_interval": 16}

    raise ValueError(f"unknown target: {target!r}")
