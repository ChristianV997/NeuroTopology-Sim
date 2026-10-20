#!/usr/bin/env python3
"""CLI runner for Round 6 train/test whitening audit.

Usage:
    python scripts/audit_round6_whitening.py [--method cholesky|zca] [--json-out PATH] [--md-out PATH]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools.whitening_audit.audit_reporter import generate_markdown_audit_report
from tools.whitening_audit.leakage_detector import run_leakage_regression_fixture
from tools.whitening_audit.synthetic_data import (
    generate_baseline_dataset,
    generate_mean_shifted_test_set,
)
from tools.whitening_audit.types import WhiteningMethod
from tools.whitening_audit.whitening_verifier import audit_whitening_pipeline


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--method",
        choices=["cholesky", "zca"],
        default="cholesky",
        help="Whitening transform method (default: cholesky)",
    )
    parser.add_argument(
        "--eigenvalue-floor",
        type=float,
        default=1e-6,
        help="Floor for SPD covariance projection (default: 1e-6)",
    )
    parser.add_argument(
        "--json-out",
        type=Path,
        default=None,
        help="Optional path to write structured JSON audit artifact",
    )
    parser.add_argument(
        "--md-out",
        type=Path,
        default=None,
        help="Optional path to write markdown audit report",
    )
    args = parser.parse_args()

    def _confine_output(path: Path) -> Path:
        """Refuse writes outside the repository root (path-traversal boundary)."""
        resolved = path.expanduser().resolve()
        root = _REPO_ROOT.resolve()
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise SystemExit(
                f"refusing to write outside repository root ({root}): {path}"
            ) from exc
        return resolved

    if args.json_out is not None:
        args.json_out = _confine_output(args.json_out)
    if args.md_out is not None:
        args.md_out = _confine_output(args.md_out)

    whitening_method = WhiteningMethod(args.method)
    print(f"[*] Running Round 6 Whitening Audit with method={whitening_method.value}...")

    # 1. Generate synthetic baseline datasets
    X_train, X_test = generate_baseline_dataset(
        n_train=120, n_test=60, n_features=4, seed=42
    )

    # 2. Run pipeline audit
    audit_res = audit_whitening_pipeline(
        X_train=X_train,
        X_test=X_test,
        method=whitening_method,
        eigenvalue_floor=args.eigenvalue_floor,
    )

    # 3. Run leakage regression fixture with shifted test set
    X_test_shifted = generate_mean_shifted_test_set(X_train, shift_magnitude=3.0)
    leakage_res = run_leakage_regression_fixture(
        X_train=X_train,
        X_test=X_test_shifted,
        method=whitening_method,
        eigenvalue_floor=args.eigenvalue_floor,
    )

    # Attach leakage check to audit result
    audit_dict = audit_res.to_dict()
    audit_dict["leakage_check"] = leakage_res.to_dict()

    # Regenerate report with leakage info
    class _CombinedResult:
        def __init__(self, d):
            self.status = audit_res.status
            self.candidate_code_present = audit_res.candidate_code_present
            self.whitening_method = audit_res.whitening_method
            self.n_train_samples = audit_res.n_train_samples
            self.n_test_samples = audit_res.n_test_samples
            self.n_features = audit_res.n_features
            self.in_sample_error = audit_res.in_sample_error
            self.out_of_sample_error = audit_res.out_of_sample_error
            self.spd_report = audit_res.spd_report
            self.method_comparison = audit_res.method_comparison
            self.leakage_check = leakage_res

    combined = _CombinedResult(audit_dict)
    md_report = generate_markdown_audit_report(combined)  # type: ignore

    # Print summary findings to stdout
    print(f"[+] Audit Status: {audit_res.status.value}")
    print(f"[+] In-sample Covariance Error: {audit_res.in_sample_error:.6e}")
    print(f"[+] Out-of-sample Covariance Error: {audit_res.out_of_sample_error:.6e}")
    print(f"[+] SPD Raw Min Eigenvalue: {audit_res.spd_report.raw_min_eigenvalue:.6e}")
    print(f"[+] SPD Correction Frobenius Norm: {audit_res.spd_report.correction_frobenius_norm:.6e}")
    if audit_res.method_comparison:
        print(f"[+] W_chol vs W_zca Frobenius Difference: {audit_res.method_comparison.transform_matrix_frobenius_difference:.6f}")
        print(f"[+] W_chol vs W_zca Rotation Norm from Identity: {audit_res.method_comparison.rotation_deviation_from_identity:.6f}")
        print(f"[+] Are Methods Equivalent: {audit_res.method_comparison.are_methods_equivalent}")
    print(f"[+] Leakage Detected in Controlled Test: {leakage_res.leakage_detected}")

    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(audit_dict, indent=2, allow_nan=False), encoding="utf-8")
        print(f"[+] Wrote JSON artifact to {args.json_out}")

    if args.md_out:
        args.md_out.parent.mkdir(parents=True, exist_ok=True)
        args.md_out.write_text(md_report, encoding="utf-8")
        print(f"[+] Wrote Markdown report to {args.md_out}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
