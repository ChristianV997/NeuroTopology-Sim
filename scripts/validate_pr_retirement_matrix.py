"""Thin Release CLI around QA PR retirement matrix rules.

Does not rewrite rules. Imports and calls QA helpers from
``tests/release/pr_retirement_validate.py``:

- ``validate_path``
- ``validate_pr_retirement_matrix``
- ``run_validation``
- ``DEFAULT_MATRIX_PATH``

Offline only. Read-only vs GitHub. No close / merge / retire actions.
Warnings never count as success: exit 0 only when ``ValidationResult.ok``.

    python scripts/validate_pr_retirement_matrix.py [--matrix PATH] [--json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

_RELEASE_DIR = REPO_ROOT / "tests" / "release"
if str(_RELEASE_DIR) not in sys.path:
    sys.path.insert(0, str(_RELEASE_DIR))

from pr_retirement_validate import (  # noqa: E402
    DEFAULT_MATRIX_PATH,
    run_validation,
    validate_path,
    validate_pr_retirement_matrix,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--matrix",
        type=Path,
        default=DEFAULT_MATRIX_PATH,
        help=(
            "Path to pr_retirement_matrix.yaml "
            "(default: configs/release/pr_retirement_matrix.yaml)"
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print a JSON dump of errors and warnings",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    matrix = Path(args.matrix)

    # Public QA helpers — same rules, no rewrite. Path and mapping APIs agree.
    result = validate_pr_retirement_matrix(matrix)
    from_path = validate_path(matrix)
    if from_path.errors != result.errors or from_path.warnings != result.warnings:
        result = from_path

    if args.json:
        print(
            json.dumps(
                {
                    "ok": result.ok,
                    "errors": list(result.errors),
                    "warnings": list(result.warnings),
                    "matrix": str(matrix),
                },
                indent=2,
                sort_keys=True,
            )
        )
    elif not result.ok:
        for item in result.errors:
            print(item)
        for item in result.warnings:
            print(item)

    # Fail-closed exit from QA: 0 only when errors and warnings are empty.
    return run_validation(matrix)


if __name__ == "__main__":
    raise SystemExit(main())
