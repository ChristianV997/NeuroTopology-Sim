"""Focused tests for the in-memory MNE signal-block contract.

Runs without MNE. Optional MNE bridge tests skip when MNE is unavailable.
"""

from __future__ import annotations

import pytest

from adapters.mne_signal_blocks import (
    SCHEMA_VERSION,
    BlockStatus,
    convert_from_mne_object,
    convert_in_memory_block,
    validate_block,
)
from adapters.mne_signal_blocks.fixtures import (
    clone_payload,
    make_channel_order_payload,
    make_empty_block_payload,
    make_event_misaligned_payload,
    make_missing_montage_payload,
    make_missing_reference_payload,
    make_missing_units_payload,
    make_non_finite_payload,
    make_shape_mismatch_payload,
    make_unsupported_channel_type_payload,
    make_valid_block_payload,
)
from adapters.mne_signal_blocks.schema import ReasonCode

try:
    import mne as _mne  # noqa: F401

    _HAS_MNE = True
except ImportError:
    _HAS_MNE = False


def test_valid_in_memory_conversion():
    payload = make_valid_block_payload()
    result = convert_in_memory_block(payload)
    assert result.block.schema_version == SCHEMA_VERSION
    assert result.block.status == BlockStatus.CONVERTED
    assert result.block.reason_codes == (ReasonCode.OK.value,)
    assert result.block.n_channels == 2
    assert result.block.n_samples == 8
    assert result.block.data_shape == (2, 8)
    assert result.block.scientific_pass is False
    assert result.mutated_input is False
    assert result.input_fingerprint


def test_preserves_channel_ordering_and_units():
    payload = make_channel_order_payload()
    original_names = list(payload["channel_names"])
    original_units = list(payload["units"])
    original_row0 = list(payload["data"][0])
    result = convert_in_memory_block(payload)
    assert list(result.block.channel_names) == original_names
    assert list(result.block.units) == original_units
    assert list(result.block.data[0]) == original_row0
    assert result.block.channel_names == ("Fz", "Cz", "Pz")


def test_event_sample_alignment_ok():
    payload = make_valid_block_payload(n_channels=1, n_samples=10)
    payload["events"] = [{"sample": 0, "id": 1}, {"sample": 9, "id": 2}]
    result = convert_in_memory_block(payload)
    assert result.block.status == BlockStatus.CONVERTED
    assert result.block.events[1]["sample"] == 9


def test_event_sample_alignment_mismatch():
    result = convert_in_memory_block(make_event_misaligned_payload())
    assert result.block.status == BlockStatus.REJECTED
    assert ReasonCode.EVENT_ALIGNMENT_MISMATCH.value in result.block.reason_codes


def test_shape_mismatch_rejected():
    result = convert_in_memory_block(make_shape_mismatch_payload())
    assert result.block.status == BlockStatus.REJECTED
    assert ReasonCode.CHANNEL_ORDER_MISMATCH.value in result.block.reason_codes or (
        ReasonCode.SHAPE_MISMATCH.value in result.block.reason_codes
    )


def test_non_finite_values_rejected():
    result = convert_in_memory_block(make_non_finite_payload())
    assert result.block.status == BlockStatus.REJECTED
    assert ReasonCode.NON_FINITE_VALUES.value in result.block.reason_codes


def test_absent_units_inconclusive():
    result = convert_in_memory_block(make_missing_units_payload())
    assert result.block.status == BlockStatus.INCONCLUSIVE
    assert ReasonCode.MISSING_UNITS.value in result.block.reason_codes
    assert all(u is None for u in result.block.units)


def test_absent_reference_inconclusive():
    result = convert_in_memory_block(make_missing_reference_payload())
    assert result.block.status == BlockStatus.INCONCLUSIVE
    assert ReasonCode.MISSING_REFERENCE.value in result.block.reason_codes
    assert result.block.reference is None


def test_absent_montage_inconclusive():
    result = convert_in_memory_block(make_missing_montage_payload())
    assert result.block.status == BlockStatus.INCONCLUSIVE
    assert ReasonCode.MISSING_MONTAGE.value in result.block.reason_codes
    assert result.block.montage_name is None
    assert result.block.montage_coordinates is None


def test_null_coordinates_without_montage_name_remain_inconclusive():
    payload = make_valid_block_payload(n_channels=1, n_samples=4)
    payload["montage_name"] = None
    payload["montage_coordinates"] = [None]
    result = convert_in_memory_block(payload)
    assert result.block.status == BlockStatus.INCONCLUSIVE
    assert ReasonCode.MISSING_MONTAGE.value in result.block.reason_codes


def test_empty_block_rejected():
    result = convert_in_memory_block(make_empty_block_payload())
    assert result.block.status == BlockStatus.REJECTED
    assert ReasonCode.EMPTY_BLOCK.value in result.block.reason_codes


