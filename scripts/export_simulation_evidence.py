"""Export deterministic lineage reports from an existing simulation run directory."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.simulation_artifacts.extractor import extract_run, render_markdown  # noqa: E402
from tools.simulation_artifacts.models import dumps_finite  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--markdown-out", type=Path)
    parser.add_argument("--previous-manifest", type=Path)
    parser.add_argument("--ledger-reference", type=Path)
    args = parser.parse_args()
    report = extract_run(args.run_dir, previous_manifest=args.previous_manifest, ledger_reference=args.ledger_reference)
    json_text = dumps_finite(report)
    markdown_text = render_markdown(report)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json_text, encoding="utf-8")
    else:
        print(json_text, end="")
    if args.markdown_out:
        args.markdown_out.parent.mkdir(parents=True, exist_ok=True)
        args.markdown_out.write_text(markdown_text, encoding="utf-8")
    return 0 if report["status"] == "COMPLETE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
