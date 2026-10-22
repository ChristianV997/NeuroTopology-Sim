"""Optional live-MNE wiring tests. Skip cleanly when MNE is absent."""
from __future__ import annotations

import math

import pytest

mne = pytest.importorskip("mne")

from adapters.mne_csd import apply_csd  # noqa: E402


def _synthetic_raw(n_channels: int = 8, n_times: int = 200):
    import numpy as np

    # Use standard montage names so MNE can attach real coordinates if needed,
    # but we set coords explicitly via a standard montage — this is an optional
    # integration path; base tests never require it.
    ch_names = ["Fp1", "Fp2", "F3", "F4", "C3", "C4", "P3", "P4"][:n_channels]
    info = mne.create_info(ch_names=ch_names, sfreq=100.0, ch_types="eeg")
    data = np.zeros((n_channels, n_times), dtype=float)
    # Spatially varying signal + common offset.
    for i in range(n_channels):
        data[i] = 0.1 * i + 0.01 * np.sin(np.linspace(0, 4 * math.pi, n_times))
    data += 2.5  # constant common reference offset
    raw = mne.io.RawArray(data, info, verbose="ERROR")
    montage = mne.channels.make_standard_montage("standard_1020")
    raw.set_montage(montage, on_missing="raise", verbose="ERROR")
    return raw, ch_names


def test_mne_backend_produces_finite_csd():
    raw, ch_names = _synthetic_raw()
    result = apply_csd(raw, channels=ch_names, sphere="auto", copy=True, verbose="ERROR")
    assert result.provenance.mne_available is True
    assert result.provenance.mne_version is not None
    data = result.instance.get_data()
    assert data.shape[0] == len(ch_names)
    assert data.shape[1] == raw.n_times
    assert np_all_finite(data)
    assert result.provenance.channel_order == ch_names


def test_mne_common_offset_remains_finite():
    raw, ch_names = _synthetic_raw()
    result = apply_csd(raw, channels=ch_names, verbose="ERROR")
    data = result.instance.get_data()
    assert np_all_finite(data)
    # Engineering note only: do not claim scientific validity of CSD theory.
    assert "reference-free" in result.provenance.reference_policy


def test_mne_missing_coords_fail_closed():
    import numpy as np

    ch_names = ["X1", "X2", "X3"]
    info = mne.create_info(ch_names=ch_names, sfreq=50.0, ch_types="eeg")
    raw = mne.io.RawArray(np.ones((3, 50)), info, verbose="ERROR")
    # No montage set -> zero locs -> fail closed before/at validation.
    from adapters.mne_csd import MissingCoordinatesError

    with pytest.raises(MissingCoordinatesError):
        apply_csd(raw, channels=ch_names, verbose="ERROR")


def np_all_finite(arr) -> bool:
    import numpy as np

    return bool(np.isfinite(arr).all())
