"""Command-line interface for binomial operating-characteristic planning.

Provides quick evaluation of Wilson score intervals and sample size requirements
for binomial operating characteristics (such as FPR and TPR).
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Sequence

from .planner import plan_sample_size, plan_zero_event_sample_size, zero_event_upper_bound
from .wilson import wilson_score_interval


def _format_result(data: dict) -> str:
    """Format dictionary result as pretty-printed JSON."""
    return json.dumps(data, indent=2)


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entrypoint for binomial planning and Wilson interval inspection."""
    parser = argparse.ArgumentParser(
        prog="python -m analysis.binomial_planning.cli",
        description="Binomial operating-characteristic planning and Wilson interval utility.",
    )
    subparsers = parser.add_subparsers(dest="command", help="Sub-command to execute")

    # 1. Interval evaluation command
    interval_parser = subparsers.add_parser("interval", help="Compute Wilson score interval")
    interval_parser.add_argument("-k", "--events", type=int, required=True, help="Observed events count (k)")
    interval_parser.add_argument("-n", "--trials", type=int, required=True, help="Total evaluation trials (n)")
    interval_parser.add_argument("-c", "--confidence", type=float, default=0.95, help="Confidence level (default 0.95)")
    interval_parser.add_argument("-z", type=float, default=None, help="Explicit normal critical value (overrides confidence)")
    interval_parser.add_argument("--cc", action="store_true", help="Apply continuity correction")

    # 2. Zero-event planning command
    zero_parser = subparsers.add_parser("plan-zero", help="Plan sample size for zero observed events")
    zero_parser.add_argument("-t", "--target", type=float, required=True, help="Target upper bound (e.g. 0.05 for 5% FPR)")
    zero_parser.add_argument("-c", "--confidence", type=float, default=0.95, help="Confidence level (default 0.95)")
    zero_parser.add_argument("-z", type=float, default=None, help="Explicit normal critical value")
    zero_parser.add_argument("--max-n", type=int, default=10_000_000, help="Maximum search bound")

    # 3. Precision width planning command
    width_parser = subparsers.add_parser("plan-width", help="Plan sample size for target interval width")
    width_parser.add_argument("-w", "--width", type=float, required=True, help="Target interval width")
    width_parser.add_argument("-p", "--design-p", type=float, default=None, help="Design proportion (if None, uniform worst-case p=0.5)")
    width_parser.add_argument("--half-width", action="store_true", help="Interpret width as half-width (margin of error)")
    width_parser.add_argument("-c", "--confidence", type=float, default=0.95, help="Confidence level (default 0.95)")
    width_parser.add_argument("-z", type=float, default=None, help="Explicit normal critical value")
    width_parser.add_argument("--max-n", type=int, default=10_000_000, help="Maximum search bound")

    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 1

    try:
        if args.command == "interval":
            res = wilson_score_interval(
                k=args.events,
                n=args.trials,
                confidence_level=args.confidence,
                z=args.z,
                continuity_correction=args.cc,
            )
            payload = {
                "k": res.k,
                "n": res.n,
                "proportion": res.proportion,
                "confidence_level": res.confidence_level,
                "z": res.z,
                "lower": res.lower,
                "upper": res.upper,
                "half_width": res.half_width,
                "full_width": res.full_width,
                "status": res.status,
                "is_available": res.is_available,
                "continuity_corrected": res.continuity_corrected,
            }
            print(_format_result(payload))
            return 0

        elif args.command == "plan-zero":
            plan = plan_zero_event_sample_size(
                target_upper=args.target,
                confidence_level=args.confidence,
                z=args.z,
                max_n=args.max_n,
            )
            payload = {
                "target_metric": plan.target_metric,
                "target_threshold": plan.target_threshold,
                "confidence_level": plan.confidence_level,
                "z": plan.z,
                "required_n": plan.required_n,
                "achieved_metric_value": plan.achieved_metric_value,
                "status": plan.status,
            }
            print(_format_result(payload))
            return 0

        elif args.command == "plan-width":
            plan = plan_sample_size(
                target_width=args.width,
                design_p=args.design_p,
                is_half_width=args.half_width,
                confidence_level=args.confidence,
                z=args.z,
                max_n=args.max_n,
            )
            payload = {
                "target_metric": plan.target_metric,
                "target_threshold": plan.target_threshold,
                "design_proportion": plan.design_proportion,
                "guarantee_type": plan.guarantee_type,
                "confidence_level": plan.confidence_level,
                "z": plan.z,
                "required_n": plan.required_n,
                "achieved_metric_value": plan.achieved_metric_value,
                "status": plan.status,
            }
            print(_format_result(payload))
            return 0

    except (ValueError, TypeError) as exc:
        sys.stderr.write(f"Error: {exc}\n")
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