def test_unsupported_channel_type_rejected():
    result = convert_in_memory_block(make_unsupported_channel_type_payload())
    assert result.block.status == BlockStatus.REJECTED
    assert ReasonCode.UNSUPPORTED_CHANNEL_TYPE.value in result.block.reason_codes


def test_does_not_mutate_input_arrays_or_metadata():
    payload = make_valid_block_payload()
    snapshot = clone_payload(payload)
    result = convert_in_memory_block(payload)
    assert payload == snapshot
    if result.block.data is not None:
        result.block.data[0][0] = 9999.0
    assert payload["data"][0][0] == snapshot["data"][0][0]


def test_malformed_non_mapping_errors():
    result = convert_in_memory_block("not-a-mapping")  # type: ignore[arg-type]
    assert result.block.status == BlockStatus.ERROR
    assert ReasonCode.MALFORMED_INPUT.value in result.block.reason_codes


def test_validate_block_roundtrip_metadata():
    result = convert_in_memory_block(make_valid_block_payload())
    meta = result.block.metadata_dict(include_data=True)
    report = validate_block(meta)
    assert report["status"] == BlockStatus.CONVERTED.value
    assert report["scientific_pass"] is False


def test_serialized_validation_requires_shape_when_signal_is_omitted():
    metadata = convert_in_memory_block(make_valid_block_payload()).block.metadata_dict()
    metadata.pop("data_shape")
    report = validate_block(metadata)
    assert report["status"] == BlockStatus.REJECTED.value
    assert ReasonCode.SHAPE_MISMATCH.value in report["reason_codes"]


def test_validate_block_does_not_upgrade_missing_reference_or_montage():
    payload = make_valid_block_payload()
    payload["reference"] = None
    payload["montage_name"] = None
    payload["montage_coordinates"] = None
    result = convert_in_memory_block(payload)
    report = validate_block(result.block.metadata_dict(include_data=True))
    assert result.block.status == BlockStatus.INCONCLUSIVE
    assert report["status"] == BlockStatus.INCONCLUSIVE.value
    assert ReasonCode.MISSING_REFERENCE.value in report["reason_codes"]
    assert ReasonCode.MISSING_MONTAGE.value in report["reason_codes"]


def test_validate_block_does_not_upgrade_declared_state_or_scientific_claim():
    result = convert_in_memory_block(make_valid_block_payload())
    metadata = result.block.metadata_dict(include_data=True)
    metadata["status"] = BlockStatus.REJECTED.value
    report = validate_block(metadata)
    assert report["status"] == BlockStatus.REJECTED.value
    metadata["scientific_pass"] = True
    report = validate_block(metadata)
    assert report["status"] == BlockStatus.ERROR.value
    assert report["scientific_pass"] is False


def test_malformed_declared_status_fails_closed_without_throwing():
    metadata = convert_in_memory_block(make_valid_block_payload()).block.metadata_dict()
    metadata["status"] = [BlockStatus.REJECTED.value]
    report = validate_block(metadata)
    assert report["status"] == BlockStatus.ERROR.value
    assert ReasonCode.MALFORMED_INPUT.value in report["reason_codes"]
    assert report["scientific_pass"] is False


def test_malformed_event_record_fails_closed_without_throwing():
    metadata = convert_in_memory_block(make_valid_block_payload()).block.metadata_dict(include_data=True)
    metadata["events"] = ["not-an-event-record"]
    report = validate_block(metadata)
    assert report["status"] == BlockStatus.REJECTED.value
    assert ReasonCode.MALFORMED_INPUT.value in report["reason_codes"]


def test_inconsistent_sample_bounds_are_rejected():
    payload = make_valid_block_payload(n_channels=1, n_samples=8)
    payload["block_start_sample"] = 5
    payload["block_end_sample"] = 14  # declared span is 9 samples, data contains 8
    result = convert_in_memory_block(payload)
    assert result.block.status == BlockStatus.REJECTED
    assert ReasonCode.INVALID_SAMPLE_BOUNDS.value in result.block.reason_codes


def test_invalid_montage_coordinates_fail_closed_without_throwing():
    payload = make_valid_block_payload(n_channels=1, n_samples=4)
    payload["montage_coordinates"] = [(0.0, float("inf"), 1.0)]
    result = convert_in_memory_block(payload)
    assert result.block.status == BlockStatus.REJECTED
    assert ReasonCode.NON_FINITE_VALUES.value in result.block.reason_codes
    assert result.block.montage_coordinates == (None,)


def test_unknown_units_reference_montage_and_channel_types_are_inconclusive():
    payload = make_valid_block_payload(n_channels=1, n_samples=4)
    payload["units"] = ["unknown"]
    payload["reference"] = "unspecified"
    payload["montage_name"] = "unknown"
    payload["montage_coordinates"] = None
    payload["channel_types"] = ["unknown"]
    result = convert_in_memory_block(payload)
    assert result.block.status == BlockStatus.INCONCLUSIVE
    assert ReasonCode.MISSING_UNITS.value in result.block.reason_codes
    assert ReasonCode.MISSING_REFERENCE.value in result.block.reason_codes
    assert ReasonCode.MISSING_MONTAGE.value in result.block.reason_codes
    assert ReasonCode.AMBIGUOUS_METADATA.value in result.block.reason_codes


