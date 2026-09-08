"""Comprehensive test suite for canonical feature contracts.

Verifies schema adherence, unit validation, axes and dimension matching,
channel uniqueness, mathematical guardrails, synthetic-empirical separation,
deterministic checksumming, serialization roundtrips, offline isolation, and CLI execution.
"""
from __future__ import annotations

import json
from pathlib import Path
import socket
import subprocess
import sys
from typing import Any

import pytest

from shared.feature_contracts import (
    CanonicalFeatureBundle,
    CanonicalFeatureRecord,
    CoordinateStatus,
    EvidenceClass,
    FeatureContractValidationError,
    FeatureFamily,
    FrequencyBand,
    TimeWindow,
    VALID_UNITS,
    bundle_from_dict,
    bundle_from_json,
    bundle_to_json,
    check_feature_compatibility,
    compute_bundle_checksum,
    compute_record_checksum,
    record_from_dict,
    record_from_json,
    record_to_json,
    validate_feature_bundle,
    validate_feature_record,
)


def _make_base_record(**overrides: Any) -> CanonicalFeatureRecord:
    kwargs: dict[str, Any] = {
        "feature_family": FeatureFamily.PSD.value,
        "feature_name": "alpha_psd",
        "mathematical_definition": "Welch power spectral density estimate in alpha band (8-13 Hz)",
        "units": "uV^2/Hz",
        "frequency_band": {"low_hz": 8.0, "high_hz": 13.0, "band_name": "alpha"},
        "time_window": {"start_s": 0.0, "duration_s": 30.0},
        "sampling_rate_hz": 250.0,
        "channel_node_identity": ["Fz", "Cz", "Pz", "Oz"],
        "coordinate_status": CoordinateStatus.THREE_D_MONTAGE.value,
        "montage_coordinates": [
            [0.0, 0.7, 0.5],
            [0.0, 0.0, 0.8],
            [0.0, -0.7, 0.5],
            [0.0, -1.0, 0.0],
        ],
        "subject": "sub-01",
        "session": "ses-01",
        "run": "run-01",
        "condition_label": "baseline_eyes_closed",
        "provenance_checksum": "a" * 64,
        "preprocessing": ["bandpass_0.5_45hz", "average_reference"],
        "missingness": 0.0,
        "uncertainty": {"method": "bootstrap_sem", "confidence_interval": 0.95},
        "is_synthetic": False,
        "evidence_class": EvidenceClass.EMPIRICAL_FEATURE.value,
        "axes": ["channel", "frequency"],
        "shape": [4, 3],
        "values": [[1.2, 2.3, 3.1], [0.9, 1.8, 2.5], [1.1, 2.0, 2.9], [1.5, 2.7, 3.8]],
    }
    kwargs.update(overrides)
    return CanonicalFeatureRecord(**kwargs)


