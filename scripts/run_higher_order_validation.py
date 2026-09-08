#!/usr/bin/env python
"""Run the higher-order adversarial validation suite (engineering evidence only).

Never emits a scientific PASS or formal Bayes factor.

Example::

    PYTHONPATH=. python scripts/run_higher_order_validation.py \\
      --seed 0 --output artifacts/higher_order_validation
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from tools.higher_order_validation.report import suite_to_dict, write_reports
from tools.higher_order_validation.suite import run_validation_suite


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--output", type=str, default="artifacts/higher_order_validation")
    p.add_argument("--json-stdout", action="store_true")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    results = run_validation_suite(seed=args.seed)
    payload = suite_to_dict(
        results,
        meta={"seed": args.seed, "cli": "run_higher_order_validation"},
    )
    paths = write_reports(payload, args.output)
    if args.json_stdout:
        from tools.higher_order_validation.report import dumps

        print(dumps(payload))
    else:
        print("higher-order adversarial validation")
        print(f"  n_cases={payload['n_cases']}")
        print(f"  counts={payload['counts']}")
        print(f"  scientific_pass_emitted={payload['scientific_pass_emitted']}")
        print(f"  formal_bayes_factor_emitted={payload['formal_bayes_factor_emitted']}")
        print(f"  wrote {paths['json']}")
        print(f"  wrote {paths['markdown']}")

    # Engineering exit: 0 if no ERROR outcomes; 1 if any ERROR; never implies scientific PASS.
    if any(r.outcome.value == "ERROR" for r in results):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
