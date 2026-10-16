"""Parameter forwarding and reference-policy tests against a mocked MNE API."""
from __future__ import annotations

from typing import Any, Dict, List

import pytest

from adapters.mne_csd import (
    DEFAULT_LAMBDA2,
    DEFAULT_N_LEGENDRE_TERMS,
    DEFAULT_STIFFNESS,
    InvalidChannelSelectionError,
    ReferenceMutationError,
    apply_csd,
)
from tests.adapters.mne_csd.conftest import FakeRaw, standard_locs


class RecordingCallable:
    def __init__(self):
        self.calls: List[Dict[str, Any]] = []

    def __call__(self, inst, **kwargs):
        self.calls.append({"inst": inst, **kwargs})
        # Simulate MNE assigning V/m^2 units.
        out = inst.copy() if hasattr(inst, "copy") else inst
        for ch in out.info["chs"]:
            ch["unit"] = "V/m^2"
        # Return finite synthetic data.
        out._data = [[1.0, 2.0, 3.0] for _ in out.ch_names]
        return out


def test_forwards_documented_api_kwargs(eeg_raw):
    backend = RecordingCallable()
    result = apply_csd(
        eeg_raw,
        channels=["Fz", "Cz", "Pz"],
        sphere=(0.0, 0.0, 0.04, 0.09),
        lambda2=1e-5,
        stiffness=4.0,
        n_legendre_terms=50,
        copy=True,
        csd_callable=backend,
    )
    assert len(backend.calls) == 1
    call = backend.calls[0]
    assert call["sphere"] == (0.0, 0.0, 0.04, 0.09)
    assert call["lambda2"] == DEFAULT_LAMBDA2
    assert call["stiffness"] == DEFAULT_STIFFNESS
    assert call["n_legendre_terms"] == DEFAULT_N_LEGENDRE_TERMS
    assert call["copy"] is True
    assert result.provenance.parameters["sphere"] == [0.0, 0.0, 0.04, 0.09]
    assert result.provenance.api_function.endswith("compute_current_source_density")


def test_sphere_auto_forwarded(eeg_raw):
    backend = RecordingCallable()
    result = apply_csd(
        eeg_raw, channels=["Fz", "Cz", "Pz"], sphere="auto", csd_callable=backend
    )
    assert backend.calls[0]["sphere"] == "auto"
    assert "digitization" in result.provenance.sphere_note


def test_defaults_match_mne_docs(eeg_raw):
    backend = RecordingCallable()
    apply_csd(eeg_raw, channels=["Fz", "Cz", "Pz"], csd_callable=backend)
    call = backend.calls[0]
    assert call["lambda2"] == 1e-5
    assert call["stiffness"] == 4
    assert call["n_legendre_terms"] == 50
    assert call["copy"] is True
    assert call["sphere"] == "auto"


def test_alter_reference_refused(eeg_raw):
    with pytest.raises(ReferenceMutationError):
        apply_csd(
            eeg_raw,
            channels=["Fz", "Cz", "Pz"],
            alter_reference=True,
            csd_callable=RecordingCallable(),
        )


def test_channel_order_preserved(eeg_raw):
    backend = RecordingCallable()
    result = apply_csd(
        eeg_raw,
        channels=["Pz", "Fz", "Cz"],
        csd_callable=backend,
    )
    assert result.provenance.channel_order == ["Pz", "Fz", "Cz"]
    assert result.instance.ch_names == ["Pz", "Fz", "Cz"]


def test_output_order_mismatch_fails_closed(eeg_raw):
    def bad_backend(inst, **kwargs):
        # Deliberately permute names without updating consistently — simulate silent reorder.
        out = inst.copy()
        out.ch_names = list(reversed(out.ch_names))
        return out

    with pytest.raises(InvalidChannelSelectionError, match="order/membership"):
        apply_csd(eeg_raw, channels=["Fz", "Cz", "Pz"], csd_callable=bad_backend)


def test_excluded_channels_not_hidden(eeg_raw_with_eog):
    result = apply_csd(
        eeg_raw_with_eog,
        channels=["Fz", "Cz", "Pz"],
        csd_callable=RecordingCallable(),
    )
    assert "EOG" in result.provenance.channels_excluded
    assert "EOG" in result.provenance.channels_dropped_report
    assert "EOG" not in result.provenance.channels_selected


def test_set_eeg_reference_never_called(eeg_raw):
    # If apply_csd incorrectly called set_eeg_reference, FakeRaw would raise.
    apply_csd(eeg_raw, channels=["Fz", "Cz", "Pz"], csd_callable=RecordingCallable())
    assert eeg_raw.set_eeg_reference_calls == []


def test_invalid_lambda2_rejected(eeg_raw):
    from adapters.mne_csd import CSDAdapterError

    with pytest.raises(CSDAdapterError, match="lambda2"):
        apply_csd(
            eeg_raw,
            channels=["Fz", "Cz", "Pz"],
            lambda2=1.0,
            csd_callable=RecordingCallable(),
        )


def test_missing_coords_never_reaches_backend():
    raw = FakeRaw(["Fz", "Cz"], locs=[[0.0] * 12, [0.0] * 12])
    backend = RecordingCallable()
    with pytest.raises(Exception):
        apply_csd(raw, channels=["Fz", "Cz"], csd_callable=backend)
    assert backend.calls == []