class TestFeatureFamiliesAndUnits:
    """Verifies registration and validation of families and units."""

    def test_all_eleven_families_registered(self) -> None:
        expected_families = {
            "psd",
            "cross_spectrum",
            "pairwise_fc",
            "triadic_fc",
            "higher_order_spectra",
            "respiration",
            "ecg_hrv",
            "spatial_phase_charge",
            "graph_beta_1",
            "directed_hypergraph",
            "behavioral_transition_labels",
        }
        actual_families = {f.value for f in FeatureFamily}
        assert actual_families == expected_families
        assert len(actual_families) == 11

    def test_valid_records_across_all_eleven_families(self) -> None:
        family_configs = [
            (
                FeatureFamily.PSD.value,
                "alpha_psd",
                "Welch power spectral density estimate",
                "uV^2/Hz",
                ["channel", "frequency"],
                [2, 3],
                [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]],
                ["Fz", "Cz"],
                CoordinateStatus.MISSING.value,
                None,
            ),
            (
                FeatureFamily.CROSS_SPECTRUM.value,
                "csd_matrix",
                "Bivariate cross-spectral density matrix",
                "uV^2/Hz",
                ["channel_i", "channel_j", "frequency"],
                [2, 2, 2],
                [[[1.0, 1.0], [0.5, 0.5]], [[0.5, 0.5], [2.0, 2.0]]],
                ["Fz", "Cz"],
                CoordinateStatus.MISSING.value,
                None,
            ),
            (
                FeatureFamily.PAIRWISE_FC.value,
                "wpli_matrix",
                "Weighted phase lag index matrix",
                "dimensionless",
                ["channel_i", "channel_j"],
                [2, 2],
                [[1.0, 0.35], [0.35, 1.0]],
                ["Fz", "Cz"],
                CoordinateStatus.MISSING.value,
                None,
            ),
            (
                FeatureFamily.TRIADIC_FC.value,
                "o_information_triad",
                "Triadic O-information redundancy metric",
                "dimensionless",
                ["channel_i", "channel_j", "channel_k"],
                [2, 2, 2],
                [[[0.0, 0.1], [0.1, 0.2]], [[0.1, 0.2], [0.2, 0.0]]],
                ["Fz", "Cz"],
                CoordinateStatus.MISSING.value,
                None,
            ),
            (
                FeatureFamily.HIGHER_ORDER_SPECTRA.value,
                "bispectrum_bicoherence",
                "Normalized bicoherence magnitude",
                "dimensionless",
                ["channel", "freq1", "freq2"],
                [2, 2, 2],
                [[[0.1, 0.2], [0.2, 0.3]], [[0.2, 0.3], [0.3, 0.4]]],
                ["Fz", "Cz"],
                CoordinateStatus.MISSING.value,
                None,
            ),
            (
                FeatureFamily.RESPIRATION.value,
                "respiratory_rate",
                "Instantaneous chest-belt respiratory rate in breaths per minute",
                "bpm",
                ["time_window"],
                [3],
                [14.5, 15.0, 14.8],
                [],
                CoordinateStatus.MISSING.value,
                None,
            ),
            (
                FeatureFamily.ECG_HRV.value,
                "rmssd_hrv",
                "Root mean square of successive RR interval differences",
                "ms",
                ["time_window"],
                [3],
                [42.5, 45.1, 43.8],
                [],
                CoordinateStatus.MISSING.value,
                None,
            ),
            (
                FeatureFamily.SPATIAL_PHASE_CHARGE.value,
                "topological_charge_integral",
                "Curvature contour phase winding charge around sensor defect",
                "rad",
                ["charge_component"],
                [2],
                [1.57, -1.57],
                ["Fz", "Cz"],
                CoordinateStatus.THREE_D_MONTAGE.value,
                [[0.0, 0.7, 0.5], [0.0, 0.0, 0.8]],
            ),
            (
                FeatureFamily.GRAPH_BETA_1.value,
                "vietoris_rips_betti_1",
                "One-dimensional Betti persistence curve over correlation filtration",
                "counts",
                ["filtration_step"],
                [4],
                [0.0, 3.0, 1.0, 0.0],
                ["Fz", "Cz"],
                CoordinateStatus.MISSING.value,
                None,
            ),
            (
                FeatureFamily.DIRECTED_HYPERGRAPH.value,
                "hyperedge_directed_transition_index",
                "Higher-order directed hyperedge incidence asymmetry",
                "index",
                ["hyperedge_order"],
                [3],
                [0.12, 0.45, 0.88],
                ["Fz", "Cz"],
                CoordinateStatus.TOPOLOGICAL_ABSTRACT.value,
                None,
            ),
            (
                FeatureFamily.BEHAVIORAL_TRANSITION_LABELS.value,
                "responsiveness_state_indicator",
                "Binary behavioral responsiveness task transition indicator",
                "dimensionless",
                ["time_window"],
                [3],
                [1.0, 1.0, 0.0],
                [],
                CoordinateStatus.MISSING.value,
                None,
            ),
        ]

        for fam, name, defn, units, axes, shape, vals, channels, coord_stat, coords in family_configs:
            rec = _make_base_record(
                feature_family=fam,
                feature_name=name,
                mathematical_definition=defn,
                units=units,
                axes=axes,
                shape=shape,
                values=vals,
                channel_node_identity=channels,
                coordinate_status=coord_stat,
                montage_coordinates=coords,
            )
            validate_feature_record(rec)

    def test_units_whitelist_enforcement(self) -> None:
        rec = _make_base_record(units="uV^2/Hz")
        validate_feature_record(rec)

        with pytest.raises(FeatureContractValidationError, match="Invalid units 'millivolts'"):
            validate_feature_record(_make_base_record(units="millivolts"))

        with pytest.raises(FeatureContractValidationError, match="units must be a non-empty string"):
            validate_feature_record(_make_base_record(units=""))

    def test_unsupported_family_rejected(self) -> None:
        with pytest.raises(FeatureContractValidationError, match="Unrecognized feature_family: 'unregistered_family'"):
            validate_feature_record(_make_base_record(feature_family="unregistered_family"))


