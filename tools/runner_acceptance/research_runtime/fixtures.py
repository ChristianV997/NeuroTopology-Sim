"""Black-box fixtures and production integration probes for Batch 1 infrastructure."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Dict, List, Optional, Tuple

from .contracts import (
    AtomicWriteSpec,
    BoundedChunkCachePlan,
    CacheEvictionPlan,
    ResumableTransferMetadata,
    SimulationCheckpointSpec,
)


def probe_production_chunk_cache() -> Tuple[bool, str]:
    """Probes whether Batch 1 chunk cache implementation exists on Python path."""
    candidate_modules = [
        "tools.openneuro_chunk_cache",
        "shared.openneuro_chunk_cache",
        "tools.chunk_cache",
        "shared.chunk_cache",
    ]
    for mod in candidate_modules:
        try:
            __import__(mod)
            return (True, f"Found production module: {mod}")
        except ModuleNotFoundError:
            continue
        except Exception as exc:
            return (False, f"Error importing {mod}: {exc}")
    return (False, "Batch 1 bounded chunk-cache is not yet merged to origin/main; integration test is marked PENDING.")


def probe_production_simulation_runner() -> Tuple[bool, str]:
    """Probes whether Batch 1 reliable simulation campaign runner exists on Python path."""
    candidate_modules = [
        "tools.simulation_campaign",
        "shared.simulation_campaign",
        "tools.simulation_runner",
        "shared.simulation_runner",
    ]
    for mod in candidate_modules:
        try:
            __import__(mod)
            return (True, f"Found production module: {mod}")
        except ModuleNotFoundError:
            continue
        except Exception as exc:
            return (False, f"Error importing {mod}: {exc}")
    return (False, "Batch 1 simulation campaign runner is not yet merged to origin/main; integration test is marked PENDING.")


def build_chunk_cache_plan_fixture(
    dataset_id: str = "ds005620",
    total_bytes: int = 15 * 1024 * 1024,  # 15 MiB
    chunk_size_bytes: int = 2 * 1024 * 1024,  # 2 MiB
    budget_bytes: int = 8 * 1024 * 1024,  # 8 MiB max
) -> BoundedChunkCachePlan:
    """Creates a deterministic black-box chunk cache plan fixture."""
    plan = BoundedChunkCachePlan(
        dataset_id=dataset_id,
        total_bytes=total_bytes,
        chunk_size_bytes=chunk_size_bytes,
        max_cache_budget_bytes=budget_bytes,
        eviction_policy="LRU",
    )

    planned_chunks: List[Dict[str, Any]] = []
    curr_offset = 0
    idx = 0
    while curr_offset < total_bytes:
        sz = min(chunk_size_bytes, total_bytes - curr_offset)
        planned_chunks.append({
            "chunk_index": idx,
            "byte_offset": curr_offset,
            "byte_length": sz,
            "sha256": hashlib.sha256(f"chunk_{idx}_{curr_offset}_{sz}".encode("utf-8")).hexdigest(),
        })
        curr_offset += sz
        idx += 1

    plan.planned_chunks = planned_chunks
    plan.chunk_count = len(planned_chunks)
    return plan


def simulate_resumable_transfer_fixture(
    target_dir: Path,
    num_chunks: int = 4,
    chunk_size: int = 1024,
) -> ResumableTransferMetadata:
    """Simulates a multi-chunk transfer with resumable state persistence."""
    target_dir.mkdir(parents=True, exist_ok=True)
    dst_file = target_dir / "transferred_artifact.bin"
    total_bytes = num_chunks * chunk_size

    # Synthesize deterministic chunk data
    chunk_data_list = [
        f"CHUNK_PAYLOAD_{i:04d}_".encode("ascii") * (chunk_size // 19 + 1)
        for i in range(num_chunks)
    ]
    # Trim each chunk to exact chunk_size
    chunk_data_list = [b[:chunk_size] for b in chunk_data_list]

    full_payload = b"".join(chunk_data_list)
    full_sha = hashlib.sha256(full_payload).hexdigest()

    # Write first 2 chunks, simulating interrupted transfer
    part_file = target_dir / "transferred_artifact.bin.part"
    with open(part_file, "wb") as fp:
        fp.write(chunk_data_list[0])
        fp.write(chunk_data_list[1])

    meta = ResumableTransferMetadata(
        transfer_id="xfer-batch1-001",
        source_uri="openneuro://ds005620/sub-01/eeg/data.bin",
        destination_path=str(dst_file),
        total_expected_bytes=total_bytes,
        transferred_bytes=chunk_size * 2,
        chunk_count=num_chunks,
        completed_chunks=[0, 1],
        active_chunk_index=2,
        resume_token=hashlib.sha256(b"token_chunk_2").hexdigest(),
        checksum_sha256=full_sha,
        is_resumable=True,
        is_complete=False,
    )

    # Now resume and complete remaining chunks
    with open(part_file, "ab") as fp:
        for idx in range(2, num_chunks):
            fp.write(chunk_data_list[idx])
            meta.completed_chunks.append(idx)
            meta.transferred_bytes += len(chunk_data_list[idx])

    # Atomic rename part to final
    os.replace(part_file, dst_file)
    meta.is_complete = True
    meta.active_chunk_index = None

    return meta


def simulate_cache_eviction_fixture(
    cache_dir: Path,
    file_sizes_bytes: List[int],
    budget_limit_bytes: int,
) -> CacheEvictionPlan:
    """Simulates LRU cache eviction when total size exceeds budget limit."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    created_files: List[Tuple[str, int, float]] = []

    for idx, sz in enumerate(file_sizes_bytes):
        f = cache_dir / f"cache_entry_{idx:03d}.dat"
        f.write_bytes(b"X" * sz)
        # Stagger access/mtime to simulate access sequence
        mtime = 1000.0 + idx * 10.0
        os.utime(f, (mtime, mtime))
        created_files.append((f.name, sz, mtime))

    total_sz = sum(sz for _, sz, _ in created_files)
    target_freed = max(0, total_sz - budget_limit_bytes)

    # LRU: sort by mtime ascending
    created_files.sort(key=lambda x: x[2])
    freed = 0
    evicted: List[str] = []
    retained: List[str] = []

    for name, sz, _ in created_files:
        p = cache_dir / name
        if freed < target_freed:
            evicted.append(name)
            freed += sz
            if p.exists():
                p.unlink()
        else:
            retained.append(name)

    resulting_sz = total_sz - freed

    return CacheEvictionPlan(
        cache_root=str(cache_dir),
        current_size_bytes=total_sz,
        budget_limit_bytes=budget_limit_bytes,
        target_freed_bytes=target_freed,
        evicted_keys=evicted,
        retained_keys=retained,
        resulting_size_bytes=resulting_sz,
    )


