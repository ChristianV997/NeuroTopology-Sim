#!/usr/bin/env python3
"""Thin CLI over tools.literature_evidence. Fully offline by default --
network access is never invoked from this script.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.literature_evidence.models import LiteratureRecord, SourceSnapshot  # noqa: E402
from tools.literature_evidence.reporting import to_finite_json  # noqa: E402
from tools.literature_evidence.store import ImmutabilityError, LiteratureEvidenceStore  # noqa: E402
from tools.literature_evidence.validation import validate_record  # noqa: E402


def _default_store_path() -> Path:
    return Path(__file__).resolve().parent.parent / "outputs" / "literature_evidence" / "events.jsonl"


def cmd_validate(args: argparse.Namespace) -> int:
    record = LiteratureRecord.from_dict(json.loads(args.record.read_text()))
    snapshot = SourceSnapshot.from_dict(json.loads(args.snapshot.read_text())) if args.snapshot else None
    result = validate_record(record, snapshot)
    print(to_finite_json(result.to_dict()))
    return 0 if result.is_valid() else 1


def cmd_ingest(args: argparse.Namespace) -> int:
    record = LiteratureRecord.from_dict(json.loads(args.record.read_text()))
    snapshot = SourceSnapshot.from_dict(json.loads(args.snapshot.read_text())) if args.snapshot else None
    result = validate_record(record, snapshot)
    if not result.is_valid():
        print(to_finite_json(result.to_dict()), file=sys.stderr)
        return 1

    store = LiteratureEvidenceStore(args.store)
    try:
        store.add_source(record)
        if snapshot is not None:
            store.add_snapshot(snapshot)
    except ImmutabilityError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(to_finite_json({"ingested": record.source_id, "validation": result.to_dict()}))
    return 0


def cmd_history(args: argparse.Namespace) -> int:
    store = LiteratureEvidenceStore(args.store)
    events = store.audit_history(entity_type=args.entity_type, entity_id=args.entity_id)
    print(json.dumps(events, indent=2, sort_keys=True))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", type=Path, default=_default_store_path())
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate", help="validate a literature record without storing it")
    validate.add_argument("--record", type=Path, required=True)
    validate.add_argument("--snapshot", type=Path, default=None)
    validate.set_defaults(func=cmd_validate)

    ingest = sub.add_parser("ingest", help="validate then store a literature record (offline)")
    ingest.add_argument("--record", type=Path, required=True)
    ingest.add_argument("--snapshot", type=Path, default=None)
    ingest.set_defaults(func=cmd_ingest)

    history = sub.add_parser("history", help="print the append-only audit history")
    history.add_argument("--entity-type", default=None)
    history.add_argument("--entity-id", default=None)
    history.set_defaults(func=cmd_history)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