class TestAxesAndShapes:
    """Verifies multi-dimensional shape and axes alignment."""

    def test_shape_mismatch_rejected(self) -> None:
        rec = _make_base_record(
            shape=[4, 4],  # actually 4, 3
            axes=["channel", "frequency"],
        )
        with pytest.raises(FeatureContractValidationError, match="Declared shape \\[4, 4\\] does not match inferred shape \\[4, 3\\]"):
            validate_feature_record(rec)

    def test_axes_length_mismatch_rejected(self) -> None:
        rec = _make_base_record(
            shape=[4, 3],
            axes=["channel"],  # length 1 vs 2 dims
        )
        with pytest.raises(FeatureContractValidationError, match="Length of axes \\(1\\) does not match dimensionality \\(2\\)"):
            validate_feature_record(rec)

    def test_null_values_with_empty_axes_and_shape(self) -> None:
        rec = _make_base_record(values=None, axes=[], shape=[])
        validate_feature_record(rec)

    def test_null_values_with_nonempty_axes_rejected(self) -> None:
        rec = _make_base_record(values=None, axes=["channel"], shape=[])
        with pytest.raises(FeatureContractValidationError, match="shape and axes must be empty when values is null"):
            validate_feature_record(rec)


class TestFiniteValuesAndDuplicates:
    """Verifies strict finite numbers and channel uniqueness."""

    def test_non_finite_values_rejected(self) -> None:
        rec = _make_base_record(values=[[1.0, float("nan"), 3.0], [0.9, 1.8, 2.5], [1.1, 2.0, 2.9], [1.5, 2.7, 3.8]])
        with pytest.raises(FeatureContractValidationError, match="Non-finite value detected"):
            validate_feature_record(rec)

        rec_inf = _make_base_record(values=[[1.0, float("inf"), 3.0], [0.9, 1.8, 2.5], [1.1, 2.0, 2.9], [1.5, 2.7, 3.8]])
        with pytest.raises(FeatureContractValidationError, match="Non-finite value detected"):
            validate_feature_record(rec_inf)

    def test_duplicate_channel_identities_rejected(self) -> None:
        rec = _make_base_record(channel_node_identity=["Fz", "Cz", "Fz", "Pz"])
        with pytest.raises(FeatureContractValidationError, match="Duplicate channel/node identities detected: \\['Fz'\\]"):
            validate_feature_record(rec)

    def test_montage_coordinates_length_mismatch_rejected(self) -> None:
        rec = _make_base_record(
            channel_node_identity=["Fz", "Cz", "Pz", "Oz"],
            montage_coordinates=[[0.0, 0.7, 0.5]],  # length 1 vs 4
            coordinate_status=CoordinateStatus.THREE_D_MONTAGE.value,
        )
        with pytest.raises(FeatureContractValidationError, match="montage_coordinates length \\(1\\) does not match channel_node_identity length \\(4\\)"):
            validate_feature_record(rec)

    def test_montage_coordinates_with_missing_status_rejected(self) -> None:
        rec = _make_base_record(
            montage_coordinates=[[0.0, 0.7, 0.5], [0.0, 0.0, 0.8], [0.0, -0.7, 0.5], [0.0, -1.0, 0.0]],
            coordinate_status=CoordinateStatus.MISSING.value,
        )
        with pytest.raises(FeatureContractValidationError, match="montage_coordinates provided but coordinate_status is marked 'missing'"):
            validate_feature_record(rec)


