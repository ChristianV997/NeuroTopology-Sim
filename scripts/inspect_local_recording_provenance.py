#!/usr/bin/env python3
"""Inspect local FIF/EDF/BDF/VHDR/BIDS metadata. No downloads. No sample load."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from shared.provenance.readers import inspect_local_recording  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--origin", default="empirical_local")
    parser.add_argument("--output-json", type=Path)
    parser.add_argument("--as-declaration", action="store_true")
    args = parser.parse_args()
    try:
        record = inspect_local_recording(args.input, origin=args.origin)
    except Exception as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2
    payload = record.as_provenance_declaration() if args.as_declaration else record.to_dict()
    text = json.dumps(payload, indent=2, sort_keys=True)
    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(text + "\n", encoding="utf-8")
    print(text)
    if record.capability != "ok" and record.capability != "available":
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
