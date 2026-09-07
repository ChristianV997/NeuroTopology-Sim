"""Tests for canonical adapter selection and duplicate resolution layer.

Verifies:
- one available adapter
- two compatible adapters
- conflicting and ambiguous adapters
- missing optional dependency
- malformed metadata
- native versus fallback preference
- deterministic repeated selection
- channel-order mismatch
- sampling-rate mismatch
- montage provenance mismatch
- no-network execution
- never loads complete recording
- duplicate detection
"""
from __future__ import annotations

from pathlib import Path
import pytest

from shared.interop.adapter_selection import (
    AdapterCandidate,
    AdapterTier,
    CanonicalAdapterSelector,
    ReasonCode,
    SelectionRequest,
    SelectionResult,
    SelectionStatus,
    detect_format_from_path,
    select_adapter,
)


# ---------------------------------------------------------------------------
# 1. Format Detection from Path (without reading file)
# ---------------------------------------------------------------------------
def test_format_detection_from_path() -> None:
    """Format is detected solely by path extension without opening file."""
    assert detect_format_from_path("sub-01_ses-01_task-rest_eeg.fif") == "fif"
    assert detect_format_from_path("sub-01_ses-01_task-rest_eeg.fif.gz") == "fif"
    assert detect_format_from_path("sub-01_eeg.edf") == "edf"
    assert detect_format_from_path("sub-01_eeg.bdf") == "bdf"
    assert detect_format_from_path("recording.vhdr") == "brainvision"
    assert detect_format_from_path("recording.vmrk") == "brainvision"
    assert detect_format_from_path("recording.eeg") == "brainvision"
    assert detect_format_from_path("fixture.npy") == "npy"
    assert detect_format_from_path("fixture.npz") == "npy"
    assert detect_format_from_path("calibration.csv") == "csv"
    assert detect_format_from_path("unknown.dat") is None


# ---------------------------------------------------------------------------
# 2. One Available Adapter
# ---------------------------------------------------------------------------
def test_one_available_adapter() -> None:
    """When exactly one adapter matches and is available, it is selected."""
    # Mock dependency checker where 'numpy' is available
    def mock_checker(dep: str) -> bool:
        return dep == "numpy"

    selector = CanonicalAdapterSelector(dependency_checker=mock_checker)
    res = selector.select(SelectionRequest(source_path="data.csv"))
    assert res.status == SelectionStatus.SELECTED
    assert res.selected_adapter == "csv_adapter"
    assert res.reason_code == ReasonCode.SINGLE_MATCH
    assert res.target_format == "csv"


# ---------------------------------------------------------------------------
# 3. Two Compatible Adapters & Native Preference
# ---------------------------------------------------------------------------
def test_two_compatible_adapters_prefer_native() -> None:
    """When both native and fallback adapters are available, native is preferred."""
    # Both numpy (native) and mne (fallback) are available
    def mock_checker(dep: str) -> bool:
        return True

    selector = CanonicalAdapterSelector(dependency_checker=mock_checker)
    res = selector.select(SelectionRequest(source_path="subject.edf"))

    assert res.status == SelectionStatus.SELECTED
    assert res.selected_adapter == "native_edf"
    assert res.reason_code == ReasonCode.NATIVE_PREFERRED
    assert "native_edf" in res.candidate_adapters
    assert "mne_edf" in res.candidate_adapters
    assert len(res.duplicate_adapters) == 2


# ---------------------------------------------------------------------------
# 4. Fallback Selected When Native Unavailable
# ---------------------------------------------------------------------------
def test_fallback_selected_when_native_unavailable() -> None:
    """When native is missing its dependency, fallback is selected if allowed."""
    # Custom candidates where native requires 'native_lib' (unavailable), fallback requires 'mne' (available)
    candidates = [
        AdapterCandidate(
            adapter_name="custom_native_bv",
            tier=AdapterTier.NATIVE,
            supported_formats=("brainvision",),
            dependency="native_lib",
            priority=100,
        ),
        AdapterCandidate(
            adapter_name="custom_fallback_bv",
            tier=AdapterTier.FALLBACK,
            supported_formats=("brainvision",),
            dependency="mne",
            priority=50,
        ),
    ]

    def mock_checker(dep: str) -> bool:
        return dep == "mne"

    selector = CanonicalAdapterSelector(candidates=candidates, dependency_checker=mock_checker)

    # With allow_fallback=True
    res = selector.select(SelectionRequest(source_path="recording.vhdr", allow_fallback=True))
    assert res.status == SelectionStatus.FALLBACK_SELECTED
    assert res.selected_adapter == "custom_fallback_bv"
    assert res.reason_code == ReasonCode.FALLBACK_PRIMARY_UNAVAILABLE

    # With allow_fallback=False
    res_no_fb = selector.select(SelectionRequest(source_path="recording.vhdr", allow_fallback=False))
    assert res_no_fb.status == SelectionStatus.UNAVAILABLE
    assert res_no_fb.reason_code == ReasonCode.DEPENDENCY_MISSING
    assert res_no_fb.selected_adapter is None