def execute_atomic_write_fixture(
    destination_file: Path,
    payload: bytes,
) -> AtomicWriteSpec:
    """Executes an atomic write using staging file and os.replace."""
    destination_file.parent.mkdir(parents=True, exist_ok=True)
    temp_file = destination_file.parent / f".tmp_{destination_file.name}_{os.getpid()}"

    spec = AtomicWriteSpec(
        destination_path=str(destination_file),
        temp_prefix=".tmp_",
        require_sync=True,
        strategy="os.replace",
    )

    with open(temp_file, "wb") as fp:
        fp.write(payload)
        fp.flush()
        os.fsync(fp.fileno())

    # Atomically replace destination
    os.replace(temp_file, destination_file)

    spec.replace_success = True
    spec.written_bytes = len(payload)
    spec.checksum_sha256 = hashlib.sha256(payload).hexdigest()
    return spec


def build_simulation_checkpoint_fixture(
    checkpoint_dir: Path,
    campaign_id: str = "cmp-001",
    run_id: str = "run-042",
    step_index: int = 50,
    total_steps: int = 100,
) -> SimulationCheckpointSpec:
    """Builds a verified simulation checkpoint record with state hash."""
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    ckpt_file = checkpoint_dir / f"{campaign_id}_{run_id}_step_{step_index:05d}.chk"

    rng_state = f"MersenneTwister_seed_1337_step_{step_index}".encode("utf-8")
    state_payload = json.dumps({
        "step": step_index,
        "energy": 0.421,
        "phase_winding": [1, -1, 0],
        "active_oscillators": 64,
    }, sort_keys=True).encode("utf-8")

    ckpt_content = b"SIM_CHK_V1\n" + rng_state + b"\n" + state_payload
    ckpt_file.write_bytes(ckpt_content)

    return SimulationCheckpointSpec(
        campaign_id=campaign_id,
        run_id=run_id,
        step_index=step_index,
        total_steps=total_steps,
        rng_seed=1337,
        rng_state_hash=hashlib.sha256(rng_state).hexdigest(),
        state_payload_hash=hashlib.sha256(state_payload).hexdigest(),
        checkpoint_file=str(ckpt_file),
        is_recoverable=True,
    )
