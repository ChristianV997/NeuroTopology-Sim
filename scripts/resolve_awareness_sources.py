#!/usr/bin/env python3
"""Thin CLI over tools.awareness_studio_research.source_resolution.
Fully offline: every input is a local JSON file (a claimed identity, a
list of candidate identities, and/or an operator correction) -- this
script never fetches anything over the network.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.awareness_studio_research.source_resolution import (  # noqa: E402
    SourceIdentity,
    SourceResolutionLog,
    claim_availability,
    resolve_source_identity,
)


def _default_log_path() -> Path:
    return Path(__file__).resolve().parent.parent / "outputs" / "awareness_studio_research" / "source_resolution_events.jsonl"


def _load_identity(path: Path) -> SourceIdentity:
    return SourceIdentity.from_dict(json.loads(Path(path).read_text()))


def _load_identities(path: Path) -> list[SourceIdentity]:
    raw = json.loads(Path(path).read_text())
    entries = raw if isinstance(raw, list) else raw.get("candidates", [])
    return [SourceIdentity.from_dict(entry) for entry in entries]


def cmd_resolve(args: argparse.Namespace) -> int:
    claimed = _load_identity(args.claimed)
    candidates = _load_identities(args.candidates) if args.candidates else []
    operator_correction = _load_identity(args.operator_correction) if args.operator_correction else None

    result = resolve_source_identity(
        claimed,
        candidates,
        operator_correction=operator_correction,
        duplicate_of=args.duplicate_of,
        superseded_by=args.superseded_by,
    )

    log = SourceResolutionLog(args.log)
    event = log.record_resolution(original_source_ref=claimed.source_ref, result=result, resolver=args.resolver)

    output = {
        "resolution": {
            "state": result.state,
            "confidence": result.confidence,
            "reason": result.reason,
            "matched_candidate_ref": result.matched_candidate_ref,
            "evidence": list(result.evidence),
        },
        "claim_availability": claim_availability(result.state),
        "event_id": event.event_id,
    }
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


def cmd_history(args: argparse.Namespace) -> int:
    log = SourceResolutionLog(args.log)
    history = log.history_for(args.source_ref)
    print(json.dumps([e.to_dict() for e in history], indent=2, sort_keys=True))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", type=Path, default=_default_log_path())
    sub = parser.add_subparsers(dest="command", required=True)

    resolve = sub.add_parser("resolve", help="resolve a claimed source identity against candidates")
    resolve.add_argument("--claimed", type=Path, required=True)
    resolve.add_argument("--candidates", type=Path, default=None)
    resolve.add_argument("--operator-correction", type=Path, default=None)
    resolve.add_argument("--duplicate-of", default=None)
    resolve.add_argument("--superseded-by", default=None)
    resolve.add_argument("--resolver", default="operator")
    resolve.set_defaults(func=cmd_resolve)

    history = sub.add_parser("history", help="print the append-only resolution history for a source ref")
    history.add_argument("--source-ref", required=True)
    history.set_defaults(func=cmd_history)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
