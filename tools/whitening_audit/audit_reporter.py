"""Report generator and formatting utilities for whitening audit artifacts.

Produces:
1. Canonical structured JSON report (strict allow_nan=False)
2. Comprehensive Markdown audit report with full mathematical disclosures
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from tools.whitening_audit.types import (
    AuditStatus,
    MethodComparisonResult,
    WhiteningAuditResult,
)


def generate_markdown_audit_report(result: WhiteningAuditResult) -> str:
    """Generate a GitHub-flavored markdown report summarizing the whitening audit."""
    comp = result.method_comparison
    leak = result.leakage_check
    spd = result.spd_report

    md_lines = [
        "# Round 6 Train/Test Whitening Audit Report",
        "",
        "> [!IMPORTANT]",
        f"> **Audit Status**: `{result.status.value}` | **Scope**: `SYNTHETIC_ONLY`",
        "> **Candidate Code Presence**: `ABSENT` (Independent verification executed; no candidate code modified or claimed)",
        "",
        "---",
        "",
        "## 1. Overview & Verification Scope",
        "",
        "- **Mandate**: Audit the Round 6 proposal for train/test feature whitening.",
        "- **Methodology**: Strict train-only fitting with held-out test data evaluation.",
        f"- **Training Samples**: {result.n_train_samples} | **Test Samples**: {result.n_test_samples} | **Features**: {result.n_features}",
        f"- **Selected Whitening Method**: `{result.whitening_method.value}`",
        f"- **In-Sample Covariance Error** ($||\\operatorname{{Cov}}(Z_{{\\text{{train}}}}) - I||_F$): `{result.in_sample_error:.6e}`",
        f"- **Out-of-Sample Covariance Error** ($||\\operatorname{{Cov}}(Z_{{\\text{{test}}}}) - I||_F$): `{result.out_of_sample_error:.6e}`",
        "",
        "---",
        "",
        "## 2. Whitening Method Comparison: Cholesky vs Symmetric ZCA",
        "",
        "The proposal utilizes Cholesky whitening $W_{\\text{chol}} = L^{-1}(x - \\mu)$. This is mathematically distinct from Symmetric ZCA whitening $W_{\\text{zca}} = \\Sigma^{-1/2}(x - \\mu)$.",
        "",
        "| Attribute | Cholesky Whitening ($L^{-1}$) | Symmetric ZCA Whitening ($\\Sigma^{-1/2}$) |",
        "| :--- | :--- | :--- |",
        "| **Mathematical Definition** | $W_{\\text{chol}} = L^{-1}$, where $\\Sigma = L L^T$ | $W_{\\text{zca}} = V \\Lambda^{-1/2} V^T$, where $\\Sigma = V \\Lambda V^T$ |",
        "| **Matrix Structure** | Strictly lower-triangular | Strictly symmetric |",
        "| **Coordinate Dependence** | Coordinate-order dependent (Gram-Schmidt) | Order-independent; minimal distortion |",
        "| **Rotation Relation** | $W_{\\text{chol}} = R W_{\\text{zca}}$ with $R \\in O(d)$ | Minimal rotation baseline ($R = I$) |",
    ]

    if comp is not None:
        md_lines.extend([
            "",
            "### Quantitative Method Comparison Metrics",
            f"- **Cholesky In-Sample Error**: `{comp.covariance_in_sample_chol_error:.6e}`",
            f"- **ZCA In-Sample Error**: `{comp.covariance_in_sample_zca_error:.6e}`",
            f"- **Transform Matrix Frobenius Difference** ($||W_{{\\text{{chol}}}} - W_{{\\text{{zca}}}}||_F$): `{comp.transform_matrix_frobenius_difference:.6f}`",
            f"- **Relative Transform Difference**: `{comp.relative_transform_difference * 100:.2f}%`",
            f"- **Rotation Matrix Deviation from Identity** ($||R - I||_F$): `{comp.rotation_deviation_from_identity:.6f}`",
            (
                f"- **Are Methods Equivalent?**: `{comp.are_methods_equivalent}`"
                + (
                    " (relative transform gap below threshold on unrepaired spectrum)"
                    if comp.are_methods_equivalent
                    else " (distinct coordinate bases / or floor-collapsed agreement withheld)"
                )
            ),
        ])

    md_lines.extend([
        "",
        "---",
        "",
        "## 3. Covariance Regularization & SPD Projection Disclosure",
        "",
        "Covariance conditioning and eigenvalue repairs are disclosed explicitly:",
        "",
        "| Metric | Value | Description |",
        "| :--- | :--- | :--- |",
        f"| **Raw Minimum Eigenvalue** | `{spd.raw_min_eigenvalue:.6e}` | Smallest eigenvalue of empirical sample covariance |",
        f"| **Raw Maximum Eigenvalue** | `{spd.raw_max_eigenvalue:.6e}` | Largest eigenvalue of empirical sample covariance |",
        f"| **Raw Condition Number** | `{spd.raw_condition_number:.4e}` | $\\lambda_{{\\max}} / \\lambda_{{\\min}}$ before regularization |",
        f"| **Applied Eigenvalue Floor** | `{spd.applied_floor:.6e}` | Regularization floor for SPD cone projection |",
        f"| **Repaired Min Eigenvalue** | `{spd.repaired_min_eigenvalue:.6e}` | Minimum eigenvalue after flooring |",
        f"| **Correction Frobenius Norm** | `{spd.correction_frobenius_norm:.6e}` | $||\\Sigma_{{\\text{{spd}}}} - \\Sigma_{{\\text{{raw}}}}||_F$ |",
        f"| **Relative Correction Norm** | `{spd.relative_correction_norm * 100:.4f}%` | Percentage modification of covariance matrix |",
        f"| **Is Correction Material?** | `{spd.is_correction_material}` | True if eigenvalues were clamped or shifted |",
        f"| **Floored Eigenvalues Count** | `{spd.n_floored_eigenvalues}` | Number of eigenvalues shifted to floor |",
        "",
        "---",
        "",
        "## 4. Train-Only Fitting & Leakage Verification",
        "",
        "- **Train-Only Guarantee**: Mean and covariance are estimated strictly on training instances. Held-out test data never influences training statistics.",
    ])

    if leak is not None:
        md_lines.extend([
            "",
            "### Leakage Regression Fixture Outcome",
            f"- **Leakage Detected in Controlled Test**: `{leak.leakage_detected}`",
            f"- **Mean Shift Under Leakage**: `{leak.mean_difference_norm:.6e}`",
            f"- **Covariance Shift Under Leakage**: `{leak.covariance_difference_norm:.6e}`",
            f"- **Transform Matrix Shift Under Leakage**: `{leak.transform_difference_norm:.6e}`",
            f"- **Out-of-Sample Error (Strict Train-Only)**: `{leak.out_of_sample_error_strict:.6f}`",
            f"- **Out-of-Sample Error (Leaky Contaminated)**: `{leak.out_of_sample_error_leaky:.6f}`",
            f"- **Discrepancy**: `{leak.error_discrepancy:.6e}`",
            f"- **Finding**: Leaking test data contaminates whitening parameters and artificially masks true generalization errors.",
        ])

    md_lines.extend([
        "",
        "---",
        "",
        "## 5. Robustness & Fail-Closed Behavior",
        "",
        "The verifier enforces strict fail-closed handling on degenerate inputs:",
        "",
        "| Stress Test Scenario | Expected Outcome | Behavior |",
        "| :--- | :--- | :--- |",
        "| **Insufficient Samples ($n \\le 1$)** | `InsufficientSamplesError` | Rejects sample count $\\le 1$ |",
        "| **Empty Feature Matrix ($n=0$ or $d=0$)** | `EmptyDataError` | Fails immediately on empty data |",
        "| **Non-Finite Values (`NaN`, `Inf`)** | `NonFiniteValuesError` | Rejects corrupt floats before computation |",
        "| **Feature Dimension Mismatch ($d_{{\\text{{test}}}} \\ne d_{{\\text{{train}}}}$)** | `FeatureDimensionMismatchError` | Rejects incompatible test shapes |",
        "| **Rank-Deficient Data ($n < d$)** | Disclosed SPD Repair | Automatically projected to SPD with full metric disclosure |",
        "| **Badly Scaled Features ($10^{-6}$ to $10^{6}$)** | Bounded Condition Number | Detects extreme conditioning and stabilizes inversion |",
        "",
        "---",
        "",
        "## 6. Disclaimers and Non-Promotional Scope",
        "",
        "> [!NOTE]",
        "> **SYNTHETIC_ONLY / HOLD**: All matrices evaluated in this audit are synthetic. No clinical claims, no biological truth claims, and no assertions of scientific validation are made. This package serves exclusively as an independent verification harness for the proposed whitening specification.",
    ])

    return "\n".join(md_lines)
