#!/usr/bin/env python3
"""Thin CLI over tools.awareness_studio_research. Offline by default --
network access requires --allow-network on the subcommands that support it.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.awareness_studio_research import importers  # noqa: E402
from tools.awareness_studio_research.query import available_query_packs, run_query_pack  # noqa: E402
from tools.awareness_studio_research.store import EvidenceRegistry  # noqa: E402


def _default_store_path() -> Path:
    return Path(__file__).resolve().parent.parent / "outputs" / "awareness_studio_research" / "events.jsonl"


def cmd_ingest(args: argparse.Namespace) -> int:
    registry = EvidenceRegistry(args.store)
    if args.kind == "json":
        sources = importers.import_json_export(args.input)
    elif args.kind == "csv":
        sources = importers.import_csv_export(args.input)
    else:
        print(f"unsupported --kind for file ingestion: {args.kind}", file=sys.stderr)
        return 2
    for source in sources:
        existing = registry.get_source(source.source_id)
        if existing is not None:
            print(f"skip (already present): {source.source_id} {source.title!r}")
            continue
        registry.add_source(source)
        print(f"added: {source.source_id} {source.title!r}")
    return 0


def cmd_query(args: argparse.Namespace) -> int:
    registry = EvidenceRegistry(args.store)
    results = run_query_pack(registry.list_claims(), args.pack)
    print(json.dumps([c.to_dict() for c in results], indent=2, sort_keys=True))
    return 0


def cmd_list_packs(_args: argparse.Namespace) -> int:
    for pack in available_query_packs():
        print(pack)
    return 0


def cmd_list_sources(args: argparse.Namespace) -> int:
    registry = EvidenceRegistry(args.store)
    for source in registry.list_sources():
        print(f"{source.source_id}  [{source.status}/{source.evidence_tier}]  {source.title}")
    return 0


def cmd_audit(args: argparse.Namespace) -> int:
    registry = EvidenceRegistry(args.store)
    events = registry.audit_history(entity_type=args.entity_type, entity_id=args.entity_id)
    print(json.dumps(events, indent=2, sort_keys=True))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", type=Path, default=_default_store_path())
    sub = parser.add_subparsers(dest="command", required=True)

    ingest = sub.add_parser("ingest", help="ingest an explicit JSON/CSV export (offline)")
    ingest.add_argument("--kind", choices=["json", "csv"], required=True)
    ingest.add_argument("--input", type=Path, required=True)
    ingest.set_defaults(func=cmd_ingest)

    query = sub.add_parser("query", help="run a deterministic query pack over stored claims")
    query.add_argument("--pack", required=True)
    query.set_defaults(func=cmd_query)

    list_packs = sub.add_parser("list-packs", help="list available query packs")
    list_packs.set_defaults(func=cmd_list_packs)

    list_sources = sub.add_parser("list-sources", help="list all sources in the registry")
    list_sources.set_defaults(func=cmd_list_sources)

    audit = sub.add_parser("audit", help="print the immutable audit history")
    audit.add_argument("--entity-type", default=None)
    audit.add_argument("--entity-id", default=None)
    audit.set_defaults(func=cmd_audit)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
