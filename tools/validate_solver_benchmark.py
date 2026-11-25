#!/usr/bin/env python3
"""Validator CLI for simulation solver benchmark telemetry files.

Verifies:
- RFC 8259 finite JSON compliance (zero NaN/Infinity).
- Companion .sha256 cryptographic digest match.
- Presence of solver performance metrics and guardrails.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Optional, Sequence

# Ensure repository root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from analysis.serialization import verify_telemetry_digest


def validate_benchmark_file(path: str | Path) -> bool:
    """Validate format, schema, finite numbers, and checksum of benchmark artifact."""
    p = Path(path).resolve()
    print(f"Validating benchmark artifact: {p}")

    # 1. Verify existence
    if not p.is_file():
        print(f"[FAIL] Benchmark file does not exist: {p}")
        return False

    # 2. Verify cryptographic SHA-256 digest
    valid_sha, sha_msg = verify_telemetry_digest(p)
    if not valid_sha:
        print(f"[FAIL] SHA-256 verification failed: {sha_msg}")
        return False
    print(f"[PASS] {sha_msg}")

    # 3. Verify RFC 8259 finite JSON
    try:
        content = p.read_text(encoding="utf-8")
        data = json.loads(content, parse_constant=lambda c: (_ for _ in ()).throw(ValueError(f"Invalid JSON constant: {c}")))
    except Exception as exc:
        print(f"[FAIL] JSON parsing or non-finite constant error: {exc}")
        return False

    # 4. Required schema fields
    required_keys = ["timestamp_utc", "solvers_benchmark", "guardrails"]
    missing = [k for k in required_keys if k not in data]
    if missing:
        print(f"[FAIL] Missing required keys: {missing}")
        return False

    # 5. Guardrail assertion
    guardrails = data.get("guardrails", {})
    if not guardrails.get("no_clinical_claims") or not guardrails.get("no_toe_claim"):
        print("[FAIL] Missing mandatory repository guardrail declarations.")
        return False

    print("[PASS] Benchmark telemetry schema, finite numbers, and guardrails verified successfully.")
    return True


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Validate solver benchmark telemetry artifact.")
    parser.add_argument("path", help="Path to simulation_solver_benchmark.json")
    args = parser.parse_args(argv)

    success = validate_benchmark_file(args.path)
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
