#!/usr/bin/env python3
"""Validate a local dataset provenance declaration. No downloads."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from shared.provenance.contract import (  # noqa: E402
    attach_provenance,
    serialize_record,
    validate_declaration,
    write_sidecar,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--declaration", required=True, type=Path, help="Local JSON declaration")
    parser.add_argument("--output-json", type=Path, help="Write DatasetProvenance JSON")
    parser.add_argument("--sidecar-dir", type=Path, help="Write dataset_provenance.json beside a run")
    parser.add_argument("--run-id-ref", type=str, default=None)
    args = parser.parse_args()
    raw = json.loads(args.declaration.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        print(json.dumps({"status": "FAIL", "error": "declaration must be a JSON object"}), file=sys.stderr)
        return 2
    record = validate_declaration(raw)
    payload = serialize_record(record)
    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(payload + "\n", encoding="utf-8")
    if args.sidecar_dir:
        write_sidecar(record, args.sidecar_dir)
        if args.run_id_ref:
            sidecar = attach_provenance({"run_id_ref": args.run_id_ref}, record)
            (args.sidecar_dir / "dataset_provenance_sidecar.json").write_text(
                json.dumps(sidecar, sort_keys=True, indent=2) + "\n",
                encoding="utf-8",
            )
    print(json.dumps(json.loads(payload), indent=2, sort_keys=True))
    if record.validation_status in {"FAIL", "UNAVAILABLE"}:
        return 2
    if record.validation_status == "INCOMPLETE":
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
