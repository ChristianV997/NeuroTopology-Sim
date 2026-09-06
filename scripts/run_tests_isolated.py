"""Run the repository test suite in bounded fresh Python processes.

Features:
- Deterministic, lexicographical test file discovery and ordering.
- Fresh subprocess per batch to release native allocations (PyTorch/MNE heaps).
- Hard process-tree timeout termination (Windows and POSIX).
- Explicit thread pool bounding (OMP, OPENBLAS, MKL, NUMEXPR capped to 1).
- Isolated temporary directory per batch (--basetemp).
- Structured JSON telemetry reports with per-batch duration, memory, and tracebacks.
- Graceful detection of pytest-timeout availability.
- Profile-aware and marker-aware execution.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import signal
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Sequence


# Keep known native/plotting-heavy tests in singleton workers. This bounds
# memory without weakening or replacing their scientific assertions.
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


def discover(root: Path) -> List[Path]:
    """Discover all test_*.py files, excluding independently managed subprojects.

    Files are sorted deterministically by POSIX relative path to guarantee identical
    batching order across all operating systems.
    """
    root_resolved = root.resolve()
    candidates = [
        path
        for path in root_resolved.rglob("test_*.py")
        if "apps/awareness_studio" not in path.as_posix()
    ]
    return sorted(candidates, key=lambda p: p.relative_to(root_resolved).as_posix())


def is_heavy_test(path: Path) -> bool:
    return path.name in HEAVY_TEST_FILES


def iter_batches(files: Sequence[Path], batch_size: int) -> Iterator[List[Path]]:
    """Yield deterministic batches while isolating known heavy files."""
    batch: List[Path] = []
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


def _probe_pytest_timeout() -> bool:
    """Check if the current Python environment has pytest-timeout installed."""
    try:
        res = subprocess.run(
            [sys.executable, "-m", "pytest", "--help"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            timeout=10,
        )
        return "--timeout=" in res.stdout or "--timeout" in res.stdout
    except Exception:
        return False


def _pytest_timeout_available() -> bool:
    """Compatibility name used by the CI contract tests."""
    try:
        return importlib.util.find_spec("pytest_timeout") is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


def _terminate_process_tree(proc: subprocess.Popen) -> None:
    """Forcefully terminate a process and all of its spawned children."""
    pid = proc.pid
    if os.name == "nt":
        # Windows: taskkill /F /T kills process tree reliably
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=5,
            )
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
    else:
        # POSIX: kill process group or kill process directly
        try:
            import signal
            os.killpg(os.getpgid(pid), signal.SIGKILL)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass


def _terminate_worker(worker: subprocess.Popen) -> None:
    """Compatibility name used by the bounded-worker regression tests."""
    _terminate_process_tree(worker)


def _measure_peak_rss(proc: subprocess.Popen, timeout_s: float) -> tuple[int, Optional[float]]:
    """Wait for process completion while monitoring peak RSS if psutil is available."""
    try:
        import psutil
        try:
            p = psutil.Process(proc.pid)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return proc.wait(timeout=timeout_s), None
        peak_bytes = 0
        start_time = time.monotonic()
        while True:
            ret = proc.poll()
            if ret is not None:
                return ret, (peak_bytes / (1024 * 1024)) if peak_bytes > 0 else None
            try:
                mem = p.memory_info().rss
                for child in p.children(recursive=True):
                    try:
                        mem += child.memory_info().rss
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
                if mem > peak_bytes:
                    peak_bytes = mem
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

            if (time.monotonic() - start_time) > timeout_s:
                raise subprocess.TimeoutExpired(cmd=proc.args, timeout=timeout_s)
            time.sleep(0.05)
    except ImportError:
        # psutil not available: use standard wait
        proc.wait(timeout=timeout_s)
        return proc.returncode, None


def run_batch(
    batch: List[Path],
    batch_idx: int,
    total_batches: int,
    timeout_s: int,
    has_pytest_timeout: bool,
    extra_pytest_args: Optional[List[str]] = None,
    keep_basetemp: bool = False,
) -> Dict[str, Any]:
    """Execute a single batch of test files inside a fresh Python subprocess."""
    temp_dir = tempfile.mkdtemp(prefix=f"nt_batch_{batch_idx:03d}_")
    env = os.environ.copy()

    # Strictly cap multi-threading libraries to 1 thread per worker
    for var in (
        "OMP_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
        "VECLIB_MAXIMUM_THREADS",
    ):
        env[var] = "1"
    env["MPLBACKEND"] = "Agg"

    cmd: List[str] = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        f"--basetemp={temp_dir}",
    ]

    if has_pytest_timeout:
        cmd.extend(["--timeout", str(timeout_s)])

    if extra_pytest_args:
        cmd.extend(extra_pytest_args)

    cmd.extend(str(p) for p in batch)

    print(f"[isolated {batch_idx}/{total_batches}] {len(batch)} files", flush=True)

    start_time = time.monotonic()
    status = "passed"
    exit_code = 0
    stdout_text = ""
    stderr_text = ""
    peak_memory_mb: Optional[float] = None

    try:
        popen_kwargs: Dict[str, Any] = {
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "text": True,
            "env": env,
        }
        if os.name == "nt":
            popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            popen_kwargs["start_new_session"] = True
        proc = subprocess.Popen(cmd, **popen_kwargs)
        try:
            exit_code, peak_memory_mb = _measure_peak_rss(proc, timeout_s=timeout_s + 15)
            if hasattr(proc, "communicate"):
                stdout_text, stderr_text = proc.communicate()
            else:
                stdout_text, stderr_text = "", ""
        except subprocess.TimeoutExpired:
            print(
                f"[isolated] batch {batch_idx} exceeded timeout ({timeout_s}s); terminating worker tree...",
                flush=True,
            )
            _terminate_worker(proc)
            try:
                if hasattr(proc, "communicate"):
                    stdout_text, stderr_text = proc.communicate(timeout=5)
                else:
                    stdout_text, stderr_text = "", ""
            except Exception:
                pass
            status = "timeout"
            exit_code = 124

        if exit_code != 0 and status != "timeout":
            status = "failed"
            print(f"[isolated] batch {batch_idx} failed with exit code {exit_code}", flush=True)

    finally:
        if not keep_basetemp:
            try:
                shutil.rmtree(temp_dir, ignore_errors=True)
            except Exception:
                pass

    elapsed_s = time.monotonic() - start_time

    # Parse short failure summaries if any
    failures = []
    if exit_code != 0:
        for line in (stdout_text + "\n" + stderr_text).splitlines():
            if line.startswith("FAILED ") or line.startswith("ERROR "):
                failures.append(line)

    return {
        "batch_index": batch_idx,
        "files": [str(p) for p in batch],
        "status": status,
        "exit_code": exit_code,
        "duration_s": round(elapsed_s, 2),
        "peak_memory_mb": round(peak_memory_mb, 2) if peak_memory_mb is not None else None,
        "failures": failures,
        "stdout_tail": stdout_text[-1000:] if stdout_text else "",
        "stderr_tail": stderr_text[-1000:] if stderr_text else "",
    }


def run_batches(
    files: List[Path],
    batch_size: int,
    timeout_s: int,
    extra_pytest_args: Optional[List[str]] = None,
    report_path: Optional[Path] = None,
    report_dir: Optional[Path] = None,
    stop_on_first_failure: bool = False,
) -> int:
    """Run all test files in partitioned batches and optionally write a telemetry report."""
    if batch_size < 1 or timeout_s < 1:
        raise ValueError("batch_size and timeout_s must be positive")

    batches = list(iter_batches(files, batch_size))
    total_batches = len(batches)
    has_pytest_timeout = _pytest_timeout_available()
    if not has_pytest_timeout:
        raise RuntimeError("pytest-timeout is required for bounded isolated execution")
    batch_reports: List[Dict[str, Any]] = []
    overall_exit_code = 0
    suite_start = time.monotonic()

    for batch_idx, batch in enumerate(batches, start=1):
        res = run_batch(
            batch=batch,
            batch_idx=batch_idx,
            total_batches=total_batches,
            timeout_s=timeout_s,
            has_pytest_timeout=has_pytest_timeout,
            extra_pytest_args=extra_pytest_args,
        )
        batch_reports.append(res)

        if res["exit_code"] != 0 and overall_exit_code == 0:
            overall_exit_code = res["exit_code"]
            if stop_on_first_failure:
                break

    suite_duration = round(time.monotonic() - suite_start, 2)

    passed_count = sum(1 for b in batch_reports if b["status"] == "passed")
    failed_count = sum(1 for b in batch_reports if b["status"] == "failed")
    timeout_count = sum(1 for b in batch_reports if b["status"] == "timeout")

    print(
        f"[isolated] finished {len(files)} files in {len(batch_reports)} batches: "
        f"{passed_count} passed, {failed_count} failed, {timeout_count} timeouts in {suite_duration}s",
        flush=True,
    )

    report_data = {
        "summary": {
            "total_files": len(files),
            "total_batches": len(batch_reports),
            "passed_batches": passed_count,
            "failed_batches": failed_count,
            "timeout_batches": timeout_count,
            "duration_s": suite_duration,
            "overall_exit_code": overall_exit_code,
        },
        "batches": batch_reports,
    }
    report_data["completed"] = len(batch_reports) == len(batches)
    report_data["exit_code"] = overall_exit_code
    for batch in batch_reports:
        batch["batch_number"] = batch["batch_index"]
        batch["test_files"] = [Path(path).as_posix() for path in batch["files"]]
        batch["timed_out"] = batch["status"] == "timeout"
        batch["timeout_status"] = "timeout" if batch["timed_out"] else "completed"
    if report_path:
        report_path = Path(report_path)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report_data, indent=2), encoding="utf-8")
        print(f"[isolated] telemetry report written to {report_path}", flush=True)
    if report_dir:
        report_dir = Path(report_dir)
        report_dir.mkdir(parents=True, exist_ok=True)
        for batch in batch_reports:
            idx = int(batch["batch_index"])
            stdout_path = (report_dir / f"batch_{idx:03d}.stdout.log").resolve()
            stderr_path = (report_dir / f"batch_{idx:03d}.stderr.log").resolve()
            stdout_path.write_text(batch["stdout_tail"], encoding="utf-8")
            stderr_path.write_text(batch["stderr_tail"], encoding="utf-8")
            batch["stdout_path"] = stdout_path.as_posix()
            batch["stderr_path"] = stderr_path.as_posix()
        (report_dir / "batch_summary.json").write_text(json.dumps(report_data, indent=2), encoding="utf-8")

    return overall_exit_code


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("tests"), help="Root directory for test discovery")
    parser.add_argument("--batch-size", type=int, default=8, help="Number of test files per fresh subprocess")
    parser.add_argument("--timeout-s", type=int, default=120, help="Per-batch hard timeout in seconds")
    parser.add_argument("--report", type=Path, default=None, help="Path to write JSON telemetry report")
    parser.add_argument("--report-dir", type=Path, default=None, help="Directory for per-batch logs and batch_summary.json")
    parser.add_argument("--marker", "-m", type=str, default=None, help="Pytest marker expression (e.g. 'not slow')")
    parser.add_argument("--fail-fast", action="store_true", help="Halt execution on first failing batch")
    parser.add_argument("files", nargs="*", type=Path, help="Explicit test files; defaults to discovery")

    args = parser.parse_args(argv)

    extra_args: List[str] = []
    if args.marker:
        extra_args.extend(["-m", args.marker])

    files = args.files or discover(args.root)
    if not files:
        parser.error(f"No test files found in {args.root}")

    return run_batches(
        files=files,
        batch_size=args.batch_size,
        timeout_s=args.timeout_s,
        extra_pytest_args=extra_args,
        report_path=args.report,
        report_dir=args.report_dir,
        stop_on_first_failure=args.fail_fast,
    )


if __name__ == "__main__":
    raise SystemExit(main())
