"""Command-line interface for narrowband phase-uncertainty calibration audit.

Executes candidate estimator over synthetic fixture battery, measures coverage/bias,
and emits structured JSON audit reports.
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from .calibration import evaluate_phase_uncertainty_calibration
from .candidate_estimator import estimate_narrowband_phase_uncertainty
from .fixtures import get_all_calibration_fixtures


def run_full_calibration_audit(n_bins: int = 5) -> dict[str, Any]:
    """Execute calibration evaluation across all standard synthetic fixtures."""
    fixtures = get_all_calibration_fixtures()

    report: dict[str, Any] = {
        "audit_version": "1.0.0",
        "estimator_candidate": "round6_narrowband_phase_uncertainty",
        "candidate_execution_status": "reconstructed_from_contract_not_previously_executed",
        "total_fixtures": len(fixtures),
        "fixture_reports": {},
        "aggregate_summary": {
            "overconfident_fixtures": 0,
            "conservative_fixtures": 0,
            "well_calibrated_fixtures": 0,
        },
    }

    for fix in fixtures:
        res = estimate_narrowband_phase_uncertainty(fix.signal, fs=fix.fs)
        cal = evaluate_phase_uncertainty_calibration(
            res,
            fix.true_phase,
            fixture_id=fix.fixture_id,
            n_bins=n_bins,
        )
        report["fixture_reports"][fix.fixture_id] = cal.to_dict()

        verdict = cal.overall_verdict
        if verdict == "overconfident":
            report["aggregate_summary"]["overconfident_fixtures"] += 1
        elif verdict == "conservative":
            report["aggregate_summary"]["conservative_fixtures"] += 1
        elif verdict == "well_calibrated":
            report["aggregate_summary"]["well_calibrated_fixtures"] += 1

    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Narrowband Phase Uncertainty Calibration CLI")
    parser.add_argument("--output", type=str, default="", help="Path to write JSON report")
    parser.add_argument("--bins", type=int, default=5, help="Number of predicted-uncertainty bins")
    args = parser.parse_args()

    audit_result = run_full_calibration_audit(n_bins=args.bins)
    json_str = json.dumps(audit_result, indent=2, allow_nan=False)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(json_str)
        print(f"Calibration report written to {args.output}")
    else:
        print(json_str)

    sys.exit(0)


if __name__ == "__main__":
    main()
