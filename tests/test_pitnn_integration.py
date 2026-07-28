"""Integration tests for the PITNN pipeline (quantum Orch-OR model)."""
import json
import tempfile
from pathlib import Path

import pytest

from run_pitnn import run_pipeline


@pytest.mark.slow
def test_pitnn_synthetic_basic():
    """PITNN pipeline runs end-to-end with synthetic data (basic config)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        result = run_pipeline(
            output_dir=tmpdir,
            seed=42,
            n_samples=64,  # Small for speed
            n_spins=16,
            steps=50,
            advanced_biophysics=False,
        )

        # Verify result structure
        assert isinstance(result, dict)
        assert "run_id" in result
        assert "data_mode" in result
        assert result["data_mode"] == "synthetic_demo"
        assert "metrics" in result
        assert "verdict" in result
        assert "input" in result
        assert "artifacts" in result

        # Verify metrics structure
        metrics = result["metrics"]
        assert "inversion" in metrics
        assert "llg" in metrics
        assert "gneb" in metrics
        assert "bayesian" in metrics

        # Verify input tracking
        inputs = result["input"]
        assert inputs["seed"] == 42
        assert inputs["n_samples"] == 64
        assert inputs["n_spins"] == 16
        assert inputs["steps"] == 50

        # Verify Bayesian falsification verdict
        bayes = metrics["bayesian"]
        assert "verdict" in bayes
        assert "bayes_factor" in bayes
        assert isinstance(bayes["bayes_factor"], (int, float))

        # Verify LLG (spin dynamics) metrics exist
        llg = metrics["llg"]
        assert "final_energy" in llg or "energy" in llg or len(llg) > 0

        # Verify GNEB (energy well) metrics exist
        gneb = metrics["gneb"]
        assert isinstance(gneb, dict)

        # Verify artifacts are relative paths
        artifacts = result["artifacts"]
        assert "spinor_trajectory" in artifacts
        assert "topological_trace" in artifacts
        # All should be relative paths
        for name, path in artifacts.items():
            assert not Path(path).is_absolute()
            assert "/" in path or "\\" in path


@pytest.mark.slow
def test_pitnn_advanced_biophysics():
    """PITNN pipeline runs advanced biophysics modules (Lindblad, exceptional points)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        result = run_pipeline(
            output_dir=tmpdir,
            seed=42,
            n_samples=32,  # Very small
            n_spins=8,
            steps=20,
            advanced_biophysics=True,
            mcwf_trajectories=0,  # Skip trajectories for speed
            fast_ep=False,  # Use standard EP scan
        )

        # Verify advanced metrics are present
        metrics = result["metrics"]
        assert "advanced_biophysics" in metrics
        advanced = metrics["advanced_biophysics"]

        # Check key quantum subsystems
        assert "lindblad" in advanced or "tryptophan" in advanced or "coherence" in advanced
        assert isinstance(advanced, dict)


@pytest.mark.slow
def test_pitnn_artifacts_written():
    """PITNN artifacts are written to disk and findable."""
    with tempfile.TemporaryDirectory() as tmpdir:
        out_path = Path(tmpdir)
        result = run_pipeline(
            output_dir=out_path,
            seed=42,
            n_samples=32,
            n_spins=8,
            steps=20,
        )

        # Verify RunRecord.json exists
        run_record_path = out_path / "RunRecord.json"
        assert run_record_path.exists(), f"RunRecord.json not found at {run_record_path}"

        # Load and verify RunRecord structure
        run_record = json.loads(run_record_path.read_text())
        assert "run_id" in run_record
        assert "run_kind" in run_record or "mode" in run_record
        assert run_record["run_id"] == result["run_id"]

        # Verify result JSON written
        result_path = out_path / "pitnn_results.json"
        assert result_path.exists()
        result_loaded = json.loads(result_path.read_text())
        assert result_loaded["run_id"] == result["run_id"]

        # Verify verdict log written
        verdict_path = out_path / "verdict.log"
        assert verdict_path.exists()
        verdict_text = verdict_path.read_text()
        assert "verdict=" in verdict_text
        assert "bayes_factor=" in verdict_text


def test_pitnn_verdict_deterministic():
    """Same seed produces same verdict across runs."""
    with tempfile.TemporaryDirectory() as tmpdir1:
        result1 = run_pipeline(
            output_dir=tmpdir1,
            seed=12345,
            n_samples=32,
            n_spins=8,
            steps=20,
        )

    with tempfile.TemporaryDirectory() as tmpdir2:
        result2 = run_pipeline(
            output_dir=tmpdir2,
            seed=12345,
            n_samples=32,
            n_spins=8,
            steps=20,
        )

    # Same seed should produce same Bayes factor (deterministic)
    bf1 = result1["metrics"]["bayesian"]["bayes_factor"]
    bf2 = result2["metrics"]["bayesian"]["bayes_factor"]
    assert bf1 == bf2, f"Same seed produced different Bayes factors: {bf1} vs {bf2}"

    # Same verdict
    assert result1["verdict"] == result2["verdict"]


@pytest.mark.slow
def test_pitnn_run_id_deterministic():
    """Same inputs produce same run_id (content-addressed)."""
    with tempfile.TemporaryDirectory() as tmpdir1:
        result1 = run_pipeline(
            output_dir=tmpdir1,
            seed=42,
            n_samples=64,
            n_spins=16,
            steps=50,
        )

    with tempfile.TemporaryDirectory() as tmpdir2:
        result2 = run_pipeline(
            output_dir=tmpdir2,
            seed=42,
            n_samples=64,
            n_spins=16,
            steps=50,
        )

    # Same inputs should produce same run_id
    assert result1["run_id"] == result2["run_id"]
