"""CLI entry: ``python -m experiments.su2_skyrme --config path.yaml``."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .provenance import canonical_json
from .runner import run_experiment
from .schema import ConfigError


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m experiments.su2_skyrme",
        description=(
            "Run a reproducible SU(2)/Skyrme experiment or parameter grid. "
            "Does not implement solver mathematics or visualization."
        ),
    )
    parser.add_argument(
        "--config",
        required=True,
        help="Path to YAML or JSON experiment config",
    )
    parser.add_argument(
        "--print-result",
        action="store_true",
        help="Print the result envelope JSON to stdout",
    )
    args = parser.parse_args(argv)

    try:
        result = run_experiment(args.config)
    except ConfigError as exc:
        print(f"invalid config: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001
        print(f"experiment failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    summary = {
        "run_id": result.run_id,
        "status": result.status,
        "artifacts": result.artifacts,
        "solver_backend_resolved": result.solver_backend_resolved,
        "solver_available": result.solver_available,
    }
    print(canonical_json(summary))
    if args.print_result:
        print(canonical_json(result.to_dict()))
    run_dir = Path(result.artifacts["run_dir"])
    print(f"wrote artifacts under {run_dir}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
