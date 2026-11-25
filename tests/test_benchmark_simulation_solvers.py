"""Integration tests for benchmark runner CLI and telemetry validator CLI."""
from __future__ import annotations

from pathlib import Path
import tempfile
import pytest

from scripts.benchmark_simulation_solvers import main as benchmark_main
from tools.validate_solver_benchmark import main as validate_main, validate_benchmark_file


class TestBenchmarkCLISuite:
    def test_cli_execution_and_validation(self):
        """Benchmark CLI must write valid telemetry verified by the validator CLI."""
        with tempfile.TemporaryDirectory() as td:
            out_dir = Path(td) / "benchmarks"

            # 1. Run benchmark CLI
            ret_code = benchmark_main([
                "--n-layers", "1",
                "--solvers", "exact_dense", "sparse_shift_invert",
                "--output-dir", str(out_dir),
            ])
            assert ret_code == 0

            target_file = out_dir / "simulation_solver_benchmark.json"
            assert target_file.is_file()
            assert target_file.with_suffix(".json.sha256").is_file()

            # 2. Run validator API
            valid = validate_benchmark_file(target_file)
            assert valid is True

            # 3. Run validator CLI entrypoint
            ret_val = validate_main([str(target_file)])
            assert ret_val == 0
