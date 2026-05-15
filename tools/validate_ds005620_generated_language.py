#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate DS005620 generated-output ontology claim language in strict mode.")
    parser.add_argument("--root", default=".")
    parser.add_argument("--json-out", default="outputs/btc_icft/ds005620_generated_language_validation.json")
    parser.add_argument("--markdown-out", default="outputs/btc_icft/ds005620_generated_language_validation.md")
    args = parser.parse_args()

    cmd = [
        sys.executable,
        "tools/validate_ontology_claim_language.py",
        "--root", args.root,
        "--scan-mode", "generated",
        "--generated-output-profile", "ds005620",
        "--strict-outputs",
        "--no-baseline",
        "--json-out", args.json_out,
        "--markdown-out", args.markdown_out,
    ]
    return subprocess.run(cmd, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