# ---------------------------------------------------------------------------
# 5. Conflicting and Ambiguous Adapters
# ---------------------------------------------------------------------------
def test_ambiguous_selection_refused() -> None:
    """When multiple native adapters compete with equal priority, selection is refused as ambiguous."""
    candidates = [
        AdapterCandidate(
            adapter_name="native_edf_alpha",
            tier=AdapterTier.NATIVE,
            supported_formats=("edf",),
            dependency="numpy",
            priority=100,
        ),
        AdapterCandidate(
            adapter_name="native_edf_beta",
            tier=AdapterTier.NATIVE,
            supported_formats=("edf",),
            dependency="numpy",
            priority=100,
        ),
    ]

    selector = CanonicalAdapterSelector(candidates=candidates, dependency_checker=lambda d: True)
    res = selector.select(SelectionRequest(source_path="patient.edf"))

    assert res.status == SelectionStatus.AMBIGUOUS
    assert res.selected_adapter is None
    assert res.reason_code == ReasonCode.AMBIGUOUS_CANDIDATES
    assert set(res.candidate_adapters) == {"native_edf_alpha", "native_edf_beta"}


# ---------------------------------------------------------------------------
# 6. Missing Optional Dependency
# ---------------------------------------------------------------------------
def test_missing_optional_dependency() -> None:
    """When all candidate dependencies are missing, outcome is UNAVAILABLE."""
    selector = CanonicalAdapterSelector(dependency_checker=lambda d: False)
    res = selector.select(SelectionRequest(source_path="experiment.fif"))

    assert res.status == SelectionStatus.UNAVAILABLE
    assert res.selected_adapter is None
    assert res.reason_code == ReasonCode.DEPENDENCY_MISSING
    assert res.dependency_status.get("mne_fif") is False


# ---------------------------------------------------------------------------
# 7. Malformed Metadata Rejection
# ---------------------------------------------------------------------------
def test_malformed_metadata_rejection() -> None:
    """Non-finite or non-positive sample rates and empty channel names are rejected."""
    selector = CanonicalAdapterSelector(dependency_checker=lambda d: True)

    # Negative sample rate
    res_neg = selector.select(SelectionRequest(source_path="test.edf", required_sample_rate=-100.0))
    assert res_neg.status == SelectionStatus.INCOMPATIBLE
    assert res_neg.reason_code == ReasonCode.MALFORMED_METADATA

    # NaN sample rate
    res_nan = selector.select(SelectionRequest(source_path="test.edf", required_sample_rate=float("nan")))
    assert res_nan.status == SelectionStatus.INCOMPATIBLE
    assert res_nan.reason_code == ReasonCode.MALFORMED_METADATA

    # Empty string channel name
    res_chan = selector.select(SelectionRequest(source_path="test.edf", required_channels=("Fp1", "")))
    assert res_chan.status == SelectionStatus.INCOMPATIBLE
    assert res_chan.reason_code == ReasonCode.MALFORMED_METADATA


# ---------------------------------------------------------------------------
# 8. Channel Order Mismatch
# ---------------------------------------------------------------------------
def test_channel_order_mismatch() -> None:
    """Channel order mismatch between requested and expected metadata is detected."""
    selector = CanonicalAdapterSelector(dependency_checker=lambda d: True)
    metadata = {"expected_channel_order": ("Fp1", "Fp2", "C3", "C4")}

    res = selector.select(
        SelectionRequest(
            source_path="recording.edf",
            required_channels=("Fp2", "Fp1", "C3", "C4"),  # Permuted
            metadata=metadata,
        )
    )
    assert res.status == SelectionStatus.INCOMPATIBLE
    assert res.reason_code == ReasonCode.CHANNEL_ORDER_MISMATCH
    assert res.selected_adapter is None