class TestMissingMetadataNullRule:
    """Verifies that missing metadata is represented as null, never 0 or 0.0."""

    def test_zero_sampling_rate_rejected(self) -> None:
        rec = _make_base_record(sampling_rate_hz=0.0)
        with pytest.raises(FeatureContractValidationError, match="sampling_rate_hz must be strictly positive or null"):
            validate_feature_record(rec)

        rec_neg = _make_base_record(sampling_rate_hz=-100.0)
        with pytest.raises(FeatureContractValidationError, match="sampling_rate_hz must be strictly positive or null"):
            validate_feature_record(rec_neg)

        rec_none = _make_base_record(sampling_rate_hz=None)
        validate_feature_record(rec_none)

    def test_invalid_frequency_band_rejected(self) -> None:
        rec = _make_base_record(frequency_band={"low_hz": 15.0, "high_hz": 10.0})
        with pytest.raises(FeatureContractValidationError, match="frequency_band must have low_hz >= 0 and high_hz > low_hz"):
            validate_feature_record(rec)

    def test_invalid_time_window_rejected(self) -> None:
        rec = _make_base_record(time_window={"start_s": 0.0, "duration_s": 0.0})
        with pytest.raises(FeatureContractValidationError, match="time_window must specify duration_s > 0"):
            validate_feature_record(rec)


class TestMathematicalGuardrails:
    """Verifies scientific boundary guardrails across feature families."""

    def test_graph_beta_1_cannot_claim_spatial_charge(self) -> None:
        rec = _make_base_record(
            feature_family=FeatureFamily.GRAPH_BETA_1.value,
            feature_name="vietoris_rips_betti_1",
            mathematical_definition="One-dimensional Betti number measuring spatial_charge on cortex",
            units="counts",
            axes=["filtration_step"],
            shape=[4],
            values=[0.0, 2.0, 1.0, 0.0],
            channel_node_identity=[],
            coordinate_status=CoordinateStatus.MISSING.value,
            montage_coordinates=None,
        )
        with pytest.raises(FeatureContractValidationError, match="Graph beta-1 features cannot claim spatial phase charge"):
            validate_feature_record(rec)

    def test_spatial_phase_charge_requires_coordinates_and_cannot_claim_betti(self) -> None:
        # Missing coordinates
        rec_no_coords = _make_base_record(
            feature_family=FeatureFamily.SPATIAL_PHASE_CHARGE.value,
            feature_name="phase_winding_index",
            mathematical_definition="Contour phase winding integral",
            units="rad",
            axes=["charge_component"],
            shape=[2],
            values=[1.0, -1.0],
            channel_node_identity=["Fz", "Cz"],
            coordinate_status=CoordinateStatus.MISSING.value,
            montage_coordinates=None,
        )
        with pytest.raises(FeatureContractValidationError, match="spatial_phase_charge family requires valid montage coordinates"):
            validate_feature_record(rec_no_coords)

        # Claiming betti_1
        rec_betti = _make_base_record(
            feature_family=FeatureFamily.SPATIAL_PHASE_CHARGE.value,
            feature_name="phase_winding_index",
            mathematical_definition="Contour phase winding integral calculating betti_1 cycles",
            units="rad",
            axes=["charge_component"],
            shape=[2],
            values=[1.0, -1.0],
            channel_node_identity=["Fz", "Cz"],
            coordinate_status=CoordinateStatus.THREE_D_MONTAGE.value,
            montage_coordinates=[[0.0, 0.7, 0.5], [0.0, 0.0, 0.8]],
        )
        with pytest.raises(FeatureContractValidationError, match="Spatial phase charge cannot claim graph persistent homology cycles"):
            validate_feature_record(rec_betti)

    def test_triadic_fc_cannot_claim_causality(self) -> None:
        rec = _make_base_record(
            feature_family=FeatureFamily.TRIADIC_FC.value,
            feature_name="causal_driver_triad",
            mathematical_definition="Higher-order interaction reflecting granger_causality between trios",
            units="dimensionless",
            axes=["channel_i", "channel_j", "channel_k"],
            shape=[2, 2, 2],
            values=[[[0.0, 0.1], [0.1, 0.2]], [[0.1, 0.2], [0.2, 0.0]]],
            channel_node_identity=["Fz", "Cz"],
            coordinate_status=CoordinateStatus.MISSING.value,
            montage_coordinates=None,
        )
        with pytest.raises(FeatureContractValidationError, match="Triadic FC reflects higher-order statistical dependence and cannot claim causality"):
            validate_feature_record(rec)

    def test_higher_order_spectra_cannot_claim_topology(self) -> None:
        rec = _make_base_record(
            feature_family=FeatureFamily.HIGHER_ORDER_SPECTRA.value,
            feature_name="bispectrum_feature",
            mathematical_definition="Trispectral phase coupling defining a betti_number invariant",
            units="dimensionless",
            axes=["channel", "freq1", "freq2"],
            shape=[2, 2, 2],
            values=[[[0.1, 0.2], [0.2, 0.3]], [[0.2, 0.3], [0.3, 0.4]]],
            channel_node_identity=["Fz", "Cz"],
            coordinate_status=CoordinateStatus.MISSING.value,
            montage_coordinates=None,
        )
        with pytest.raises(FeatureContractValidationError, match="Trispectral modulation reflects phase-amplitude coupling and cannot claim topology"):
            validate_feature_record(rec)

    def test_respiration_cannot_claim_consciousness(self) -> None:
        rec = _make_base_record(
            feature_family=FeatureFamily.RESPIRATION.value,
            feature_name="respiration_rate",
            mathematical_definition="Breath rate indicating depth_of_anesthesia and conscious_state",
            units="bpm",
            axes=["time_window"],
            shape=[3],
            values=[14.0, 15.0, 14.5],
            channel_node_identity=[],
            coordinate_status=CoordinateStatus.MISSING.value,
            montage_coordinates=None,
        )
        with pytest.raises(FeatureContractValidationError, match="Respiration cannot claim direct cognitive arousal or consciousness state"):
            validate_feature_record(rec)

    def test_eeg_cannot_claim_discernment(self) -> None:
        rec = _make_base_record(
            feature_family=FeatureFamily.PSD.value,
            feature_name="discernment_score_alpha",
            mathematical_definition="Welch power spectral density alpha band indexing spiritual discernment",
            units="uV^2/Hz",
        )
        with pytest.raises(FeatureContractValidationError, match="Mental discernment/cognitive awareness cannot be inferred from EEG alone"):
            validate_feature_record(rec)


