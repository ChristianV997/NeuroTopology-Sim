"""Read-only post-integration scientific-release audit CLI.

Consumes a single JSON document (schema documented in
docs/release/scientific_release_audit.md) describing the integration
merge matrix, scientific-gate report, provenance records, falsification
payloads, topology summaries, capability snapshot, test summary, CI
status, performance claims, and an optional dashboard-isolation claim,
and produces a release decision plus findings.

This script never mutates anything: no git operation, no network call,
no write except the optional --output-dir report files.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from tools.release_scientific_audit import audit, loaders, reporting  # noqa: E402


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="AuditInput JSON document")
    parser.add_argument("--dashboard-src", type=Path, default=None,
                         help="override/supply the dashboard source path to independently scan")
    parser.add_argument("--output-dir", type=Path, default=None, help="write report.json/report.md here")
    args = parser.parse_args(argv)

    audit_input = loaders.audit_input_from_file(args.input)
    if args.dashboard_src is not None:
        audit_input = audit_input.__class__(
            **{**audit_input.__dict__, "dashboard_src_path": str(args.dashboard_src)}
        )

    report = audit.run_audit(audit_input)
    json_text = reporting.to_json(report)
    markdown_text = reporting.to_markdown(report)

    if args.output_dir is not None:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        (args.output_dir / "report.json").write_text(json_text + "\n", encoding="utf-8")
        (args.output_dir / "report.md").write_text(markdown_text, encoding="utf-8")
    else:
        print(json_text)

    print(f"release_decision={report.release_decision}", file=sys.stderr)
    return 0 if report.release_decision == "RELEASE_READY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
