"""Build Level O report artifacts from the package-local ledger."""

from __future__ import annotations

import argparse

from ..reports import build_ontology_report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    build_ontology_report(args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
