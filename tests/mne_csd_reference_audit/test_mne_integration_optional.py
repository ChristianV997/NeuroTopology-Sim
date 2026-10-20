"""Deterministic, fixture-based checks of the pinned MNE 1.13.2 code path. No MNE is imported and nothing skips.

The file name is fixed by the Round 6 gate mapping (docs/mne_csd_reference_audit.md, "Hosted CI status"). The
live-MNE comparison is not in this file. It lives in tests/optional_live_mne/, outside the gate, because any skip
in this file fails the gate.

What the fixture is: a frozen copy of the transcription in conftest.py. Its producer and provenance are recorded in
the JSON. It is not executed MNE output. The package's own agreement with the transcription is tested in
test_kkt_operator.py, so these tests guard against drift of the transcription itself. A shared misreading of the
pinned source would pass here; the independent check is the live comparison outside the gate.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from tools.mne_csd_reference_audit import pin
from tools.mne_csd_reference_audit.montages import MONTAGES

RADIUS = 0.095
LAMBDA2 = 1e-5
EPS = np.finfo(float).eps
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "mne_code_path_transcription.json"
FIXTURE_DATA = json.loads(FIXTURE.read_text(encoding="utf-8"))
NAMES = sorted(FIXTURE_DATA["montages"])


def _bound(entry: dict) -> float:
    # Same justification as the operator tests: 10 * cond(G + lambda2 I) * eps.
    return 10 * entry["cond_G_reg"] * EPS


def test_fixture_covers_every_montage():
    # Regression (2026-10-20, code review): a montage added to MONTAGES without a frozen matrix was reported by no test.
    assert set(NAMES) == set(MONTAGES), sorted(set(MONTAGES) ^ set(NAMES))


def test_fixture_provenance_matches_the_pin():
    assert FIXTURE_DATA["mne_version"] == pin.MNE_VERSION
    assert FIXTURE_DATA["mne_tag_commit"] == pin.MNE_TAG_COMMIT
    assert FIXTURE_DATA["sdist_sha256"] == pin.MNE_SDIST_SHA256
    assert FIXTURE_DATA["source_sha256"] == pin.MNE_SOURCE_FILES
    assert FIXTURE_DATA["radius_m"] == RADIUS
    assert FIXTURE_DATA["lambda2"] == LAMBDA2
    assert FIXTURE_DATA["stiffness"] == 4
    assert FIXTURE_DATA["n_legendre_terms"] == 50
    assert FIXTURE_DATA["evidence_class"] == "SYNTHETIC_ONLY"
    # Regression (2026-10-20): _calc_h is at lines 20-37 of interpolation.py and _calc_g at 40-62. The earlier
    # citation gave 40-62 for both, so an auditor following it read the wrong exponent.
    assert "20-37 (_calc_h)" in FIXTURE_DATA["source_lines"]["mne/channels/interpolation.py"]
    assert "40-62 (_calc_g)" in FIXTURE_DATA["source_lines"]["mne/channels/interpolation.py"]


@pytest.mark.parametrize("name", NAMES)
def test_transcription_reproduces_the_frozen_matrix(name, mne_code_path_oracle):
    entry = FIXTURE_DATA["montages"][name]
    pos = RADIUS * MONTAGES[name]()
    np.testing.assert_allclose(pos, np.array(entry["positions_m"]), rtol=1e-15, atol=0)
    M, _ = mne_code_path_oracle(pos, RADIUS, LAMBDA2)
    stored = np.array(entry["matrix"])
    assert np.linalg.norm(M - stored) / np.linalg.norm(stored) <= _bound(entry)
