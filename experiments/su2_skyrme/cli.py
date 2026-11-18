"""CLI for the SU(2)/Skyrme experiment layer."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .adapter import probe_solver_availability
from .result_contract import validate_result_dict
from .runner import run_experiment
from .schema import ExperimentConfigError, load_experiment_config


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m experiments.su2_skyrme",
        description=(
            "Reproducible SU(2)/Skyrme experiment and parameter-sweep runner. "
            "Does not implement solver mathematics or visualization."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="Run one experiment config")
    run_p.add_argument("--config", required=True, help="Path to YAML/JSON experiment config")
    run_p.add_argument(
        "--output",
        required=True,
        help="Destination JSON path for ExperimentResultV1",
    )
    run_p.add_argument(
        "--allow-stub",
        action="store_true",
        help="Permit deterministic stub backend when field_theory.su2 is unavailable",
    )

    probe_p = sub.add_parser("probe-solver", help="Report solver API availability")
    probe_p.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON",
    )

    validate_p = sub.add_parser("validate-config", help="Validate an experiment config")
    validate_p.add_argument("--config", required=True)

    validate_r = sub.add_parser("validate-result", help="Validate a result JSON envelope")
    validate_r.add_argument("--result", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "probe-solver":
        availability = probe_solver_availability()
        payload = availability.to_dict()
        if args.json:
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            print(f"import_status: {availability.import_status}")
            print(f"module_path: {availability.module_path}")
            print(f"public_symbols: {', '.join(availability.public_symbols) or '(none)'}")
            print(f"missing_symbols: {', '.join(availability.missing_symbols) or '(none)'}")
            print(f"notes: {availability.notes}")
            if availability.dependency_blocker:
                print(f"dependency_blocker: {availability.dependency_blocker}")
        return 0 if availability.import_status == "available" else 2

    if args.command == "validate-config":
        try:
            config = load_experiment_config(args.config)
        except ExperimentConfigError as exc:
            print(f"invalid config: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(config.to_dict(), indent=2, sort_keys=True))
        return 0

    if args.command == "validate-result":
        raw = json.loads(Path(args.result).read_text(encoding="utf-8"))
        problems = validate_result_dict(raw)
        if problems:
            for problem in problems:
                print(f"invalid: {problem}", file=sys.stderr)
            return 1
        print("result ok")
        return 0

    if args.command == "run":
        try:
            config = load_experiment_config(args.config)
        except ExperimentConfigError as exc:
            print(f"invalid config: {exc}", file=sys.stderr)
            return 1
        result = run_experiment(config, allow_stub=bool(args.allow_stub))
        path = result.write_json(args.output)
        print(f"wrote {path}")
        print(f"status={result.status} backend={result.solver_backend} result_id={result.result_id}")
        if result.status == "solver_unavailable":
            return 2
        if result.status in {"failed", "invalid_config", "numerical_failure"}:
            return 1
        return 0

    parser.error(f"unknown command {args.command}")
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
