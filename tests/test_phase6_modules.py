"""Tests for Phase 6 modules: S3 fetchers and fast-TR validation pipeline."""
from __future__ import annotations

import pytest
import tempfile
from pathlib import Path


def test_s3_fetchers_import():
    """Test that s3_fetchers module can be imported."""
    from validation.s3_fetchers import NKIRSFetcher, HCPYAFetcher
    assert callable(NKIRSFetcher)
    assert callable(HCPYAFetcher)


@pytest.mark.skipif(
    pytest.importorskip("boto3", minversion=None) is None,
    reason="boto3 not installed",
)
def test_nki_rs_fetcher_init():
    """Test NKI-RS fetcher initialization."""
    from validation.s3_fetchers import NKIRSFetcher

    with tempfile.TemporaryDirectory() as tmpdir:
        # Should initialize without credentials (public bucket)
        fetcher = NKIRSFetcher(cache_dir=tmpdir)
        assert fetcher.bucket == "nki-openaccess"
        assert fetcher.region == "us-east-1"


@pytest.mark.skipif(
    pytest.importorskip("boto3", minversion=None) is None,
    reason="boto3 not installed",
)
def test_hcp_ya_fetcher_init_requires_profile():
    """Test HCP-YA fetcher requires credentials."""
    from validation.s3_fetchers import HCPYAFetcher

    with tempfile.TemporaryDirectory() as tmpdir:
        # Should fail without valid AWS credentials (no DUA setup in test env)
        with pytest.raises(RuntimeError):
            HCPYAFetcher(cache_dir=tmpdir, profile="nonexistent")


def test_nki_rs_s3_path_building():
    """Test S3 path construction for NKI-RS."""
    pytest.importorskip("boto3")
    from validation.s3_fetchers import NKIRSFetcher

    with tempfile.TemporaryDirectory() as tmpdir:
        fetcher = NKIRSFetcher(cache_dir=tmpdir)

        # Test BOLD path
        bold_path = fetcher._s3_path("A00008326", 1, "bold")
        assert "sub-A00008326" in bold_path
        assert "ses-01" in bold_path
        assert "bold.nii.gz" in bold_path

        # Test confounds path
        confounds_path = fetcher._s3_path("A00008326", 1, "confounds")
        assert "sub-A00008326" in confounds_path
        assert "ses-01" in confounds_path
        assert "physio.tsv" in confounds_path


def test_hcp_ya_s3_path_building():
    """Test S3 path construction for HCP-YA."""
    pytest.importorskip("boto3")
    from validation.s3_fetchers import HCPYAFetcher

    # Create a mock fetcher (without real credentials)
    class MockHCPYA(HCPYAFetcher):
        def __init__(self, cache_dir):
            self.cache_dir = Path(cache_dir)
            self.bucket = "hcp-openaccess"
            self.region = "us-east-1"
            self.s3_client = None

    with tempfile.TemporaryDirectory() as tmpdir:
        fetcher = MockHCPYA(tmpdir)

        # Test BOLD path
        bold_path = fetcher._s3_path("100206", 1, "bold")
        assert "HCP_1200/100206" in bold_path
        assert "rfMRI_REST1_LR" in bold_path
        assert "nii.gz" in bold_path

        # Test confounds path
        confounds_path = fetcher._s3_path("100206", 1, "confounds")
        assert "HCP_1200/100206" in confounds_path
        assert "Physio_log" in confounds_path


def test_hcp_ya_invalid_run():
    """Test that invalid HCP run numbers raise error."""
    pytest.importorskip("boto3")
    from validation.s3_fetchers import HCPYAFetcher

    class MockHCPYA(HCPYAFetcher):
        def __init__(self, cache_dir):
            self.cache_dir = Path(cache_dir)
            self.s3_client = None

    with tempfile.TemporaryDirectory() as tmpdir:
        fetcher = MockHCPYA(tmpdir)
        with pytest.raises(ValueError, match="run"):
            fetcher._s3_path("100206", 5, "bold")


def test_fast_tr_validation_import():
    """Test that fast_tr_validation pipeline can be imported."""
    from pipelines.run_fast_tr_validation import run as run_fast_tr_validation
    assert callable(run_fast_tr_validation)