class TestSyntheticEvidenceSeparation:
    """Verifies that synthetic scaffolding cannot claim empirical evidence."""

    def test_synthetic_claiming_empirical_rejected(self) -> None:
        rec = _make_base_record(
            is_synthetic=True,
            evidence_class=EvidenceClass.EMPIRICAL_FEATURE.value,
        )
        with pytest.raises(FeatureContractValidationError, match="Synthetic feature cannot enter formal empirical evidence"):
            validate_feature_record(rec)

    def test_synthetic_with_synthetic_scaffolding_accepted(self) -> None:
        rec = _make_base_record(
            is_synthetic=True,
            evidence_class=EvidenceClass.SYNTHETIC_SCAFFOLDING.value,
        )
        validate_feature_record(rec)


class TestBundleValidationAndCompatibility:
    """Verifies bundle consistency and multi-family compatibility checks."""

    def test_bundle_validation_success(self) -> None:
        rec1 = _make_base_record(feature_name="psd_1")
        rec2 = _make_base_record(feature_name="psd_2")
        bundle = CanonicalFeatureBundle(
            bundle_id="bundle-sub01-ses01",
            subject="sub-01",
            session="ses-01",
            run="run-01",
            condition_label="baseline_eyes_closed",
            is_synthetic=False,
            records=[rec1, rec2],
        )
        validate_feature_bundle(bundle)

    def test_bundle_subject_mismatch_rejected(self) -> None:
        rec1 = _make_base_record(subject="sub-02")
        bundle = CanonicalFeatureBundle(
            bundle_id="bundle-sub01-ses01",
            subject="sub-01",
            records=[rec1],
        )
        with pytest.raises(FeatureContractValidationError, match="Record \\[0\\] subject 'sub-02' does not match bundle subject 'sub-01'"):
            validate_feature_bundle(bundle)

    def test_feature_compatibility_checks(self) -> None:
        rec_a = _make_base_record(
            feature_family=FeatureFamily.PSD.value,
            subject="sub-01",
            condition_label="eyes_closed",
            channel_node_identity=["Fz", "Cz"],
        )
        rec_b = _make_base_record(
            feature_family=FeatureFamily.PAIRWISE_FC.value,
            subject="sub-01",
            condition_label="eyes_closed",
            channel_node_identity=["Cz", "Pz"],
            units="dimensionless",
            axes=["channel_i", "channel_j"],
            shape=[2, 2],
            values=[[1.0, 0.4], [0.4, 1.0]],
        )
        compatible, errs = check_feature_compatibility(rec_a, rec_b)
        assert compatible is True
        assert len(errs) == 0

        # Mismatched subjects
        rec_diff_sub = _make_base_record(subject="sub-02")
        compatible, errs = check_feature_compatibility(rec_a, rec_diff_sub)
        assert compatible is False
        assert any("Mismatched subjects" in e for e in errs)


