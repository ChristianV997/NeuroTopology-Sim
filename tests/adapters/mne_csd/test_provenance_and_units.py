"""Provenance, units, dimensions, and finiteness (mocked backend)."""
from __future__ import annotations

import json
import math

from adapters.mne_csd import TRANSFORM_KIND, apply_csd
from adapters.mne_csd.constants import DOCUMENTED_OUTPUT_UNIT, MNE_LICENSE, NOT_SOURCE_LOCALIZATION
from tests.adapters.mne_csd.conftest import FakeRaw, standard_locs
from tests.adapters.mne_csd.test_parameter_forwarding import RecordingCallable


def test_provenance_distinguishes_sensor_space_from_source_localization(eeg_raw):
    result = apply_csd(eeg_raw, channels=["Fz", "Cz", "Pz"], csd_callable=RecordingCallable())
    prov = result.provenance
    assert prov.transform_kind == TRANSFORM_KIND
    assert "not anatomical source localization" in prov.not_source_localization.lower()
    assert prov.not_source_localization == NOT_SOURCE_LOCALIZATION
    assert prov.mne_license == MNE_LICENSE
    assert "compute_current_source_density" in prov.api_function


def test_injected_callable_does_not_claim_mne_installed(eeg_raw):
    """Provenance.mne_available reflects importability, not injectable backends."""
    result = apply_csd(eeg_raw, channels=["Fz", "Cz", "Pz"], csd_callable=RecordingCallable())
    try:
        import mne  # noqa: F401
    except ImportError:
        assert result.provenance.mne_available is False
    else:
        assert result.provenance.mne_available is True


def test_dimensions_and_units_explicit(eeg_raw):
    result = apply_csd(eeg_raw, channels=["Fz", "Cz", "Pz"], csd_callable=RecordingCallable())
    assert result.data is not None
    assert len(result.data) == 3
    assert result.provenance.output_units == DOCUMENTED_OUTPUT_UNIT
    assert result.provenance.output_units_status == "documented"
    assert result.provenance.channel_types_requested == {
        "Fz": "eeg",
        "Cz": "eeg",
        "Pz": "eeg",
    }


def test_unknown_units_when_unmapped():
    def backend(inst, **kwargs):
        out = inst.copy()
        for ch in out.info["chs"]:
            ch["unit"] = "UNMAPPED_UNIT_TOKEN"
        out._data = [[0.0, 0.0] for _ in out.ch_names]
        return out

    raw = FakeRaw(["Fz", "Cz"], locs=standard_locs(2))
    result = apply_csd(raw, channels=["Fz", "Cz"], csd_callable=backend)
    assert result.provenance.output_units is None
    assert result.provenance.output_units_status == "unknown"
    assert any("unknown" in w for w in result.provenance.warnings)


def test_finite_json_provenance(eeg_raw):
    result = apply_csd(eeg_raw, channels=["Fz", "Cz", "Pz"], csd_callable=RecordingCallable())
    payload = result.provenance.to_dict()
    text = json.dumps(payload, allow_nan=False)
    json.loads(text, parse_constant=lambda t: (_ for _ in ()).throw(ValueError(t)))


def test_output_finite_for_deterministic_fixture(eeg_raw):
    result = apply_csd(eeg_raw, channels=["Fz", "Cz", "Pz"], csd_callable=RecordingCallable())
    assert result.data is not None
    for row in result.data:
        for value in row:
            assert math.isfinite(float(value))


def test_constant_common_offset_documented_reference_free_policy(eeg_raw):
    """Engineering check: adapter does not re-reference; policy is recorded.

    Numerical removal of a common offset is an upstream MNE property. Here we
    only assert the adapter's documented reference policy and that a constant
    offset fixture still yields finite output through the wired callable.
    """
    offset = 1.25
    eeg_raw._data = [[offset + i * 0.01 for i in range(5)] for _ in eeg_raw.ch_names]

    def backend(inst, **kwargs):
        # Model reference-free Laplacian: subtract channel-wise mean (common offset).
        out = inst.copy()
        data = out.get_data()
        means = [sum(row) / len(row) for row in data]
        # Spatially constant offset across channels -> removed in a Laplacian model.
        common = sum(means) / len(means)
        out._data = [[v - common for v in row] for row in data]
        for ch in out.info["chs"]:
            ch["unit"] = "V/m^2"
        return out

    result = apply_csd(eeg_raw, channels=["Fz", "Cz", "Pz"], csd_callable=backend)
    assert "does_not_call_set_eeg_reference" in result.provenance.reference_policy
    assert "reference-free" in result.provenance.reference_policy
    for row in result.data:
        for value in row:
            assert math.isfinite(float(value))


def test_output_units_unknown_when_backend_reports_no_unit():
    """'documented' needs a unit the backend reported; an absent unit is unknown."""

    def backend(inst, **kwargs):
        out = inst.copy()
        for ch in out.info["chs"]:
            ch["unit"] = None
        out._data = [[0.0, 0.0] for _ in out.ch_names]
        return out

    raw = FakeRaw(["Fz", "Cz"], locs=standard_locs(2))
    result = apply_csd(raw, channels=["Fz", "Cz"], csd_callable=backend)
    assert result.provenance.output_units is None
    assert result.provenance.output_units_status == "unknown"
