"""Unit and integration tests for local streaming paired-cohort topology execution."""

from __future__ import annotations

import csv
import json
from pathlib import Path
import numpy as np
import pytest

from shared.data_loaders.cohort_manifest import (
    CohortManifest,
    CohortStatus,
    PairedSubjectRecord,
    ProvenanceRecord,
    RecordingRecord,
)
from scripts.cohort_topology_runner import (
    build_parser,
    execute_cohort_topology,
    load_and_validate_manifest,
    main,
    stream_file_chunks,
)


class TestCohortTopologyRunner:
    """Rigorous validation of the local streaming cohort topology execution runner."""

    def test_empty_manifest_refusal(self, tmp_path: Path):
        """Empty manifest (no_data) must refuse execution unless diagnostic-only."""
        empty_manifest = tmp_path / "empty_manifest.json"
        empty_manifest.write_text(json.dumps({
            "schema": "NeuroTopologySim.PairedCohortManifest.v1",
            "status": "no_data",
            "status_reason": "Zero recordings discovered",
            "paired_records": [],
        }), encoding="utf-8")

        out_dir = tmp_path / "out_empty"
        res = execute_cohort_topology(empty_manifest, out_dir)

        assert res["execution_status"] == "REFUSED"
        assert res["pairs_processed"] == 0
        assert any("no_data" in r for r in res["refusal_reasons"])
        assert (out_dir / "cohort_topology_execution_summary.json").is_file()

        # Diagnostic-only bypasses refusal
        diag_res = execute_cohort_topology(empty_manifest, out_dir, diagnostic_only=True)
        assert diag_res["execution_status"] == "NO_PAIRS_PROCESSED"

    def test_insufficient_pairs_refusal(self, tmp_path: Path, make_paired_manifest):
        """Manifest reporting insufficient_pairs must refuse execution unless allowed."""
        manifest_file = make_paired_manifest(n_pairs=1, status=CohortStatus.INSUFFICIENT_PAIRS)
        out_dir = tmp_path / "out_insufficient"

        # Default run: refuses execution
        res = execute_cohort_topology(manifest_file, out_dir)
        assert res["execution_status"] == "REFUSED"
        assert any("insufficient_pairs" in r for r in res["refusal_reasons"])

        # Allowed with flag
        res_allowed = execute_cohort_topology(manifest_file, out_dir, allow_insufficient=True)
        assert res_allowed["execution_status"] in ("SYNTHETIC_EVALUATION", "INSUFFICIENT_PAIRS_PROCESSED")
        assert res_allowed["pairs_processed"] == 1

    def test_malformed_manifest_refusal(self, tmp_path: Path):
        """Corrupt JSON or malformed cohort status must refuse execution."""
        bad_json = tmp_path / "corrupt.json"
        bad_json.write_text("NOT_VALID_JSON{}[", encoding="utf-8")

        out_dir = tmp_path / "out_malformed"
        res = execute_cohort_topology(bad_json, out_dir)
        assert res["execution_status"] == "REFUSED"
        assert any("Malformed JSON" in r for r in res["refusal_reasons"])

        # Nonexistent file
        res_missing = execute_cohort_topology(tmp_path / "nonexistent.json", out_dir)
        assert res_missing["execution_status"] == "REFUSED"
        assert any("not found" in r for r in res_missing["refusal_reasons"])

    def test_ambiguous_labels_refusal(self, tmp_path: Path, make_paired_manifest):
        """Manifest with ambiguous matches must refuse execution unless diagnostic-only."""
        ambiguous = [{"file_path": "sub-01.npy", "reason": "condition_matches_both_a_and_b"}]
        manifest_file = make_paired_manifest(n_pairs=2, ambiguous_matches=ambiguous)
        out_dir = tmp_path / "out_ambiguous"

        res = execute_cohort_topology(manifest_file, out_dir)
        assert res["execution_status"] == "REFUSED"
        assert any("ambiguous matches" in r for r in res["refusal_reasons"])

        # Diagnostic-only bypasses
        res_diag = execute_cohort_topology(manifest_file, out_dir, diagnostic_only=True)
        assert res_diag["execution_status"] != "REFUSED"
        assert res_diag["pairs_processed"] == 2

    def test_valid_paired_manifest(self, tmp_path: Path, make_paired_manifest):
        """Processes valid paired cohort, produces JSON and CSV with descriptive metrics."""
        manifest_file = make_paired_manifest(n_pairs=2, status=CohortStatus.VALID_PAIRED_COHORT)
        out_dir = tmp_path / "out_valid"

        res = execute_cohort_topology(
            manifest_file,
            out_dir,
            chunk_samples=500,
            max_windows=4,
        )

        assert res["execution_status"] in ("VALID_COHORT_PROCESSED", "SYNTHETIC_EVALUATION")
        assert res["pairs_processed"] == 2
        assert res["pairs_skipped"] == 0

        # Check output artifacts
        json_file = out_dir / "cohort_topology_execution_summary.json"
        csv_file = out_dir / "cohort_topology_execution_summary.csv"
        assert json_file.is_file()
        assert csv_file.is_file()

        # Check metrics on processed pairs
        pair0 = res["processed_pairs"][0]
        assert "delta_landscape_area" in pair0
        assert pair0["delta_landscape_area"] >= 0.0

        cond_a = pair0["condition_a"]
        assert cond_a["sample_count"] == 2000
        assert cond_a["channel_count"] == 4
        assert cond_a["sampling_rate_hz"] == 250.0
        assert cond_a["windows_processed"] == 4
        assert cond_a["finite_value_status"] is True

        # Graph beta-1 metrics
        assert "mean_filtration_beta1_max" in cond_a["beta1_summary"]
        assert "mean_beta1" in cond_a["beta1_summary"]

        # CSV checks
        with csv_file.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            assert len(rows) == 2
            assert "delta_landscape_area" in rows[0]
            assert "cond_a_mean_beta1" in rows[0]

    def test_one_malformed_subject_among_valid_subjects(self, tmp_path: Path, make_paired_manifest, make_mock_npy):
        """Runner continues processing valid pairs and records corrupt pair in skipped_pairs."""
        manifest_file = make_paired_manifest(n_pairs=3)
        data = json.loads(manifest_file.read_text(encoding="utf-8"))

        # Corrupt condition_b of pair 1 (second pair)
        corrupt_file = tmp_path / "corrupt_sub2.npy"
        corrupt_file.write_bytes(b"INVALID_NPY_HEADER_BYTES")
        data["paired_records"][1]["condition_b_record"]["file_path"] = str(corrupt_file)
        manifest_file.write_text(json.dumps(data), encoding="utf-8")

        out_dir = tmp_path / "out_partial_skip"
        res = execute_cohort_topology(manifest_file, out_dir)

        assert res["pairs_processed"] == 2
        assert res["pairs_skipped"] == 1

        # Skipped pair recorded with exact reason
        skipped = res["skipped_pairs"]
        assert len(skipped) == 1
        assert skipped[0]["pairing_key"] == {"subject": "sub-002"}
        assert skipped[0]["status"] == "SKIPPED"
        assert len(skipped[0]["reason"]) > 0

    def test_deterministic_repeat(self, tmp_path: Path, make_paired_manifest):
        """Repeated runs on identical inputs yield identical numerical outputs."""
        manifest_file = make_paired_manifest(n_pairs=2)
        out_1 = tmp_path / "out_repeat_1"
        out_2 = tmp_path / "out_repeat_2"

        res1 = execute_cohort_topology(manifest_file, out_1, seed=42)
        res2 = execute_cohort_topology(manifest_file, out_2, seed=42)

        area1_0 = res1["processed_pairs"][0]["delta_landscape_area"]
        area2_0 = res2["processed_pairs"][0]["delta_landscape_area"]
        assert np.isclose(area1_0, area2_0, atol=1e-12)

        beta1_0 = res1["processed_pairs"][0]["condition_a"]["beta1_summary"]["mean_beta1"]
        beta2_0 = res2["processed_pairs"][0]["condition_a"]["beta1_summary"]["mean_beta1"]
        assert np.isclose(beta1_0, beta2_0, atol=1e-12)

    def test_bounded_streaming(self, tmp_path: Path, make_mock_npy):
        """Streams only bounded windows without loading full array into memory."""
        big_file = make_mock_npy(tmp_path, "large_recording.npy", samples=50000, channels=4)
        
        # Test stream_file_chunks with max_windows=3 and chunk_samples=250
        chunks, sfreq, coords = stream_file_chunks(big_file, chunk_samples=250, max_windows=3)
        chunk_list = list(chunks)
        assert len(chunk_list) == 3
        for c in chunk_list:
            assert c.shape == (4, 250)

    def test_finite_json_null_safe(self, tmp_path: Path, make_paired_manifest):
        """Ensures all output values are strictly JSON-compliant without NaNs."""
        manifest_file = make_paired_manifest(n_pairs=2)
        out_dir = tmp_path / "out_null_safe"
        res = execute_cohort_topology(manifest_file, out_dir)

        json_file = out_dir / "cohort_topology_execution_summary.json"
        raw_text = json_file.read_text(encoding="utf-8")
        
        # Strict parsing with allow_nan=False verification
        parsed = json.loads(raw_text)
        assert "NaN" not in raw_text
        assert "Infinity" not in raw_text
        assert parsed["schema"] == "NeuroTopologySim.CohortTopologyExecutionSummary.v1"

    def test_synthetic_labeling_never_emits_pass(self, tmp_path: Path, make_paired_manifest):
        """Synthetic data must NEVER emit PASS or EMPIRICAL_PASS."""
        manifest_file = make_paired_manifest(n_pairs=3, is_synthetic=True)
        out_dir = tmp_path / "out_synthetic"

        res = execute_cohort_topology(manifest_file, out_dir)

        # Status must explicitly identify synthetic evaluation
        assert res["execution_status"] == "SYNTHETIC_EVALUATION"
        assert res["execution_status"] != "PASS"
        assert res["synthetic_pairs_count"] == 3
        assert res["empirical_pairs_count"] == 0

    def test_topology_metric_separation(self, tmp_path: Path, make_paired_manifest):
        """Graph beta-1 and spatial phase charge must reside in distinct structures."""
        manifest_file = make_paired_manifest(n_pairs=2)
        out_dir = tmp_path / "out_separation"

        res = execute_cohort_topology(manifest_file, out_dir)
        pair = res["processed_pairs"][0]
        cond_a = pair["condition_a"]

        # Ensure beta-1 and spatial charge are completely separate dict keys
        assert "beta1_summary" in cond_a
        assert "spatial_charge_summary" in cond_a
        assert "landscape_area_summary" in cond_a

        # Spatial charge availability is explicitly recorded
        assert isinstance(cond_a["spatial_charge_summary"]["available"], bool)
        assert "mean_filtration_beta1_max" in cond_a["beta1_summary"]

    def test_cli_execution(self, tmp_path: Path, make_paired_manifest):
        """Tests CLI entrypoint and exit code handling."""
        manifest_file = make_paired_manifest(n_pairs=2)
        out_dir = tmp_path / "out_cli"

        exit_code = main([
            "--manifest", str(manifest_file),
            "--output-dir", str(out_dir),
            "--chunk-samples", "500",
            "--max-windows", "2",
        ])
        assert exit_code == 0
        assert (out_dir / "cohort_topology_execution_summary.json").is_file()
