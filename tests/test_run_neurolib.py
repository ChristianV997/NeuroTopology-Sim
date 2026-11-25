"""Tests for neurolib neural mass model pipeline."""
from __future__ import annotations

import importlib.util
import tempfile
from pathlib import Path

import numpy as np
import pytest

# Do not call pytest.importorskip at module/decorator import time: that skips
# the entire module when neurolib is absent and blocks pure unit tests of the
# seconds→ms contract helper.
_HAS_NEUROLIB = importlib.util.find_spec("neurolib") is not None


def test_run_neurolib_imports():
    """Test that neurolib pipeline can be imported."""
    pytest.importorskip("neurolib")
    from pipelines.run_neurolib import run as run_neurolib
    assert callable(run_neurolib)


@pytest.mark.skipif(not _HAS_NEUROLIB, reason="neurolib required")
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


@pytest.mark.skipif(not _HAS_NEUROLIB, reason="neurolib required")
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
        # RunRecordV1 has no `sim_params` field; sim input params live on
        # the canonical `input` field (see runs/run_record.py).
        assert record.input["model_type"] == "hopf"
        # Seconds API must land in neurolib as milliseconds on the live model path.
        assert record.input["neurolib_time"]["dt_ms"] == pytest.approx(
            record.input["dt"] * 1000.0
        )
        assert record.input["neurolib_time"]["duration_ms"] == pytest.approx(
            record.input["t_max"] * 1000.0
        )


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


def test_neurolib_runtime_time_params_convert_seconds_to_ms():
    """Public dt/t_max are seconds; neurolib params.dt/duration are milliseconds.

    Regression: converting only duration left params['dt'] in seconds while
    neurolib interprets dt as ms (1000× too small vs the documented API).
    Does not require neurolib to be installed.
    """
    from pipelines.run_neurolib import neurolib_runtime_time_params

    params = neurolib_runtime_time_params(dt_s=0.01, t_max_s=2.0)
    assert params["dt_s"] == pytest.approx(0.01)
    assert params["t_max_s"] == pytest.approx(2.0)
    # 0.01 s = 10 ms; 2.0 s = 2000 ms
    assert params["dt_ms"] == pytest.approx(10.0)
    assert params["duration_ms"] == pytest.approx(2000.0)
    # Both must share the same unit system (ms): duration/dt = number of steps
    assert params["duration_ms"] / params["dt_ms"] == pytest.approx(200.0)


def test_neurolib_runtime_time_params_reject_nonpositive():
    from pipelines.run_neurolib import neurolib_runtime_time_params

    with pytest.raises(ValueError, match="dt must be positive"):
        neurolib_runtime_time_params(dt_s=0.0, t_max_s=1.0)
    with pytest.raises(ValueError, match="t_max must be positive"):
        neurolib_runtime_time_params(dt_s=0.01, t_max_s=-1.0)


def test_kuramoto_integration_keeps_seconds_dt():
    """Neighboring interface: native Kuramoto path must stay in seconds.

    It does not go through neurolib's millisecond runtime params.
    """
    from pipelines.run_neurolib import _integrate_kuramoto, _generate_random_connectivity

    Cmat = _generate_random_connectivity(4, seed=0)
    # dt=0.05 s, t_max=0.2 s → 4 steps (max with >=3 floor)
    out = _integrate_kuramoto(4, coupling=0.1, dt=0.05, t_max=0.2, seed=0, Cmat=Cmat)
    assert out.shape == (4, 4)
