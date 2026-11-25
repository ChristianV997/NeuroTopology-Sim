"""OPTIONAL live-MNE parity against an installed MNE 1.13.2.

This directory is outside the Round 6 gate. The gate does not run it, so a skip here does not fail the gate, and a
skip here is NOT evidence. The result is recorded only when this file runs with MNE 1.13.2 installed, in an
environment the audit owner controls. MNE is never installed by the audit.
"""
from __future__ import annotations

import pytest

from tools.mne_csd_reference_audit import pin
from tools.mne_csd_reference_audit.kkt import apply_csd, csd_operator
from tools.mne_csd_reference_audit.montages import MONTAGES

RADIUS = 0.095


@pytest.mark.parametrize("name", ["tetrahedron_4", "seeded_cap_7", "seeded_cap_12"])
def test_matches_pinned_mne_compute_current_source_density(name):
    mne = pytest.importorskip("mne")
    if mne.__version__ != pin.MNE_VERSION:
        pytest.skip(f"installed MNE {mne.__version__} differs from pinned {pin.MNE_VERSION}")
    import numpy as np

    unit = MONTAGES[name]()
    positions = RADIUS * unit
    n = unit.shape[0]
    info = mne.create_info([f"E{i}" for i in range(n)], sfreq=100.0, ch_types="eeg")
    data = np.random.default_rng(0).standard_normal((n, 200)) * 1e-6
    raw = mne.io.RawArray(data, info, verbose=False)
    for channel, position in zip(raw.info["chs"], positions):
        channel["loc"][:3] = position
    csd = mne.preprocessing.compute_current_source_density(
        raw,
        sphere=(0.0, 0.0, 0.0, RADIUS),
        lambda2=1e-5,
        stiffness=4,
        n_legendre_terms=50,
        copy=True,
        verbose=False,
    )
    expected = apply_csd(csd_operator(positions, radius=RADIUS, lambda2=1e-5, method="kkt"), data)
    np.testing.assert_allclose(csd.get_data(), expected, rtol=1e-8, atol=1e-12)
