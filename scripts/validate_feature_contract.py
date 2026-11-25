#!/usr/bin/env python3
"""CLI entrypoint for validating canonical feature contract JSON files and bundles.

Enforces schema, units, axes, channel uniqueness, and scientific guardrails.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

# Ensure repository root is on sys.path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.feature_contracts import (
    FeatureContractValidationError,
    bundle_from_dict,
    record_from_dict,
    validate_feature_bundle,
    validate_feature_record,
)


def parse_args(args: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate canonical feature records and bundles against schema and guardrails.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--input",
        type=Path,
        required=True,
        help="Path to feature record/bundle JSON file or directory of JSON files.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional path to write validation summary JSON report.",
    )
    return parser.parse_args(args)


def validate_file(path: Path) -> dict[str, Any]:
    """Validates a single JSON file containing a CanonicalFeatureRecord or CanonicalFeatureBundle."""
    result: dict[str, Any] = {
        "file": str(path.resolve()),
        "valid": False,
        "type": "unknown",
        "errors": [],
    }

    try:
        content = path.read_text(encoding="utf-8")
        data = json.loads(content)
    except Exception as exc:
        result["errors"].append(f"Failed to read/parse JSON: {exc}")
        return result

    if not isinstance(data, dict):
        result["errors"].append("Root JSON element must be an object.")
        return result

    schema = data.get("schema_version", "")

    if "FeatureBundle" in schema or "Bundle" in schema or "bundle_id" in data:
        result["type"] = "bundle"
        try:
            bundle = bundle_from_dict(data, validate=True)
            result["valid"] = True
            result["bundle_id"] = bundle.bundle_id
            result["records_count"] = len(bundle.records)
        except FeatureContractValidationError as exc:
            result["errors"].append(str(exc))
        except Exception as exc:
            result["errors"].append(f"Unexpected bundle error: {exc}")

    elif "FeatureRecord" in schema or "Record" in schema or "feature_family" in data:
        result["type"] = "record"
        try:
            rec = record_from_dict(data, validate=True)
            result["valid"] = True
            result["feature_family"] = rec.feature_family
            result["feature_name"] = rec.feature_name
        except FeatureContractValidationError as exc:
            result["errors"].append(str(exc))
        except Exception as exc:
            result["errors"].append(f"Unexpected record error: {exc}")
    else:
        result["errors"].append(f"Unrecognized schema_version or root keys: '{schema}'.")

    return result


def main() -> int:
    args = parse_args()
    input_path = args.input

    if not input_path.exists():
        print(json.dumps({"error": f"Input path does not exist: {input_path}"}, indent=2), file=sys.stderr)
        return 1

    if input_path.is_file():
        target_files = [input_path]
    else:
        target_files = sorted(input_path.glob("**/*.json"))

    if not target_files:
        print(json.dumps({"error": f"No JSON files discovered in path: {input_path}"}, indent=2), file=sys.stderr)
        return 1

    reports: list[dict[str, Any]] = []
    total_valid = 0
    total_invalid = 0

    for f in target_files:
        rep = validate_file(f)
        if rep["valid"]:
            total_valid += 1
        else:
            total_invalid += 1
        reports.append(rep)

    summary = {
        "schema": "NeuroTopologySim.FeatureContractValidationReport.v1",
        "total_files": len(target_files),
        "valid_count": total_valid,
        "invalid_count": total_invalid,
        "all_valid": (total_invalid == 0),
        "results": reports,
    }

    report_json = json.dumps(summary, indent=2)
    print(report_json)

    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report_json + "\n", encoding="utf-8")

    if total_invalid > 0:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
