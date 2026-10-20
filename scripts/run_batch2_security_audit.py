#!/usr/bin/env python3
"""Run the Batch 2 release-readiness security harness (local-only).

Engineering acceptance only. ``security_pass`` is never scientific PASS.

Example::

    PYTHONPATH=. python scripts/run_batch2_security_audit.py \\
      --output artifacts/batch2_security
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from tools.release_readiness.batch2_security.report import dumps, write_reports
from tools.release_readiness.batch2_security.runner import run_security_suite
from tools.release_readiness.batch2_security.schema import EXIT_OK, EXIT_SECURITY_FAIL, EXIT_USAGE


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--output",
        default="artifacts/batch2_security",
        help="Directory for machine-readable JSON + Markdown reports.",
    )
    p.add_argument(
        "--work-root",
        default=None,
        help="Scratch directory for path-containment / symlink fixtures.",
    )
    p.add_argument("--json-stdout", action="store_true")
    return p.parse_args(argv)


def main(argv=None) -> int:
    try:
        args = parse_args(argv)
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else EXIT_USAGE
        return code if code is not None else EXIT_USAGE

    work_root = Path(args.work_root) if args.work_root else Path(args.output) / "_work"
    payload = run_security_suite(work_root=work_root)
    # Report destination is a trusted local path for this CLI. Callers that
    # need containment must pass trusted_root to write_reports. This is a
    # local harness boundary, not a repository-wide security claim.
    paths = write_reports(payload, args.output)

    if args.json_stdout:
        print(dumps(payload))
    else:
        print(f"security_pass={payload.get('security_pass')}")
        print(f"scientific_pass_emitted={payload.get('scientific_pass_emitted')}")
        print(f"network_accessed={payload.get('network_accessed')}")
        print(f"rea_status={payload.get('rea_status')}")
        print(f"n_checks={payload.get('n_checks')}")
        print(f"checks_passed={payload.get('checks_passed')}")
        print(f"deterministic={payload.get('deterministic')}")
        for row in payload.get("check_matrix") or []:
            print(f"  {row['check_id']}: passed={row['passed']}")
        for label, pth in paths.items():
            print(f"wrote {label}={pth}")
        print(
            "NOTE: A passing security harness does not establish scientific validity "
            "or repository-wide compliance."
        )

    return EXIT_OK if payload.get("security_pass") else EXIT_SECURITY_FAIL


if __name__ == "__main__":
    raise SystemExit(main())
