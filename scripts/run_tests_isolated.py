"""Run the repository test suite in bounded fresh Python processes.

The monolithic pytest collector imports optional Torch/MNE stacks into one
process. This runner preserves coverage while releasing those native heaps
after each file batch.
"""
from __future__ import annotations
import argparse
import os
import subprocess
import sys
from pathlib import Path


def discover(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("test_*.py") if "apps/awareness_studio" not in path.as_posix())


def run_batches(files: list[Path], batch_size: int, timeout_s: int) -> int:
    if batch_size < 1 or timeout_s < 1:
        raise ValueError("batch_size and timeout_s must be positive")
    total = (len(files) + batch_size - 1) // batch_size
    for offset in range(0, len(files), batch_size):
        batch = files[offset:offset + batch_size]
        number = offset // batch_size + 1
        command = [sys.executable, "-m", "pytest", "-q", "--timeout", str(timeout_s), *[str(p) for p in batch]]
        print(f"[isolated {number}/{total}] {len(batch)} files", flush=True)
        env = os.environ.copy()
        # Keep native BLAS/OpenMP pools bounded in every fresh worker.
        for variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
            env[variable] = "1"
        try:
            completed = subprocess.run(
                command,
                check=False,
                env=env,
                timeout=timeout_s + 30,
            )
        except subprocess.TimeoutExpired:
            print(
                f"[isolated] batch {number} exceeded {timeout_s + 30}s; "
                "terminating the worker",
                flush=True,
            )
            return 124
        if completed.returncode != 0:
            print(f"[isolated] batch {number} failed with exit code {completed.returncode}", flush=True)
            return completed.returncode
    print(f"[isolated] completed {len(files)} test files in {total} fresh processes", flush=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("tests"))
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--timeout-s", type=int, default=300)
    parser.add_argument("files", nargs="*", type=Path, help="explicit test files; defaults to discovery")
    args = parser.parse_args(argv)
    files = args.files or discover(args.root)
    if not files:
        parser.error("no test files found")
    return run_batches(files, args.batch_size, args.timeout_s)


if __name__ == "__main__":
    raise SystemExit(main())