def test_boolean_sample_rate_is_not_coerced_to_one_hertz():
    payload = make_valid_block_payload(n_channels=1, n_samples=4)
    payload["sample_rate_hz"] = True
    result = convert_in_memory_block(payload)
    assert result.block.status == BlockStatus.INCONCLUSIVE
    assert result.block.sample_rate_hz is None
    assert ReasonCode.AMBIGUOUS_METADATA.value in result.block.reason_codes


def test_numeric_text_sample_rate_is_not_coerced():
    payload = make_valid_block_payload(n_channels=1, n_samples=4)
    payload["sample_rate_hz"] = "100"
    result = convert_in_memory_block(payload)
    assert result.block.status == BlockStatus.INCONCLUSIVE
    assert result.block.sample_rate_hz is None
    assert ReasonCode.AMBIGUOUS_METADATA.value in result.block.reason_codes


def test_non_finite_sample_rate_is_not_emitted_in_json():
    from adapters.mne_signal_blocks.reporting import serialize_json

    payload = make_valid_block_payload(n_channels=1, n_samples=4)
    payload["sample_rate_hz"] = float("inf")
    result = convert_in_memory_block(payload)
    assert result.block.status == BlockStatus.INCONCLUSIVE
    assert result.block.sample_rate_hz is None
    assert "infinity" not in serialize_json(result.to_dict()).lower()


def test_non_string_unit_is_not_coerced_into_a_unit_label():
    payload = make_valid_block_payload(n_channels=1, n_samples=4)
    payload["units"] = [1]
    result = convert_in_memory_block(payload)
    assert result.block.status == BlockStatus.INCONCLUSIVE
    assert result.block.units == (None,)
    assert ReasonCode.MISSING_UNITS.value in result.block.reason_codes


def test_non_string_channel_name_is_not_coerced_into_a_name():
    payload = make_valid_block_payload(n_channels=1, n_samples=4)
    payload["channel_names"] = [None]
    result = convert_in_memory_block(payload)
    assert result.block.status == BlockStatus.INCONCLUSIVE
    assert result.block.channel_names == ("",)
    assert ReasonCode.AMBIGUOUS_METADATA.value in result.block.reason_codes


def test_never_infers_units_as_volts():
    """Anti-pattern check vs shared MneFifAdapter which hardcodes units='V'."""
    payload = make_missing_units_payload()
    result = convert_in_memory_block(payload)
    assert all(u is None for u in result.block.units)


def test_conversion_result_to_dict_is_json_safe():
    from adapters.mne_signal_blocks.reporting import serialize_json

    result = convert_in_memory_block(make_valid_block_payload())
    text = serialize_json(result.to_dict())
    assert SCHEMA_VERSION in text
    assert '"scientific_pass": false' in text


def test_mne_unavailable_path_without_import(monkeypatch):
    import builtins

    original_import = builtins.__import__

    def import_without_mne(name, *args, **kwargs):
        if name == "mne" or name.startswith("mne."):
            raise ImportError("MNE intentionally unavailable in this test")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", import_without_mne)
    result = convert_from_mne_object(object())
    assert result.block.status == BlockStatus.ERROR
    assert ReasonCode.MNE_UNAVAILABLE.value in result.block.reason_codes


@pytest.mark.requires_mne
def test_optional_mne_raw_bridge_preserves_channel_order():
    if not _HAS_MNE:
        pytest.skip("mne not installed")
    import mne
    import numpy as np

    sfreq = 100.0
    data = np.array([[1.0, 2.0, 3.0, 4.0], [10.0, 20.0, 30.0, 40.0]], dtype=float)
    info = mne.create_info(ch_names=["Fz", "Cz"], sfreq=sfreq, ch_types="eeg")
    raw = mne.io.RawArray(data.copy(), info)
    before = data.copy()
    result = convert_from_mne_object(raw, source_id="fixture-raw")
    assert np.array_equal(data, before)
    assert list(result.block.channel_names) == ["Fz", "Cz"]
    assert result.block.scientific_pass is False
    assert result.block.reference is None


@pytest.mark.requires_mne
def test_optional_mne_unavailable_reason_not_raised_when_present():
    if not _HAS_MNE:
        pytest.skip("mne not installed")
    import mne
    import numpy as np

    info = mne.create_info(ch_names=["Cz"], sfreq=50.0, ch_types="eeg")
    raw = mne.io.RawArray(np.zeros((1, 5)), info)
    result = convert_from_mne_object(raw)
    assert ReasonCode.MNE_UNAVAILABLE.value not in result.block.reason_codes
