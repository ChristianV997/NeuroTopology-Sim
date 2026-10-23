"""CLI: ``python -m tools.mne_csd_reference_audit [--json-out PATH]``.

Writes the reference-audit report as strict, sorted JSON. Pure NumPy; never imports MNE.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .report import build_report, to_json


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json-out", type=Path, default=None)
    args = parser.parse_args(argv)
    text = to_json(build_report())
    if args.json_out:
        args.json_out.write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
