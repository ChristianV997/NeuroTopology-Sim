"""Validate and render a higher-order spectral feature contract offline."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.higher_order_integration.spectral_adapter import (  # noqa: E402
    adapt_spectral_feature_report,
    contract_to_json,
    contract_to_markdown,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="higher-order spectral JSON report")
    parser.add_argument("--output-json", type=Path)
    parser.add_argument("--output-markdown", type=Path)
    parser.add_argument("--channel-identity")
    parser.add_argument("--condition-label")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = json.loads(args.input.read_text(encoding="utf-8"))
        contract = adapt_spectral_feature_report(
            report,
            channel_identity=args.channel_identity,
            condition_label=args.condition_label,
        )
        encoded = contract_to_json(contract)
        markdown = contract_to_markdown(contract)
    except Exception as error:
        # Keep command-line failures machine-readable and finite.
        encoded = json.dumps(
            {
                "schema_version": "NeuroTopologySim.SpectralFeatureContract.v1",
                "records": [],
                "validation_errors": [f"{type(error).__name__}: {error}"],
                "validation_warnings": [],
            },
            sort_keys=True,
            indent=2,
            allow_nan=False,
        )
        markdown = "# Spectral feature contract\n\nValidation failed.\n"
        contract = None
    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(encoded + "\n", encoding="utf-8")
    else:
        print(encoded)
    if args.output_markdown:
        args.output_markdown.parent.mkdir(parents=True, exist_ok=True)
        args.output_markdown.write_text(markdown, encoding="utf-8")
    if contract is None:
        return 1
    return 1 if contract.validation_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
