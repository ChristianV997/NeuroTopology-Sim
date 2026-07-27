import numpy as np
import pytest
from sim.pitnn.ingest_empirical import empirical_to_macro_signal, ingest_empirical


def test_csv_ingestion_normalizes_and_extracts_phase(tmp_path):
    t = np.linspace(0, 8 * np.pi, 64)
    data = np.column_stack([np.sin(t), 2 * np.cos(t)])
    path = tmp_path / "eeg.csv"
    np.savetxt(path, data, delimiter=",")
    signal = ingest_empirical(path, sample_rate_hz=100.0)
    assert signal.data.shape == signal.phase.shape == (64, 2)
    assert np.allclose(np.mean(signal.data, axis=0), 0, atol=1e-12)
    assert np.allclose(np.std(signal.data, axis=0), 1, atol=1e-12)
    assert empirical_to_macro_signal(signal).shape == (64,)


def test_npy_ingestion_is_deterministic(tmp_path):
    values = np.column_stack([np.sin(np.linspace(0, 10, 32)), np.cos(np.linspace(0, 10, 32))])
    path = tmp_path / "signal.npy"; np.save(path, values)
    a = ingest_empirical(path, sample_rate_hz=200.0); b = ingest_empirical(path, sample_rate_hz=200.0)
    np.testing.assert_array_equal(a.phase, b.phase)
    assert a.sample_rate_hz == 200.0


def test_ingestion_rejects_constant_channels(tmp_path):
    path = tmp_path / "bad.csv"; np.savetxt(path, np.ones((16, 2)), delimiter=",")
    with pytest.raises(ValueError): ingest_empirical(path, sample_rate_hz=100.0)
