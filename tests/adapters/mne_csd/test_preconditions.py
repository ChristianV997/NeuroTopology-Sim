"""Fail-closed precondition tests (no MNE required)."""
from __future__ import annotations

import pytest

from adapters.mne_csd import (
    InvalidChannelSelectionError,
    MissingCoordinatesError,
    ReferenceMutationError,
    extract_channel_inventory,
    inspect_preconditions,
    reject_reference_mutation,
    validate_channel_selection,
)
from adapters.mne_csd.preconditions import excluded_channels
from tests.adapters.mne_csd.conftest import FakeRaw, standard_locs


def test_explicit_channels_required(eeg_raw):
    inv = extract_channel_inventory(eeg_raw)
    with pytest.raises(InvalidChannelSelectionError, match="explicit"):
        validate_channel_selection(inv, [])


def test_missing_coordinates_fail_closed():
    raw = FakeRaw(["Fz", "Cz"], locs=[[0.0] * 12, [0.0] * 12])
    inv = extract_channel_inventory(raw)
    with pytest.raises(MissingCoordinatesError):
        validate_channel_selection(inv, ["Fz", "Cz"])


@pytest.mark.parametrize(
    "bad_loc",
    [
        [float("nan"), 0.01, 0.02] + [0.0] * 9,
        [0.01, float("inf"), 0.02] + [0.0] * 9,
        [0.01, 0.02, float("-inf")] + [0.0] * 9,
    ],
)
def test_non_finite_coordinates_fail_closed(bad_loc):
    """NaN/Inf montage coords must not be treated as usable meters."""
    good = standard_locs(1)[0]
    raw = FakeRaw(["Bad", "Good"], locs=[bad_loc, good])
    inv = extract_channel_inventory(raw)
    assert inv["Bad"]["xyz_m"] is None
    with pytest.raises(MissingCoordinatesError, match="usable 3D coordinates"):
        validate_channel_selection(inv, ["Bad", "Good"])


def test_non_eeg_channel_fail_closed(eeg_raw_with_eog):
    inv = extract_channel_inventory(eeg_raw_with_eog)
    with pytest.raises(InvalidChannelSelectionError, match="non_eeg|EOG|eog"):
        validate_channel_selection(inv, ["Fz", "EOG"])


@pytest.mark.parametrize(
    "intracranial_type",
    ["seeg", "ecog", "dbs", "ref_eeg"],
)
def test_intracranial_and_ref_eeg_not_misclassified_as_scalp_eeg(intracranial_type):
    """Substring 'eeg' must not promote seeg/ref_eeg into the scalp-EEG allowlist."""
    raw = FakeRaw(
        ["X1", "X2"],
        ch_types=[intracranial_type, intracranial_type],
        locs=standard_locs(2),
    )
    inv = extract_channel_inventory(raw)
    assert inv["X1"]["ch_type"] == intracranial_type.casefold()
    with pytest.raises(InvalidChannelSelectionError, match="non_eeg|requires eeg"):
        validate_channel_selection(inv, ["X1", "X2"])


def test_unknown_channel_fail_closed(eeg_raw):
    inv = extract_channel_inventory(eeg_raw)
    with pytest.raises(InvalidChannelSelectionError, match="not found"):
        validate_channel_selection(inv, ["Fz", "NOPE"])


def test_excluded_channels_reported(eeg_raw_with_eog):
    inv = extract_channel_inventory(eeg_raw_with_eog)
    selected, _, _ = validate_channel_selection(inv, ["Fz", "Cz", "Pz"])
    excl = excluded_channels(inv, selected)
    assert excl == ["EOG"]


def test_reject_reference_mutation():
    reject_reference_mutation(alter_reference=False)
    with pytest.raises(ReferenceMutationError):
        reject_reference_mutation(alter_reference=True)


def test_inspect_preconditions_reports_frame_and_coords(eeg_raw):
    report = inspect_preconditions(eeg_raw, ["Fz", "Cz", "Pz"])
    assert report["channels_selected"] == ["Fz", "Cz", "Pz"]
    assert report["coordinate_frame"] == "head"
    assert set(report["coordinates_m"]) == {"Fz", "Cz", "Pz"}
    for xyz in report["coordinates_m"].values():
        assert xyz is not None
        assert any(abs(v) > 0 for v in xyz)


def test_usable_coords_accepted():
    raw = FakeRaw(["A", "B"], locs=standard_locs(2))
    inv = extract_channel_inventory(raw)
    selected, reports, errors = validate_channel_selection(inv, ["A", "B"])
    assert selected == ["A", "B"]
    assert errors == []
    assert all(r.usable for r in reports)
