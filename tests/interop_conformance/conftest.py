"""Pytest configuration and fixture providers for cross-adapter conformance."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import pytest
import numpy as np

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES_DIR


@pytest.fixture
def fixture_numpy_path() -> Path:
    return FIXTURES_DIR / "numpy_fixture.npy"


@pytest.fixture
def fixture_csv_path() -> Path:
    return FIXTURES_DIR / "signal_fixture.csv"


@pytest.fixture
def fixture_fif_metadata_path() -> Path:
    return FIXTURES_DIR / "fif_metadata.json"


@pytest.fixture
def fixture_edf_metadata_path() -> Path:
    return FIXTURES_DIR / "edf_metadata.json"


@pytest.fixture
def fixture_brainvision_metadata_path() -> Path:
    return FIXTURES_DIR / "brainvision_metadata.json"


@pytest.fixture
def fixture_missing_montage_path() -> Path:
    return FIXTURES_DIR / "missing_montage.json"


@pytest.fixture
def fixture_inferred_montage_path() -> Path:
    return FIXTURES_DIR / "inferred_montage.json"


@pytest.fixture
def fixture_malformed_path() -> Path:
    return FIXTURES_DIR / "malformed_input.bin"


@pytest.fixture
def discovered_adapters() -> dict[str, dict]:
    """Inspects the python environment for available adapters."""
    adapters = {}
    
    # PR #214: MNE streaming adapter
    if importlib.util.find_spec("sciencer_d.btc_icft.io.eeg_mne_adapter"):
        try:
            mod = importlib.import_module("sciencer_d.btc_icft.io.eeg_mne_adapter")
            fn = getattr(mod, "iter_mne_signal_chunks", None)
            adapters["PR214_MNE"] = {
                "available": fn is not None,
                "function": fn,
                "module": mod,
                "capability_check": getattr(mod, "check_mne_available", None),
            }
        except Exception as e:
            adapters["PR214_MNE"] = {"available": False, "error": str(e)}
    else:
        adapters["PR214_MNE"] = {"available": False, "reason": "Module not present"}

    # PR #220: Native signal adapter
    if importlib.util.find_spec("sciencer_d.btc_icft.io.eeg_native_adapter"):
        try:
            mod = importlib.import_module("sciencer_d.btc_icft.io.eeg_native_adapter")
            fn = getattr(mod, "iter_native_signal_chunks", None) or getattr(mod, "iter_signal_chunks", None)
            adapters["PR220_Native"] = {
                "available": fn is not None,
                "function": fn,
                "module": mod,
                "capability_check": getattr(mod, "check_native_available", None),
            }
        except Exception as e:
            adapters["PR220_Native"] = {"available": False, "error": str(e)}
    else:
        adapters["PR220_Native"] = {"available": False, "reason": "Module not present"}

    return adapters