class TestDeterministicSerializationAndChecksums:
    """Verifies deterministic sorting, JSON serialization, and SHA-256 checksums."""

    def test_record_serialization_roundtrip(self) -> None:
        rec = _make_base_record()
        json_str = record_to_json(rec)
        rec_loaded = record_from_json(json_str)
        assert rec_loaded.feature_name == rec.feature_name
        assert rec_loaded.checksum == rec.checksum
        assert len(rec_loaded.checksum) == 64

    def test_deterministic_checksum_stability(self) -> None:
        rec1 = _make_base_record()
        rec2 = _make_base_record()
        cs1 = compute_record_checksum(rec1)
        cs2 = compute_record_checksum(rec2)
        assert cs1 == cs2
        assert len(cs1) == 64

    def test_bundle_serialization_roundtrip(self) -> None:
        rec1 = _make_base_record(feature_name="psd_b")
        rec2 = _make_base_record(feature_name="psd_a")
        bundle = CanonicalFeatureBundle(
            bundle_id="bundle-01",
            subject="sub-01",
            records=[rec1, rec2],
        )
        json_str = bundle_to_json(bundle)
        bundle_loaded = bundle_from_json(json_str)
        assert bundle_loaded.bundle_id == "bundle-01"
        assert len(bundle_loaded.records) == 2
        # Records sorted canonically
        assert bundle_loaded.records[0].feature_name == "psd_a"
        assert bundle_loaded.records[1].feature_name == "psd_b"
        assert len(bundle_loaded.bundle_checksum) == 64


class TestZeroNetworkExecution:
    """Verifies that all serialization, models, and validation run strictly offline."""

    def test_offline_execution_enforced(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def forbidden_connect(*args: Any, **kwargs: Any) -> None:
            raise RuntimeError("CRITICAL: Network socket connection attempted during feature contract execution.")

        monkeypatch.setattr(socket.socket, "connect", forbidden_connect)

        rec = _make_base_record()
        validate_feature_record(rec)
        json_str = record_to_json(rec)
        deserialized = record_from_json(json_str)
        assert deserialized.feature_name == rec.feature_name


class TestCLIValidator:
    """Verifies scripts/validate_feature_contract.py behavior via subprocess."""

    def test_cli_valid_record_and_bundle(self, tmp_path: Path) -> None:
        rec = _make_base_record()
        rec_path = tmp_path / "valid_record.json"
        rec_path.write_text(record_to_json(rec), encoding="utf-8")

        bundle = CanonicalFeatureBundle(
            bundle_id="bundle-test",
            subject="sub-01",
            records=[rec],
        )
        bundle_path = tmp_path / "valid_bundle.json"
        bundle_path.write_text(bundle_to_json(bundle), encoding="utf-8")

        summary_path = tmp_path / "report.json"
        cmd = [
            sys.executable,
            str(Path(__file__).resolve().parents[2] / "scripts" / "validate_feature_contract.py"),
            "--input",
            str(tmp_path),
            "--output",
            str(summary_path),
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        assert res.returncode == 0
        assert summary_path.exists()
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        assert summary["total_files"] == 2
        assert summary["valid_count"] == 2
        assert summary["invalid_count"] == 0
        assert summary["all_valid"] is True

    def test_cli_invalid_record_returns_exit_code_2(self, tmp_path: Path) -> None:
        invalid_rec = {
            "schema_version": "NeuroTopologySim.CanonicalFeatureRecord.v1",
            "feature_family": "psd",
            "feature_name": "bad_units",
            "mathematical_definition": "Welch PSD",
            "units": "illegal_unit_string",
        }
        rec_path = tmp_path / "invalid_record.json"
        rec_path.write_text(json.dumps(invalid_rec), encoding="utf-8")

        cmd = [
            sys.executable,
            str(Path(__file__).resolve().parents[2] / "scripts" / "validate_feature_contract.py"),
            "--input",
            str(rec_path),
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        assert res.returncode == 2
        report = json.loads(res.stdout)
        assert report["valid_count"] == 0
        assert report["invalid_count"] == 1
        assert "Invalid units" in report["results"][0]["errors"][0]
