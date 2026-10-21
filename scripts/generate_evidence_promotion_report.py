#!/usr/bin/env python3
"""Generate fixture-only promotion-gate reports, command-center payload, and RAG pack."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.evidence_promotion_gate.command_center import build_payload  # noqa: E402
from tools.evidence_promotion_gate.rag_pack import build_pack  # noqa: E402
from tools.evidence_promotion_gate.reporting import (  # noqa: E402
    evaluate_and_report,
    serialize_json,
    write_markdown,
    write_report,
)


def _args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate fixture-only evidence promotion reports")
    parser.add_argument(
        "--input",
        type=Path,
        default=ROOT / "tests" / "evidence_promotion_gate" / "fixtures",
        help="Fixture directory",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "outputs" / "evidence_promotion_gate",
        help="Output directory",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _args(argv)
    payload = evaluate_and_report(args.input)
    out = args.output
    out.mkdir(parents=True, exist_ok=True)
    write_report(payload, out / "report.json")
    write_markdown(payload, out / "report.md")
    (out / "command_center").mkdir(parents=True, exist_ok=True)
    (out / "rag_pack").mkdir(parents=True, exist_ok=True)
    (out / "command_center" / "evidence_promotion_status.json").write_text(
        serialize_json(build_payload(payload)), encoding="utf-8"
    )
    (out / "rag_pack" / "rag_pack.json").write_text(serialize_json(build_pack(payload)), encoding="utf-8")
    (out / "rag_pack" / "rag_public_answer_guidelines.md").write_text(
        "No proof, diagnosis, treatment, ontology promotion, or empirical confirmation claims.\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
