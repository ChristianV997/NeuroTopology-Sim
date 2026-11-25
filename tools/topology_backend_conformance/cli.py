"""Command-line harness for TDA backend semantic conformance.

Runs the deterministic synthetic fixture suite across all probed backends,
validates comparability invariants, tests permutation invariance, and outputs
structured, finite JSON reports.
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any
import numpy as np

from .adapters import get_all_adapters
from .comparator import compare_conformance_runs, validate_mathematical_comparability
from .fixtures import (
    get_all_conformance_fixtures,
    make_filled_triangle_fixture,
    make_known_loop_fixture,
    make_reordered_fixture,
    make_threshold_boundary_fixture,
)
from .models import (
    ComparabilityStatus,
    ConformanceExecutionConfig,
    FiltrationType,
    MetricConvention,
    sanitize_float,
)


def run_conformance_audit(
    max_dimension: int = 1,
    tolerance: float = 1e-5,
) -> dict[str, Any]:
    """Execute complete semantic conformance audit across all probed adapters."""
    adapters = get_all_adapters()
    fixtures = get_all_conformance_fixtures()

    report: dict[str, Any] = {
        "conformance_version": "1.0.0",
        "parameters": {
            "max_dimension": max_dimension,
            "tolerance": tolerance,
        },
        "backends": {},
        "fixture_runs": {},
        "comparisons": [],
        "invariant_verifications": {},
        "summary": {
            "total_fixtures": len(fixtures),
            "probed_backends": len(adapters),
            "available_backends": 0,
            "passed_conformance": True,
        },
    }

    # 1. Probe backend availability and metadata
    for bid, adapter in adapters.items():
        meta = adapter.get_metadata()
        report["backends"][bid] = meta.to_dict()
        if meta.is_available:
            report["summary"]["available_backends"] += 1

    # 2. Run fixtures across available backends
    ref_adapter = adapters["reference_simplicial"]
    for fix in fixtures:
        cfg = fix.get_config(max_dimension=max_dimension, tolerance=tolerance)
        fix_entry: dict[str, Any] = {
            "description": fix.description,
            "filtration_type": fix.filtration_type.value,
            "metric_convention": fix.metric_convention.value,
            "is_degenerate": fix.is_degenerate,
            "backend_results": {},
        }

        # Run on reference engine if Vietoris-Rips
        if fix.filtration_type == FiltrationType.VIETORIS_RIPS:
            run_ref = ref_adapter.compute(fix.data, cfg)
            fix_entry["backend_results"]["reference_simplicial"] = run_ref.to_dict()

        for bid, adapter in adapters.items():
            if bid == "reference_simplicial":
                continue
            if fix.filtration_type in adapter.supported_filtrations and adapter.is_available():
                run_res = adapter.compute(fix.data, cfg)
                fix_entry["backend_results"][bid] = run_res.to_dict()

                # Compare against reference
                if fix.filtration_type == FiltrationType.VIETORIS_RIPS:
                    cmp_res = compare_conformance_runs(run_ref, run_res, dimension=1, tolerance=tolerance)
                    report["comparisons"].append({
                        "fixture_id": fix.fixture_id,
                        "backend_a": "reference_simplicial",
                        "backend_b": bid,
                        "dimension": 1,
                        "result": cmp_res.to_dict(),
                    })
                    if not cmp_res.passed_tolerance:
                        report["summary"]["passed_conformance"] = False

        report["fixture_runs"][fix.fixture_id] = fix_entry

    # 3. Verify Permutation Invariance on Known Loop
    loop_fix = make_known_loop_fixture()
    loop_cfg = loop_fix.get_config(max_dimension=1, tolerance=tolerance)
    reord_fix = make_reordered_fixture(loop_fix, [2, 0, 3, 1])

    ref_orig = ref_adapter.compute(loop_fix.data, loop_cfg)
    ref_perm = ref_adapter.compute(reord_fix.data, loop_cfg)
    perm_cmp = compare_conformance_runs(ref_orig, ref_perm, dimension=1, tolerance=tolerance)
    report["invariant_verifications"]["permutation_invariance"] = {
        "passed": perm_cmp.passed_tolerance,
        "bottleneck_distance": perm_cmp.bottleneck_distance,
        "details": perm_cmp.details,
    }
    if not perm_cmp.passed_tolerance:
        report["summary"]["passed_conformance"] = False

    # 4. Verify Non-Comparable Rejection Invariant
    cfg_rips = ConformanceExecutionConfig(
        filtration_type=FiltrationType.VIETORIS_RIPS,
        metric_convention=MetricConvention.PRECOMPUTED_DISTANCE_MATRIX,
    )
    cfg_cubical = ConformanceExecutionConfig(
        filtration_type=FiltrationType.CUBICAL_SUBLEVEL,
        metric_convention=MetricConvention.GRID_SCALAR_SUBLEVEL,
    )
    comp_status, comp_reasons = validate_mathematical_comparability(cfg_rips, cfg_cubical)
    non_comp_passed = (comp_status == ComparabilityStatus.NOT_COMPARABLE) and len(comp_reasons) > 0
    report["invariant_verifications"]["non_comparable_filtration_rejection"] = {
        "passed": non_comp_passed,
        "status": comp_status.value,
        "reasons": comp_reasons,
    }
    if not non_comp_passed:
        report["summary"]["passed_conformance"] = False

    # 5. Verify Threshold Boundary Invariant
    thresh_fix = make_threshold_boundary_fixture(threshold=1.2)
    thresh_cfg = thresh_fix.get_config(max_dimension=1, tolerance=tolerance)
    run_thresh = ref_adapter.compute(thresh_fix.data, thresh_cfg)
    h1_bars = run_thresh.get_bars(1)
    thresh_passed = len(h1_bars) == 1 and h1_bars[0].is_infinite and h1_bars[0].birth == 1.0
    report["invariant_verifications"]["threshold_boundary_truncation"] = {
        "passed": thresh_passed,
        "h1_bar_birth": h1_bars[0].birth if h1_bars else None,
        "h1_bar_is_infinite": h1_bars[0].is_infinite if h1_bars else None,
    }
    if not thresh_passed:
        report["summary"]["passed_conformance"] = False

    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="TDA Backend Semantic Conformance Audit CLI")
    parser.add_argument("--output", type=str, default="", help="Path to write JSON conformance report")
    parser.add_argument("--tolerance", type=float, default=1e-5, help="Bottleneck tolerance")
    parser.add_argument("--max-dim", type=int, default=1, help="Max homology dimension")
    args = parser.parse_args()

    report = run_conformance_audit(max_dimension=args.max_dim, tolerance=args.tolerance)
    json_str = json.dumps(report, indent=2, allow_nan=False)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(json_str)
        print(f"Conformance report written to {args.output}")
    else:
        print(json_str)

    passed = report["summary"]["passed_conformance"]
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
