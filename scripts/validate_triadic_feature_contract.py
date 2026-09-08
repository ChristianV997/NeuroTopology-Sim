"""Validate and serialize one triadic feature-contract input envelope."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

# Direct script execution starts with ``scripts/`` on sys.path.  Add only the
# repository root so the owned adapter can be imported without installation.
if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.higher_order_integration.triadic_adapter import (
    TriadicContractError,
    adapt_triadic_output,
    validate_serialized_feature_record,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="JSON input envelope")
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--markdown-out", type=Path)
    args = parser.parse_args(argv)
    try:
        envelope = json.loads(args.input.read_text(encoding="utf-8"))
        record = adapt_triadic_output(envelope)
        validate_serialized_feature_record(record.to_dict())
        if args.json_out:
            args.json_out.parent.mkdir(parents=True, exist_ok=True)
            args.json_out.write_text(record.to_json() + "\n", encoding="utf-8")
        if args.markdown_out:
            args.markdown_out.parent.mkdir(parents=True, exist_ok=True)
            args.markdown_out.write_text(record.to_markdown(), encoding="utf-8")
        print(record.to_json())
        return 0
    except (OSError, ValueError, TypeError, json.JSONDecodeError, TriadicContractError) as exc:
        print(f"triadic feature contract invalid: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
