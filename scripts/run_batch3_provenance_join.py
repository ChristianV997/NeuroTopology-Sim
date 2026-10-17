"""Run the bounded, read-only Batch 3 provenance join auditor."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools.batch3_provenance_join.auditor import AuditInputError, audit_provenance
from tools.batch3_provenance_join.models import AuditLimits


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-root", required=True, type=Path)
    parser.add_argument(
        "--input-manifest",
        action="append",
        required=True,
        type=Path,
        help="explicit JSON producer manifest path beneath artifact-root; repeat as needed",
    )
    parser.add_argument("--max-manifest-bytes", type=int, default=2 * 1024 * 1024)
    parser.add_argument("--max-artifact-bytes", type=int, default=64 * 1024 * 1024)
    parser.add_argument("--max-total-bytes", type=int, default=256 * 1024 * 1024)
    parser.add_argument("--max-files", type=int, default=10_000)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        limits = AuditLimits(
            max_manifest_bytes=args.max_manifest_bytes,
            max_artifact_bytes=args.max_artifact_bytes,
            max_total_bytes=args.max_total_bytes,
            max_files=args.max_files,
        )
        report = audit_provenance(args.artifact_root, args.input_manifest, limits=limits)
    except (AuditInputError, ValueError) as exc:
        print(json.dumps({"status": "INVALID", "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(report, sort_keys=True, indent=2, allow_nan=False))
    return {"CLEAN": 0, "INCOMPLETE": 1, "INVALID": 2}[report["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
