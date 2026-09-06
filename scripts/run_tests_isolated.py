"""Run tests in bounded fresh Python processes.

Each batch gets a fresh interpreter so native scientific heaps are released.
Every batch also writes a machine-readable result and separate stdout/stderr
logs, including when a worker times out.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Iterator, Sequence


# Native extensions, plotting, or dense matrix/TDA paths are singleton batches.
# This bounds memory without weakening or replacing scientific assertions.
HEAVY_TEST_FILES = frozenset(
    {
        "test_anesthesia_pipeline.py",
        "test_connectivity_topology.py",
        "test_cross_modal_fusion.py",
        "test_decoherence_sweep.py",
        "test_fmri_tda_pipeline.py",
        "test_mne_bids_feature_recipe_features.py",
        "test_multi_lattice_dashboard.py",
        "test_non_markovian_bath.py",
        "test_open_quantum.py",
        "test_preprocessing.py",
        "test_preprocessing_artifact_rejection.py",
        "test_quantum_trajectories.py",
        "test_spectral_tda.py",
        "test_speculative_non_hermitian.py",
        "test_t_real_cli_stats_wiring.py",
        "test_topology.py",
        "test_tryptophan_lindblad.py",
        "test_unified_quantum_lattice.py",
    }
)
_WORKER_GRACE_S = 30


def discover(root: Path) -> list[Path]:
    return sorted(
        (path for path in root.rglob("test_*.py") if "apps/awareness_studio" not in path.as_posix()),
        key=lambda path: path.as_posix(),
    )


def is_heavy_test(path: Path) -> bool:
    return path.name in HEAVY_TEST_FILES


def iter_batches(files: Sequence[Path], batch_size: int) -> Iterator[list[Path]]:
    """Yield deterministic batches while isolating known heavy files."""
    batch: list[Path] = []
    for path in files:
        if is_heavy_test(path):
            if batch:
                yield batch
                batch = []
            yield [path]
            continue
        batch.append(path)
        if len(batch) == batch_size:
            yield batch
            batch = []
    if batch:
        yield batch


def _pytest_timeout_available() -> bool:
    try:
        return importlib.util.find_spec("pytest_timeout") is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


def _write_summary(path: Path, summary: dict) -> None:
    path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _terminate_worker(worker: subprocess.Popen) -> None:
    """Terminate a timed-out worker and its descendants on Windows/POSIX."""
    if worker.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(worker.pid), "/T", "/F"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
        )
    else:
        try:
            os.killpg(worker.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
        try:
            worker.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(worker.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
    if worker.poll() is None:
        worker.kill()
        worker.wait()


def run_batches(
    files: Sequence[Path],
    batch_size: int,
    timeout_s: int,
    report_dir: Path | None = None,
    repo_root: Path | None = None,
) -> int:
    if batch_size < 1 or timeout_s < 1:
        raise ValueError("batch_size and timeout_s must be positive")
    if not _pytest_timeout_available():
        raise RuntimeError("pytest-timeout is required for bounded isolated execution")

    root = Path(repo_root or Path(__file__).resolve().parents[1]).resolve()
    report_root = Path(report_dir or root / "test-results" / "isolated")
    report_root.mkdir(parents=True, exist_ok=True)
    batches = list(iter_batches(files, batch_size))
    summary_path = report_root / "batch_summary.json"
    summary: dict = {
        "schema_version": "isolated_test_summary_v1",
        "batch_size": batch_size,
        "timeout_s": timeout_s,
        "worker_grace_s": _WORKER_GRACE_S,
        "batches": [],
    }
    _write_summary(summary_path, summary)
    first_failure: int | None = None
    timed_out_any = False

    for number, batch in enumerate(batches, start=1):
        command = [
            sys.executable, "-m", "pytest", "-q", "--timeout", str(timeout_s),
            *[str(path) for path in batch],
        ]
        print(
            f"[isolated {number}/{len(batches)}] {len(batch)} files: "
            f"{', '.join(path.as_posix() for path in batch)}",
            flush=True,
        )
        env = os.environ.copy()
        for variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
            env[variable] = "1"
        env["MPLBACKEND"] = "Agg"
        stdout_path = report_root / f"batch_{number:03d}.stdout.log"
        stderr_path = report_root / f"batch_{number:03d}.stderr.log"
        popen_kwargs: dict = {"cwd": str(root), "env": env}
        if os.name == "nt":
            popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            popen_kwargs["start_new_session"] = True

        started = time.monotonic()
        returncode = 1
        timed_out = False
        try:
            with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
                worker = subprocess.Popen(command, stdout=stdout, stderr=stderr, **popen_kwargs)
                try:
                    returncode = worker.wait(timeout=timeout_s + _WORKER_GRACE_S)
                except subprocess.TimeoutExpired:
                    timed_out = True
                    returncode = 124
                    _terminate_worker(worker)
        except OSError as exc:
            stderr_path.write_text(f"isolated worker could not start: {exc}\n", encoding="utf-8")

        duration_s = round(time.monotonic() - started, 6)
        entry = {
            "batch_number": number,
            "test_files": [path.as_posix() for path in batch],
            "duration_s": duration_s,
            "exit_code": returncode,
            "timed_out": timed_out,
            "timeout_status": "timeout" if timed_out else "completed",
            "stdout_path": stdout_path.as_posix(),
            "stderr_path": stderr_path.as_posix(),
        }
        summary["batches"].append(entry)
        _write_summary(summary_path, summary)
        if timed_out:
            timed_out_any = True
            print(f"[isolated] batch {number} exceeded {timeout_s + _WORKER_GRACE_S}s; continuing", flush=True)
        elif returncode != 0:
            first_failure = first_failure if first_failure is not None else returncode
            print(f"[isolated] batch {number} failed with exit code {returncode}; continuing", flush=True)

    summary["completed"] = len(summary["batches"]) == len(batches)
    summary["exit_code"] = 124 if timed_out_any else (first_failure or 0)
    _write_summary(summary_path, summary)
    print(f"[isolated] completed {len(files)} test files in {len(batches)} fresh processes", flush=True)
    return summary["exit_code"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("tests"))
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--timeout-s", type=int, default=300)
    parser.add_argument("--report-dir", type=Path, default=Path("test-results/isolated"))
    parser.add_argument("files", nargs="*", type=Path, help="explicit test files; defaults to discovery")
    args = parser.parse_args(argv)
    files = args.files or discover(args.root)
    if not files:
        parser.error("no test files found")
    return run_batches(files, args.batch_size, args.timeout_s, report_dir=args.report_dir)


if __name__ == "__main__":
    raise SystemExit(main())
