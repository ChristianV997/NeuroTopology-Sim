"""Run the offline empirical higher-order forecasting harness."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis.empirical_higher_order.runner import run_empirical
from analysis.empirical_higher_order.schema import finite_json


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = run_empirical(args.manifest)
    payload = finite_json(report)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0 if report["status"] in {"READY_FOR_DESCRIPTIVE_ANALYSIS", "READY_FOR_FORECASTING", "INSUFFICIENT_PAIRED_SUBJECTS", "SYNTHETIC_DEMO_ONLY"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
