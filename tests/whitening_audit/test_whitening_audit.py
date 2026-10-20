"""Comprehensive test suite for Round 6 train/test whitening audit.

Tests:
1. Train-only fitting with held-out data from same distribution.
2. Train-only fitting with shifted mean.
3. Train-only fitting with shifted covariance.
4. Train-only fitting with rank-deficient data (n < d).
5. Train-only fitting with collinear features.
6. Fail-closed handling of insufficient samples (n <= 1).
7. Fail-closed handling of non-finite values (NaN, Inf).
8. Fail-closed handling of feature dimension mismatch.
9. Badly scaled features robustness.
10. Strict test data isolation (zero leakage).
11. Leakage regression fixture (detects contaminated fitting).
12. Cholesky whitening vs Symmetric ZCA comparison (rotation difference).
13. SPD repair full disclosure (raw min eigenvalue, applied floor, correction norm).
14. Deterministic replay bit-for-bit.
15. Strict finite JSON serialization.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
import sys
import unittest

# Ensure repo root is on sys.path
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools.whitening_audit.leakage_detector import (
    run_leakage_regression_fixture,
)
from tools.whitening_audit.matrix_ops import (
    compute_covariance,
    compute_mean,
    matrix_frobenius_norm,
    project_spd_covariance,
)
from tools.whitening_audit.synthetic_data import (
    generate_badly_scaled_dataset,
    generate_baseline_dataset,
    generate_collinear_dataset,
    generate_covariance_shifted_test_set,
    generate_mean_shifted_test_set,
    generate_nonfinite_dataset,
    generate_rank_deficient_dataset,
)
from tools.whitening_audit.types import (
    AuditStatus,
    EmptyDataError,
    FeatureDimensionMismatchError,
    InsufficientSamplesError,
    NonFiniteValuesError,
    NonPositiveDefiniteError,
    WhiteningMethod,
)
from tools.whitening_audit.whitening_verifier import (
    TrainOnlyWhiteningModel,
    audit_whitening_pipeline,
    compare_whitening_methods,
)


class TestWhiteningAudit(unittest.TestCase):
    """Test suite verifying train/test whitening mathematical invariants and leakage immunity."""

    def setUp(self) -> None:
        """Create baseline synthetic dataset."""
        self.X_train, self.X_test = generate_baseline_dataset(
            n_train=120, n_test=60, n_features=4, seed=123
        )

    # -------------------------------------------------------------------------
    # 1. Train-Only Fitting: Same Distribution
    # -------------------------------------------------------------------------

    def test_train_only_fitting_same_distribution(self) -> None:
        """Fitting on training data whitens in-sample covariance and generalizes to test."""
        model = TrainOnlyWhiteningModel(method=WhiteningMethod.CHOLESKY)
        result = model.fit(self.X_train)

        self.assertLess(result.in_sample_error, 1e-10)
        self.assertEqual(result.n_train_samples, 120)
        self.assertEqual(result.n_features, 4)

        # Evaluate out-of-sample error on test data from same distribution
        out_err = model.evaluate_out_of_sample_error(self.X_test)
        self.assertTrue(math.isfinite(out_err))
        # For n=60 samples from same distribution, sampling error is moderate
        self.assertLess(out_err, 1.5)

    # -------------------------------------------------------------------------
    # 2. Train-Only Fitting: Shifted Mean
    # -------------------------------------------------------------------------

    def test_train_only_fitting_shifted_mean(self) -> None:
        """Shifted test mean does not alter train parameters; increases out-of-sample error."""
        model = TrainOnlyWhiteningModel(method=WhiteningMethod.CHOLESKY)
        model.fit(self.X_train)
        fitted_mean_before = model.mean

        X_test_shifted = generate_mean_shifted_test_set(self.X_train, shift_magnitude=5.0)
        Z_test = model.transform(X_test_shifted)

        # Model fitted mean is strictly unchanged
        self.assertEqual(model.mean, fitted_mean_before)

        # Transformed test features have non-zero mean due to the shift
        test_z_mean = compute_mean(Z_test)
        test_z_mean_norm = math.sqrt(sum(m * m for m in test_z_mean))
        self.assertGreater(test_z_mean_norm, 1.0)

    # -------------------------------------------------------------------------
    # 3. Train-Only Fitting: Shifted Covariance
    # -------------------------------------------------------------------------

    def test_train_only_fitting_shifted_covariance(self) -> None:
        """Shifted test covariance produces expected out-of-sample divergence."""
        model = TrainOnlyWhiteningModel(method=WhiteningMethod.CHOLESKY)
        model.fit(self.X_train)

        X_test_cov_shifted = generate_covariance_shifted_test_set(
            n_test=60, n_features=4, scale_factor=3.0, seed=456
        )
        out_err = model.evaluate_out_of_sample_error(X_test_cov_shifted)

        # In-sample error remains pristine
        self.assertLess(model.in_sample_error, 1e-10)
        # Out-of-sample error reflects the 3x scale factor divergence
        self.assertGreater(out_err, 2.0)

    # -------------------------------------------------------------------------
    # 4. Train-Only Fitting: Rank-Deficient Data (n < d)
    # -------------------------------------------------------------------------

    def test_train_only_fitting_rank_deficient(self) -> None:
        """Rank-deficient training data (n < d) triggers disclosed SPD repair."""
        # 5 samples with 8 features
        X_rank_def = generate_rank_deficient_dataset(n_samples=5, n_features=8, seed=789)
        model = TrainOnlyWhiteningModel(method=WhiteningMethod.CHOLESKY, eigenvalue_floor=1e-4)
        result = model.fit(X_rank_def)

        # SPD report must disclose the repair
        spd = result.spd_report
        self.assertTrue(spd.is_correction_material)
        self.assertGreater(spd.n_floored_eigenvalues, 0)
        self.assertLessEqual(spd.raw_min_eigenvalue, 1e-4)
        self.assertGreaterEqual(spd.repaired_min_eigenvalue, 1e-4)
        self.assertGreater(spd.correction_frobenius_norm, 0.0)

        # Transform executes stably without crashing
        Z_train = model.transform(X_rank_def)
        self.assertEqual(len(Z_train), 5)
        self.assertEqual(len(Z_train[0]), 8)

    # -------------------------------------------------------------------------
    # 5. Train-Only Fitting: Collinear Features
    # -------------------------------------------------------------------------

    def test_train_only_fitting_collinear_features(self) -> None:
        """Collinear features with zero eigenvalue are safely floored and disclosed."""
        X_collinear = generate_collinear_dataset(n_samples=50, n_features=4, seed=901)
        model = TrainOnlyWhiteningModel(method=WhiteningMethod.CHOLESKY, eigenvalue_floor=1e-5)
        result = model.fit(X_collinear)

        spd = result.spd_report
        self.assertTrue(spd.is_correction_material)
        self.assertGreaterEqual(spd.n_floored_eigenvalues, 1)
        self.assertAlmostEqual(spd.repaired_min_eigenvalue, 1e-5, delta=1e-8)

    # -------------------------------------------------------------------------
    # 6. Fail-Closed: Insufficient Samples (n <= 1)
    # -------------------------------------------------------------------------

    def test_insufficient_samples_fails_closed(self) -> None:
        """Single-sample (n=1) and empty (n=0) inputs must raise explicit errors."""
        model = TrainOnlyWhiteningModel()

        # n = 1
        with self.assertRaises(InsufficientSamplesError):
            model.fit([[1.0, 2.0, 3.0]])

        # n = 0
        with self.assertRaises(EmptyDataError):
            model.fit([])

    def test_nonpositive_eigenvalue_floor_fails_closed(self) -> None:
        """Regression: floor <= 0 must not reach ZeroDivisionError / silent accept.

        A non-positive floor bypasses the SPD projection contract and can crash
        Cholesky/ZCA with an untyped ZeroDivisionError on singular covariances.
        """
        from tools.whitening_audit.types import WhiteningAuditError

        X_collinear = generate_collinear_dataset(n_samples=40, n_features=4, seed=2)
        for bad_floor in (0.0, -1.0, -1e-6):
            with self.assertRaises(WhiteningAuditError):
                TrainOnlyWhiteningModel(eigenvalue_floor=bad_floor).fit(X_collinear)
            with self.assertRaises(WhiteningAuditError):
                project_spd_covariance([[1.0, 0.0], [0.0, 1.0]], eigenvalue_floor=bad_floor)

    # -------------------------------------------------------------------------
    # 7. Fail-Closed: Non-Finite Values (NaN / Inf)
    # -------------------------------------------------------------------------

    def test_nonfinite_values_rejected(self) -> None:
        """Matrices containing NaN or Inf must fail closed immediately."""
        model = TrainOnlyWhiteningModel()

        X_nan = generate_nonfinite_dataset(inject_type="nan")
        with self.assertRaises(NonFiniteValuesError):
            model.fit(X_nan)

        X_inf = generate_nonfinite_dataset(inject_type="inf")
        with self.assertRaises(NonFiniteValuesError):
            model.fit(X_inf)

    # -------------------------------------------------------------------------
    # 8. Fail-Closed: Feature Dimension Mismatch
    # -------------------------------------------------------------------------

    def test_feature_dimension_mismatch_rejected(self) -> None:
        """Transforming test data with d_test != d_train raises FeatureDimensionMismatchError."""
        model = TrainOnlyWhiteningModel()
        model.fit(self.X_train)  # d = 4

        # Incompatible test data with 3 features
        X_bad_dim = [[1.0, 2.0, 3.0] for _ in range(10)]
        with self.assertRaises(FeatureDimensionMismatchError):
            model.transform(X_bad_dim)

    # -------------------------------------------------------------------------
    # 9. Badly Scaled Features Robustness
    # -------------------------------------------------------------------------

    def test_badly_scaled_features_robustness(self) -> None:
        """Variances spanning extreme scales (10^-12 to 10^12) are handled stably."""
        X_scaled = generate_badly_scaled_dataset(n_samples=80, n_features=4, seed=777)
        model = TrainOnlyWhiteningModel(method=WhiteningMethod.CHOLESKY, eigenvalue_floor=1e-14)
        result = model.fit(X_scaled)

        self.assertTrue(math.isfinite(result.in_sample_error))
        self.assertTrue(math.isfinite(result.spd_report.raw_condition_number))
        self.assertGreater(result.spd_report.raw_condition_number, 1e8)

        # In-sample whitened features have normalized unit variance
        Z = model.transform(X_scaled)
        cov_z = compute_covariance(Z)
        for i in range(4):
            self.assertAlmostEqual(cov_z[i][i], 1.0, delta=1e-3)

    # -------------------------------------------------------------------------
    # 10. Strict Test Data Isolation (Zero Leakage)
    # -------------------------------------------------------------------------

    def test_held_out_data_isolation(self) -> None:
        """Calling transform or evaluate_out_of_sample_error does not alter fitted model state."""
        model = TrainOnlyWhiteningModel(method=WhiteningMethod.CHOLESKY)
        model.fit(self.X_train)

        mu_orig = model.mean
        W_orig = model.transform_matrix
        err_orig = model.in_sample_error

        # Run out-of-sample transformations
        _ = model.transform(self.X_test)
        _ = model.evaluate_out_of_sample_error(self.X_test)

        # Verify bit-for-bit invariance of model state
        self.assertEqual(model.mean, mu_orig)
        self.assertEqual(model.transform_matrix, W_orig)
        self.assertEqual(model.in_sample_error, err_orig)

    # -------------------------------------------------------------------------
    # 11. Leakage Regression Fixture Demonstration
    # -------------------------------------------------------------------------

    def test_leakage_regression_fixture_demonstrates_contamination(self) -> None:
        """Controlled leakage test verifies that leaking test data alters parameters."""
        # Create test set with shifted distribution
        X_test_shifted = generate_mean_shifted_test_set(self.X_train, shift_magnitude=3.0)

        leakage_res = run_leakage_regression_fixture(
            self.X_train, X_test_shifted, method=WhiteningMethod.CHOLESKY
        )

        self.assertTrue(leakage_res.leakage_detected)
        self.assertGreater(leakage_res.mean_difference_norm, 0.1)
        self.assertGreater(leakage_res.covariance_difference_norm, 0.1)
        self.assertGreater(leakage_res.transform_difference_norm, 0.05)
        self.assertGreater(leakage_res.error_discrepancy, 0.01)

    # -------------------------------------------------------------------------
    # 12. Cholesky vs Symmetric ZCA Comparison
    # -------------------------------------------------------------------------

    def test_cholesky_vs_zca_whitening_comparison(self) -> None:
        """Cholesky and Symmetric ZCA both whiten covariance but rotate coordinates differently."""
        cov_train = compute_covariance(self.X_train)
        comparison = compare_whitening_methods(cov_train)

        # 1. Both whiten in-sample covariance to identity
        self.assertLess(comparison.covariance_in_sample_chol_error, 1e-10)
        self.assertLess(comparison.covariance_in_sample_zca_error, 1e-10)

        # 2. Cholesky is lower-triangular; ZCA is symmetric
        self.assertTrue(comparison.cholesky_is_lower_triangular)
        self.assertTrue(comparison.zca_is_symmetric)

        # 3. Transformation matrices are materially different
        self.assertGreater(comparison.transform_matrix_frobenius_difference, 0.05)
        self.assertGreater(comparison.relative_transform_difference, 0.05)
        self.assertFalse(comparison.are_methods_equivalent)

        # 4. Orthogonal rotation R differs from identity
        self.assertGreater(comparison.rotation_deviation_from_identity, 0.05)

        # Verify R * R^T == I (orthogonal matrix)
        d = len(cov_train)
        R = comparison.rotation_matrix
        for i in range(d):
            for j in range(d):
                dot = sum(R[i][k] * R[j][k] for k in range(d))
                expected = 1.0 if i == j else 0.0
                self.assertAlmostEqual(dot, expected, delta=1e-12)

    # -------------------------------------------------------------------------
    # 13. SPD Repair Full Disclosure
    # -------------------------------------------------------------------------

    def test_spd_repair_full_disclosure_on_valid_and_repaired(self) -> None:
        """Verifies disclosure fields on both clean SPD and rank-deficient matrices."""
        # Clean SPD
        cov_spd = [[4.0, 1.0], [1.0, 3.0]]
        _, rep_clean = project_spd_covariance(cov_spd, eigenvalue_floor=1e-4)
        self.assertFalse(rep_clean.is_correction_material)
        self.assertEqual(rep_clean.n_floored_eigenvalues, 0)
        self.assertLess(rep_clean.correction_frobenius_norm, 1e-12)

        # Indefinite / Singular
        cov_singular = [[1.0, 2.0], [2.0, 4.0]]  # det = 0, rank 1
        _, rep_singular = project_spd_covariance(cov_singular, eigenvalue_floor=1e-3)
        self.assertTrue(rep_singular.is_correction_material)
        self.assertEqual(rep_singular.n_floored_eigenvalues, 1)
        self.assertAlmostEqual(rep_singular.repaired_min_eigenvalue, 1e-3, delta=1e-8)
        self.assertGreater(rep_singular.correction_frobenius_norm, 0.0)

    # -------------------------------------------------------------------------
    # 14. Deterministic Replay
    # -------------------------------------------------------------------------

    def test_deterministic_replay(self) -> None:
        """Identical inputs produce identical whitening models bit-for-bit."""
        model_a = TrainOnlyWhiteningModel(method=WhiteningMethod.CHOLESKY)
        res_a = model_a.fit(self.X_train)

        model_b = TrainOnlyWhiteningModel(method=WhiteningMethod.CHOLESKY)
        res_b = model_b.fit(self.X_train)

        self.assertEqual(res_a.mean, res_b.mean)
        self.assertEqual(res_a.transform_matrix, res_b.transform_matrix)
        self.assertEqual(res_a.in_sample_error, res_b.in_sample_error)

    # -------------------------------------------------------------------------
    # 15. Finite JSON Report Serialization
    # -------------------------------------------------------------------------

    def test_strict_finite_json_report(self) -> None:
        """Audit result serializes to valid, finite JSON without NaN or Inf."""
        audit_res = audit_whitening_pipeline(self.X_train, self.X_test)
        json_str = audit_res.to_json()
        parsed = json.loads(json_str)

        self.assertEqual(parsed["status"], "PASSED")
        self.assertEqual(parsed["candidate_code_present"], False)
        self.assertIn("spd_report", parsed)
        self.assertIn("method_comparison", parsed)
        self.assertNotIn("NaN", json_str)
        self.assertNotIn("Infinity", json_str)

    def test_cli_refuses_output_outside_repository(self) -> None:
        """Security boundary: CLI must not write JSON/MD outside the repo root."""
        import subprocess

        outside = Path("/tmp/whitening_audit_outside_repo.json")
        proc = subprocess.run(
            [
                sys.executable,
                str(_REPO_ROOT / "scripts" / "audit_round6_whitening.py"),
                "--json-out",
                str(outside),
            ],
            cwd=str(_REPO_ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("refusing to write outside repository root", proc.stderr + proc.stdout)
        self.assertFalse(outside.exists())


if __name__ == "__main__":
    unittest.main()