def test_fast_tr_validation_synthetic_run():
    """Test fast-TR validation pipeline on synthetic data."""
    from pipelines.run_fast_tr_validation import run as run_fast_tr_validation

    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "fast_tr_validation.json"
        record = run_fast_tr_validation(
            output_csv=output_path,
            n_voxels=16,
            n_timepoints=100,
            tr=0.645,
            seed=42,
        )

        assert record is not None
        assert record.run_id is not None
        assert record.metrics is not None
        assert "q_mean" in record.metrics
        assert "qabs_mean" in record.metrics
        assert "f_dress_mean" in record.metrics
        assert record.metrics["tr"] == 0.645
        assert output_path.exists()


def test_fast_tr_validation_nyquist_frequency():
    """Test that Nyquist frequency is computed correctly."""
    from pipelines.run_fast_tr_validation import run as run_fast_tr_validation

    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "nyquist_test.json"
        tr = 0.645
        record = run_fast_tr_validation(
            output_csv=output_path,
            n_voxels=8,
            n_timepoints=50,
            tr=tr,
        )

        # Nyquist = 1 / (2 * TR)
        expected_nyquist = 1.0 / (2.0 * tr)
        assert record.metrics["nyquist_freq_hz"] == pytest.approx(expected_nyquist)


def test_fast_tr_validation_metrics_exist():
    """Test that all expected metrics are present."""
    from pipelines.run_fast_tr_validation import run as run_fast_tr_validation

    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "metrics_test.json"
        record = run_fast_tr_validation(output_csv=output_path)

        required_metrics = [
            "n_voxels",
            "n_timepoints",
            "tr",
            "nyquist_freq_hz",
            "q_mean",
            "q_std",
            "qabs_mean",
            "qabs_std",
            "f_dress_mean",
            "f_dress_std",
            "vortex_count_mean",
        ]
        for metric in required_metrics:
            assert metric in record.metrics, f"Missing metric: {metric}"


def test_fast_tr_validation_artifacts():
    """Test that artifacts are properly saved."""
    from pipelines.run_fast_tr_validation import run as run_fast_tr_validation

    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "artifacts_test.json"
        record = run_fast_tr_validation(output_csv=output_path)

        assert "phase_shape" in record.artifacts
        assert "phase_summary" in record.artifacts
        assert "phase_topology_note" in record.artifacts
        assert "next_steps" in record.artifacts


def test_fast_tr_validation_spec_id():
    """Test that spec_id indicates synthetic/fast-TR nature."""
    from pipelines.run_fast_tr_validation import run as run_fast_tr_validation

    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "spec_test.json"
        record = run_fast_tr_validation(output_csv=output_path)

        assert "fast_tr" in record.spec_id or "validation" in record.spec_id


def test_fast_tr_synthetic_data_generation():
    """Test synthetic fast-TR BOLD data generation."""
    from pipelines.run_fast_tr_validation import _generate_synthetic_fast_tr_bold

    psi = _generate_synthetic_fast_tr_bold(n_voxels=8, n_timepoints=50, tr=0.645, seed=42)

    assert psi.shape == (8, 8, 50)
    assert psi.dtype == np.complex128
    assert np.all(np.isfinite(psi))


@pytest.mark.skipif(
    pytest.importorskip("numpy", minversion=None) is None,
    reason="numpy not installed",
)
def test_fast_tr_synthetic_has_structure():
    """Test that synthetic data has expected structure (not just noise)."""
    import numpy as np
    from pipelines.run_fast_tr_validation import _generate_synthetic_fast_tr_bold

    psi = _generate_synthetic_fast_tr_bold(n_voxels=16, n_timepoints=200, tr=0.645, seed=42)

    # Compute phase
    phase = np.angle(psi)

    # Phase should vary spatially (not constant everywhere)
    spatial_var = np.var(phase[:, :, 0])
    assert spatial_var > 0.1, "Spatial phase structure too weak"

    # Phase should vary temporally (not constant over time)
    temporal_var = np.var(phase[8, 8, :])
    assert temporal_var > 0.1, "Temporal phase structure too weak"


def test_phase6_modules_in_main():
    """Test that phase 6 modules are wired into main.py."""
    import main

    # Check that fast_tr_validation is in the mode choices
    # (This is a basic check that the mode was registered)
    assert hasattr(main, "run_fast_tr_validation")


# Import numpy for test fixtures
import numpy as np
