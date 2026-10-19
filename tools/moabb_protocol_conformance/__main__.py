"""CLI: offline MOABB protocol-conformance from candidate/fixture JSON."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from dataset_importers.moabb_importer import import_moabb_candidates_from_fixture
from tools.moabb_protocol_conformance.manifest import build_from_candidate_dict, build_protocol_manifest
from tools.moabb_protocol_conformance.serialization import dumps, load_json


def _load_candidates(args: argparse.Namespace) -> List[Dict[str, Any]]:
    if args.candidate_json:
        data = load_json(args.candidate_json)
        if "candidate_id" in data or "source_dataset_id" in data:
            return [data]
        entries = data.get("candidates") or data.get("datasets") or data.get("entries") or []
        return [dict(e) for e in entries]
    if args.moabb_fixture:
        records = import_moabb_candidates_from_fixture(args.moabb_fixture)
        return [r.to_dict() for r in records]
    raise SystemExit("Provide --candidate-json or --moabb-fixture")


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--candidate-json", help="DatasetCandidateRecordV1 JSON or list wrapper")
    p.add_argument("--moabb-fixture", help="MOABB importer fixture JSON (datasets[])")
    p.add_argument("--protocol-json", required=True, help="Protocol field object JSON")
    p.add_argument("--output", default=None, help="Write manifest JSON here")
    def positive_limit(value: str) -> int:
        try:
            limit = int(value)
        except ValueError as exc:
            raise argparse.ArgumentTypeError("limit must be a positive integer") from exc
        if limit <= 0:
            raise argparse.ArgumentTypeError("limit must be a positive integer")
        return limit

    p.add_argument("--limit", type=positive_limit, default=1)
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    protocol_fields = load_json(args.protocol_json)
    candidates = _load_candidates(args)[: args.limit]
    manifests = []
    for candidate in candidates:
        manifest = build_from_candidate_dict(candidate, protocol_fields)
        manifests.append(manifest.to_dict())

    if len(manifests) == 1:
        payload: Any = manifests[0]
    else:
        payload = {
            "schema_version": "NeuroTopology.MoabbProtocolManifestBatch.v1",
            "evidence_class": "protocol_conformance_only",
            "count": len(manifests),
            "manifests": manifests,
        }

    text = dumps(payload)
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    print(text)
    if len(manifests) == 1:
        return 0 if manifests[0].get("conformance", {}).get("ok") else 1
    return 0 if all(m.get("conformance", {}).get("ok") for m in manifests) else 1


if __name__ == "__main__":
    raise SystemExit(main())
