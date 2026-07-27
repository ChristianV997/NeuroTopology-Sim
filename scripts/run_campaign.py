"""Run a bounded, reproducible cross-repository research campaign.

The campaign composes existing ScienceR-Dsim and NeuroTopology-Sim entrypoints
in isolated subprocesses.  It never submits Amazon Braket tasks and treats
all local-reference outputs as model-validation evidence only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any


SCIENCE_ROOT = Path(__file__).resolve().parents[1]
NEURO_ROOT = SCIENCE_ROOT.parent / "NeuroTopology-Sim"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _json_dump(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False), encoding="utf-8")
    temporary.replace(path)


def _run(name: str, cwd: Path, args: list[str], timeout_s: int, env: dict[str, str]) -> dict[str, Any]:
    started = time.monotonic()
    command = [sys.executable, *args]
    try:
        completed = subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True,
                                   timeout=timeout_s, check=False)
        status = "completed" if completed.returncode == 0 else "failed"
        error = None if completed.returncode == 0 else (completed.stderr[-4000:] or completed.stdout[-4000:])
    except subprocess.TimeoutExpired as exc:
        status, error = "timeout", str(exc)
        completed = None
    return {"name": name, "status": status, "returncode": None if completed is None else completed.returncode,
            "elapsed_s": time.monotonic() - started, "stdout_tail": "" if completed is None else completed.stdout[-2000:],
            "stderr_tail": "" if completed is None else completed.stderr[-2000:], "error": error}


def build_manifest(output_dir: Path, seed: int, timeout_s: int, *, lane: str = "discovery",
                   shard_index: int = 0, shard_count: int = 1, execution_mode: str = "local_reference_only",
                   max_workers: int = 1) -> dict[str, Any]:
    pdb = SCIENCE_ROOT / "data" / "1jff.pdb"
    awake = NEURO_ROOT / "data" / "ds005620" / "sub-1010_task-awake_acq-EC_eeg.vhdr"
    sedated = NEURO_ROOT / "data" / "ds005620" / "sub-1010_task-sed2_acq-rest_run-1_eeg.vhdr"
    files = [path for path in (pdb, awake, sedated) if path.is_file()]
    return {"schema": "ScienceR-Dsim.ResearchCampaignManifest.v1", "seed": seed,
            "lane": lane, "shard_index": shard_index, "shard_count": shard_count,
            "execution_mode": execution_mode, "braket_submission": False,
            "timeout_s": timeout_s, "science_root": str(SCIENCE_ROOT), "neuro_root": str(NEURO_ROOT),
            "inputs": [{"path": str(path), "sha256": _sha256(path)} for path in files],
            "missing_inputs": [str(path) for path in (pdb, awake, sedated) if not path.is_file()],
            "resource_policy": {"max_workers": max_workers, "omp_threads": "1", "mkl_threads": "1",
                                "memory_limit_mb": 512}}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=SCIENCE_ROOT / "artifacts" / "campaign")
    parser.add_argument("--seed", type=int, default=20260726)
    parser.add_argument("--timeout-s", type=int, default=300)
    parser.add_argument("--skip-eeg", action="store_true")
    parser.add_argument("--skip-quantum", action="store_true")
    parser.add_argument("--lane", choices=["discovery", "replication", "triangulation"], default="discovery")
    parser.add_argument("--shard-index", type=int, default=0)
    parser.add_argument("--shard-count", type=int, default=1)
    parser.add_argument("--execution-mode", choices=["local_reference_only", "ec2_batch"], default="local_reference_only")
    parser.add_argument("--max-workers", type=int, default=1)
    args = parser.parse_args()
    if args.shard_count < 1 or not 0 <= args.shard_index < args.shard_count:
        parser.error("--shard-index must be within --shard-count")
    if args.max_workers < 1:
        parser.error("--max-workers must be positive")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    manifest = build_manifest(args.output_dir, args.seed, args.timeout_s, lane=args.lane,
                              shard_index=args.shard_index, shard_count=args.shard_count,
                              execution_mode=args.execution_mode, max_workers=args.max_workers)
    _json_dump(args.output_dir / "campaign_manifest.json", manifest)
    env = os.environ.copy()
    env.update({"OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1",
                "NUMEXPR_NUM_THREADS": "1", "PYTHONHASHSEED": str(args.seed)})
    results: list[dict[str, Any]] = []
    # Shards vary the discovery coordinates deterministically. The index is
    # part of the manifest, so independent EC2 jobs never look identical.
    discovery = args.lane == "discovery"
    if not args.skip_quantum:
        temperatures = [10, 60, 110, 160, 210, 260, 310] if discovery else [10, 110, 210, 310]
        spacings = [3, 5, 8, 12, 18, 25, 35] if discovery else [5, 10, 15]
        layers = [2, 3, 4] if discovery else [2, 3]
        shard_temperatures = temperatures[args.shard_index::args.shard_count]
        shard_spacings = spacings[args.shard_index::args.shard_count]
        shard_layers = layers[args.shard_index::args.shard_count]
        results.append(_run("pdb_decoherence", SCIENCE_ROOT,
                            ["scripts/run_decoherence_sweep.py", "--pdb", str(SCIENCE_ROOT / "data/1jff.pdb"),
                             "--temperatures", *map(str, shard_temperatures or temperatures[:1]), "--pump-rate", "0",
                             "--output-dir", str(args.output_dir / "pdb_decoherence")], args.timeout_s, env))
        results.append(_run("multi_lattice", SCIENCE_ROOT,
                            ["scripts/run_multi_lattice_coupling.py", "--spacings-nm", *map(str, shard_spacings or spacings[:1]),
                             "--n-layers", "1", "--dielectric-constants", "4", "7", "10", "--dephasing-rates-s", "1e7", "1e8", "1e9",
                             "--pump-orientations", "axial", "lateral", "helical", "--tau-min-s", "1e-15", "--tau-max-s", "1e3",
                             "--workers", str(args.max_workers), "--output-dir", str(args.output_dir / "multi_lattice")], args.timeout_s, env))
        results.append(_run("matrix_free", SCIENCE_ROOT,
                            ["scripts/run_matrix_free_scaling.py", "--n-layers", *map(str, shard_layers or layers[:1]),
                             "--output-dir", str(args.output_dir / "matrix_free")], args.timeout_s, env))
    if not args.skip_eeg:
        awake = NEURO_ROOT / "data/ds005620/sub-1010_task-awake_acq-EC_eeg.vhdr"
        sedated = NEURO_ROOT / "data/ds005620/sub-1010_task-sed2_acq-rest_run-1_eeg.vhdr"
        if awake.is_file() and sedated.is_file():
            results.append(_run("eeg_topology", NEURO_ROOT,
                                ["scripts/run_eeg_topology_analysis.py", "--awake-file", str(awake),
                                 "--sedated-file", str(sedated), "--max-windows", "4", "--chunk-samples", "500",
                                 # Absolute path is required because this subprocess runs from the sibling repo.
                                 "--output-dir", str((SCIENCE_ROOT / args.output_dir / "eeg_topology").resolve())], args.timeout_s, env))
        else:
            results.append({"name": "eeg_topology", "status": "skipped_missing_input", "error": "paired local EEG headers unavailable"})
    payload = {"schema": "ScienceR-Dsim.ResearchCampaignResult.v1", "manifest": manifest, "steps": results,
               "scientific_note": "These are bounded local-reference computations. Braket was not submitted; no result is QPU evidence."}
    _json_dump(args.output_dir / "campaign_result.json", payload)
    print(json.dumps({"output": str(args.output_dir), "steps": results}, sort_keys=True))
    return 0 if all(step["status"] in {"completed", "skipped_missing_input"} for step in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
