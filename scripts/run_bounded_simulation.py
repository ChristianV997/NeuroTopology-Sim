"""Run one explicitly allowlisted local simulation workload in isolation."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.simulation_execution.finite import dumps_finite  # noqa: E402
from tools.simulation_execution.models import RunnerConfig, WorkUnit  # noqa: E402
from tools.simulation_execution.runner import run_plan  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workload-id", required=True)
    parser.add_argument("--unit-id", required=True)
    parser.add_argument("--command", required=True, nargs="+")
    parser.add_argument("--allow-command", required=True, nargs="+")
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--expected-output", action="append", default=[])
    parser.add_argument("--timeout-s", type=float, default=300.0)
    parser.add_argument("--memory-budget-bytes", type=int)
    parser.add_argument("--disk-budget-bytes", type=int)
    parser.add_argument("--code-revision", default="unknown")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--no-resume", action="store_true")
    parser.add_argument("--allow-network", action="store_true")
    args = parser.parse_args()
    output_dir = args.output_dir or args.output_root / args.unit_id
    expected = tuple(dict.fromkeys(["unit_manifest.json", *args.expected_output]))
    unit = WorkUnit.make(args.unit_id, args.workload_id, args.command, output_dir, expected_outputs=expected, seed=args.seed, timeout_s=args.timeout_s)
    config = RunnerConfig(output_root=args.output_root, allowed_commands={args.workload_id: tuple(args.allow_command)}, default_timeout_s=args.timeout_s, memory_budget_bytes=args.memory_budget_bytes, disk_budget_bytes=args.disk_budget_bytes, code_revision=args.code_revision, network_disabled=not args.allow_network)
    report = run_plan([unit], config, resume=not args.no_resume)
    print(dumps_finite(report), end="")
    return 0 if report["summary"].get("PASS", 0) == 1 else 2


if __name__ == "__main__":
    raise SystemExit(main())
