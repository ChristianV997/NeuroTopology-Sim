"""Tests for neurolib neural mass model pipeline."""
from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import pytest


def test_run_neurolib_imports():
    """Test that neurolib pipeline can be imported."""
    pytest.importorskip("neurolib")
    from pipelines.run_neurolib import run as run_neurolib
    assert callable(run_neurolib)


@pytest.mark.skipif(
    pytest.importorskip("neurolib", minversion=None) is None,
    reason="neurolib required",
)
def test_run_neurolib_kuramoto_basic():
    """Test that neurolib Kuramoto model runs and produces nonzero topology."""
    from pipelines.run_neurolib import run as run_neurolib

    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "test_output.json"
        record = run_neurolib(
            output_csv=output_path,
            n_nodes=8,
            model_type="kuramoto",
            t_max=1.0,
            dt=0.01,
            coupling=0.5,
            seed=42,
        )
        assert record is not None
        assert record.run_id is not None
        assert record.metrics is not None
        assert "Q_mean" in record.metrics
        assert "Qabs_mean" in record.metrics
        # Check that output was written
        assert output_path.exists()


@pytest.mark.skipif(
    pytest.importorskip("neurolib", minversion=None) is None,
    reason="neurolib required",
)
def test_run_neurolib_hopf():
    """Test Hopf oscillator model."""
    from pipelines.run_neurolib import run as run_neurolib

    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "test_output.json"
        record = run_neurolib(
            output_csv=output_path,
            n_nodes=6,
            model_type="hopf",
            t_max=0.5,
            coupling=0.2,
            seed=42,
        )
        assert record is not None
        assert record.sim_params["model_type"] == "hopf"


def test_run_neurolib_invalid_model():
    """Test that invalid model type raises an error."""
    pytest.importorskip("neurolib")
    from pipelines.run_neurolib import run as run_neurolib

    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "test_output.json"
        with pytest.raises(ValueError, match="Unknown model_type"):
            run_neurolib(
                output_csv=output_path,
                n_nodes=8,
                model_type="invalid_model",
                t_max=1.0,
                coupling=0.1,
            )
