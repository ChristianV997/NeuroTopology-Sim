#!/usr/bin/env python3
"""Validate one claim or a JSONL batch using the offline claim gate."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.research_claim_gate.gate import evaluate_claim, serialize_json  # noqa: E402


def _args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Offline deterministic research-claim gate")
    parser.add_argument("--input", required=True, type=Path, help="JSON object or JSONL claim file")
    parser.add_argument("--output", type=Path, help="Output JSON or JSONL report; stdout when omitted")
    parser.add_argument("--jsonl", action="store_true", help="Treat input as one JSON object per line")
    parser.add_argument("--request-network", action="store_true", help="Request network access; rejected without --network-policy")
    parser.add_argument("--network-policy", help="Explicit approved policy identifier; no network is contacted")
    return parser.parse_args(argv)


def _load(path: Path, jsonl: bool) -> list[Any] | Any:
    text = path.read_text(encoding="utf-8")
    if jsonl:
        records = []
        for line_number, line in enumerate(text.splitlines(), 1):
            if not line.strip():
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                records.append({"claim_id": f"line-{line_number}", "text": "", "_parse_error": str(exc)})
        return records
    return json.loads(text)


def main(argv: list[str] | None = None) -> int:
    args = _args(argv)
    try:
        payload = _load(args.input, args.jsonl)
    except (OSError, json.JSONDecodeError) as exc:
        report = {"schema_version": "NeuroTopology.ResearchClaimGate.v1", "decision": "CLAIM_INCOMPLETE", "error": str(exc)}
        output = serialize_json(report)
        if args.output:
            args.output.write_text(output, encoding="utf-8")
        else:
            print(output, end="")
        return 2

    def apply_network(record: Any) -> Any:
        if not isinstance(record, dict):
            return record
        adjusted = dict(record)
        if args.request_network:
            adjusted["network_access_requested"] = True
            adjusted["network_policy_approved"] = bool(args.network_policy)
        return adjusted

    if args.jsonl:
        results = [evaluate_claim(apply_network(record)).to_dict() for record in payload]
        output = serialize_json(results)
        failed = any(result["decision"] not in {"CLAIM_ADMISSIBLE"} for result in results)
    else:
        result = evaluate_claim(apply_network(payload))
        output = serialize_json(result)
        failed = result.decision != "CLAIM_ADMISSIBLE"

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output, encoding="utf-8")
    else:
        print(output, end="")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