# ---------------------------------------------------------------------------
# 9. Sampling Rate Mismatch
# ---------------------------------------------------------------------------
def test_sampling_rate_mismatch() -> None:
    """Sampling rate mismatch between requested and expected metadata is detected."""
    selector = CanonicalAdapterSelector(dependency_checker=lambda d: True)
    metadata = {"expected_sample_rate": 1000.0}

    res = selector.select(
        SelectionRequest(
            source_path="recording.edf",
            required_sample_rate=500.0,
            metadata=metadata,
        )
    )
    assert res.status == SelectionStatus.INCOMPATIBLE
    assert res.reason_code == ReasonCode.SAMPLE_RATE_MISMATCH


# ---------------------------------------------------------------------------
# 10. Montage Provenance Mismatch
# ---------------------------------------------------------------------------
def test_montage_provenance_mismatch() -> None:
    """When montage coordinates are required but format adapter lacks montage support, it fails."""
    selector = CanonicalAdapterSelector(dependency_checker=lambda d: True)
    # npy array reader does not have montage support
    res = selector.select(
        SelectionRequest(
            source_path="array_data.npy",
            require_montage=True,
        )
    )
    assert res.status == SelectionStatus.INCOMPATIBLE
    assert res.reason_code == ReasonCode.MONTAGE_UNSUPPORTED


# ---------------------------------------------------------------------------
# 11. No-Network Execution & Network Restrictions
# ---------------------------------------------------------------------------
def test_no_network_execution() -> None:
    """Candidate requiring network communication is rejected when allow_network=False."""
    candidates = [
        AdapterCandidate(
            adapter_name="cloud_stream_adapter",
            tier=AdapterTier.NATIVE,
            supported_formats=("cloud-stream",),
            dependency="numpy",
            network_requirement="required",
        ),
    ]
    selector = CanonicalAdapterSelector(candidates=candidates, dependency_checker=lambda d: True)

    res = selector.select(SelectionRequest(file_format="cloud-stream", allow_network=False))
    assert res.status == SelectionStatus.INCOMPATIBLE
    assert res.reason_code == ReasonCode.NETWORK_NOT_ALLOWED


# ---------------------------------------------------------------------------
# 12. Deterministic Repeated Selection
# ---------------------------------------------------------------------------
def test_deterministic_repeated_selection() -> None:
    """Repeated selection queries produce 100% identical results and reason codes."""
    selector = CanonicalAdapterSelector(dependency_checker=lambda d: True)
    req = SelectionRequest(source_path="patient_record.bdf")

    results = [selector.select(req) for _ in range(15)]
    first = results[0]
    for r in results[1:]:
        assert r.status == first.status
        assert r.selected_adapter == first.selected_adapter
        assert r.reason_code == first.reason_code
        assert r.candidate_adapters == first.candidate_adapters
        assert r.duplicate_adapters == first.duplicate_adapters


# ---------------------------------------------------------------------------
# 13. Never Loads Complete Recording
# ---------------------------------------------------------------------------
def test_never_loads_complete_recording() -> None:
    """Selection operates on virtual/non-existent paths without attempting disk I/O."""
    selector = CanonicalAdapterSelector(dependency_checker=lambda d: True)
    # Path does not exist on disk
    virtual_path = Path("/nonexistent/storage/terabyte_recording_001.edf")
    res = selector.select(SelectionRequest(source_path=virtual_path))

    assert res.status == SelectionStatus.SELECTED
    assert res.selected_adapter == "native_edf"
    assert res.target_format == "edf"


# ---------------------------------------------------------------------------
# 14. Duplicate Detection
# ---------------------------------------------------------------------------
def test_detect_duplicates() -> None:
    """Detects competing duplicate adapters across the ecosystem."""
    selector = CanonicalAdapterSelector()
    dups = selector.detect_duplicates()

    # EDF has both native_edf and mne_edf
    assert "edf" in dups
    assert set(dups["edf"]) == {"native_edf", "mne_edf"}

    # BrainVision has both native_brainvision and mne_brainvision
    assert "brainvision" in dups
    assert set(dups["brainvision"]) == {"native_brainvision", "mne_brainvision"}

    # Filtered detection
    dups_edf = selector.detect_duplicates("edf")
    assert "edf" in dups_edf
    assert "brainvision" not in dups_edf
