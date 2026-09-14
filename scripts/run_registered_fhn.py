"""Exact-argv worker for the bounded, registered synthetic FHN workload."""
from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.simulation_execution.fhn_workload import execute_spec


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: run_registered_fhn.py SPEC_JSON EXPECTED_SHA256")
    execute_spec(Path(sys.argv[1]), sys.argv[2], Path.cwd())
