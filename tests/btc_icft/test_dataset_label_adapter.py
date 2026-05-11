"""Tests for P14 — Dataset label adapter readiness (stdlib-only, no fixtures required).

All tests use tmp_path only. No real dataset files required.
"""
from __future__ import annotations

import csv
import json
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

import pytest

from sciencer_d.btc_icft.labels.dataset_label_adapter import (
    DatasetLabelAdapterSpec,
    LabelAdapterProbeResult,
    DatasetAdapterReadiness,
    LabelAdapterReadinessSummary,
    assess_all_datasets,
    assess_dataset_adapter_readiness,
    get_label_adapter_specs,
    probe_metadata_file,
    write_adapter_readiness_outputs,
    _SAFE_CLAIM,
    _BANNED_PHRASES,
)

DATASET_IDS = ["DS005620", "DS002094", "ds001787", "ds003969", "ds003816", "PhysioNet_GABA"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_events_csv(path: Path, trial_types: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    cols = ["dataset_id", "row_id", "window_id", "trial_type"]
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for i, tt in enumerate(trial_types):
            w.writerow({"dataset_id": "DS005620", "row_id": f"r{i}",
                        "window_id": f"w{i}", "trial_type": tt})


def _write_events_tsv(path: Path, trial_types: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        fh.write("onset\tduration\ttrial_type\n")
        for i, tt in enumerate(trial_types):
            fh.write(f"{i}.0\t1.0\t{tt}\n")


# ---------------------------------------------------------------------------
# get_label_adapter_specs
# ---------------------------------------------------------------------------

class TestGetLabelAdapterSpecs:
    def test_returns_all_six_datasets(self):
        specs = get_label_adapter_specs()
        assert set(specs.keys()) == set(DATASET_IDS)

    def test_each_spec_is_dataclass(self):
        specs = get_label_adapter_specs()
        for ds_id, spec in specs.items():
            assert isinstance(spec, DatasetLabelAdapterSpec), ds_id

    def test_each_spec_has_candidate_filenames(self):
        for spec in get_label_adapter_specs().values():
            assert len(spec.candidate_metadata_filenames) > 0

    def test_each_spec_has_known_label_columns(self):
        for spec in get_label_adapter_specs().values():
            assert len(spec.known_label_columns) > 0

    def test_no_banned_phrases_in_spec_titles(self):
        specs = get_label_adapter_specs()
        for phrase in _BANNED_PHRASES:
            for spec in specs.values():
                assert phrase not in spec.title.lower()

    def test_no_banned_phrases_in_spec_caveats(self):
        for phrase in _BANNED_PHRASES:
            for spec in get_label_adapter_specs().values():
                for caveat in spec.adapter_caveats:
                    assert phrase not in caveat.lower()

    def test_all_planning_statuses_are_safe_strings(self):
        for spec in get_label_adapter_specs().values():
            assert isinstance(spec.planning_status, str)
            assert len(spec.planning_status) > 0
            for phrase in _BANNED_PHRASES:
                assert phrase not in spec.planning_status.lower()

    def test_physionet_gaba_label_scope_is_subject(self):
        specs = get_label_adapter_specs()
        assert specs["PhysioNet_GABA"].label_scope == "subject"

    def test_openneuro_datasets_label_scope_is_window(self):
        specs = get_label_adapter_specs()
        for ds_id in ["DS005620", "DS002094", "ds001787", "ds003969", "ds003816"]:
            assert specs[ds_id].label_scope == "window"


# ---------------------------------------------------------------------------
# probe_metadata_file
# ---------------------------------------------------------------------------

class TestProbeMetadataFile:
    def test_returns_not_found_when_file_missing(self, tmp_path):
        spec = get_label_adapter_specs()["DS005620"]
        result = probe_metadata_file("DS005620", tmp_path / "nonexistent.csv", spec)
        assert result.metadata_found is False
        assert result.readiness_status == "metadata_file_not_found"

    def test_reads_csv_metadata_file(self, tmp_path):
        spec = get_label_adapter_specs()["DS005620"]
        f = tmp_path / "events.csv"
        _write_events_csv(f, ["cond_a", "cond_b"])
        result = probe_metadata_file("DS005620", f, spec)
        assert result.metadata_found is True
        assert result.parse_ok is True
        assert result.n_rows == 2

    def test_reads_tsv_metadata_file(self, tmp_path):
        spec = get_label_adapter_specs()["DS005620"]
        f = tmp_path / "events.tsv"
        _write_events_tsv(f, ["med", "rest"])
        result = probe_metadata_file("DS005620", f, spec)
        assert result.metadata_found is True
        assert result.parse_ok is True
        assert result.n_rows == 2

    def test_detects_candidate_label_column(self, tmp_path):
        spec = get_label_adapter_specs()["DS005620"]
        f = tmp_path / "events.csv"
        _write_events_csv(f, ["cond_a", "cond_b"])
        result = probe_metadata_file("DS005620", f, spec)
        assert len(result.candidate_label_columns) > 0
        assert "trial_type" in result.candidate_label_columns

    def test_reports_unique_values(self, tmp_path):
        spec = get_label_adapter_specs()["DS005620"]
        f = tmp_path / "events.csv"
        _write_events_csv(f, ["cond_a", "cond_b", "cond_a"])
        result = probe_metadata_file("DS005620", f, spec)
        assert "trial_type" in result.unique_values
        assert set(result.unique_values["trial_type"]) == {"cond_a", "cond_b"}

    def test_insufficient_label_values_when_one_distinct(self, tmp_path):
        spec = get_label_adapter_specs()["DS005620"]
        f = tmp_path / "events.csv"
        _write_events_csv(f, ["cond_a", "cond_a", "cond_a"])
        result = probe_metadata_file("DS005620", f, spec)
        assert result.readiness_status == "insufficient_label_values"
        assert result.has_sufficient_label_values is False

    def test_needs_explicit_mapping_when_two_distinct(self, tmp_path):
        spec = get_label_adapter_specs()["DS005620"]
        f = tmp_path / "events.csv"
        _write_events_csv(f, ["cond_a", "cond_b"])
        result = probe_metadata_file("DS005620", f, spec)
        assert result.readiness_status == "needs_explicit_mapping"
        assert result.has_sufficient_label_values is True

    def test_ready_to_activate_when_known_values_present(self, tmp_path):
        spec = get_label_adapter_specs()["DS005620"]
        spec_with_known = DatasetLabelAdapterSpec(
            **{**asdict(spec),
               "known_positive_values": ["cond_a"],
               "known_negative_values": ["cond_b"]}
        )
        f = tmp_path / "events.csv"
        _write_events_csv(f, ["cond_a", "cond_b"])
        result = probe_metadata_file("DS005620", f, spec_with_known)
        assert result.readiness_status == "ready_to_activate"

    def test_no_candidate_label_column_when_unrecognized_columns(self, tmp_path):
        spec = get_label_adapter_specs()["DS005620"]
        f = tmp_path / "metadata.csv"
        f.write_text("onset,duration,x_coord\n0.0,1.0,42\n1.0,1.0,99\n", encoding="utf-8")
        result = probe_metadata_file("DS005620", f, spec)
        assert result.readiness_status == "no_candidate_label_column"


# ---------------------------------------------------------------------------
# assess_dataset_adapter_readiness
# ---------------------------------------------------------------------------

class TestAssessDatasetAdapterReadiness:
    def test_returns_dataclass_instance(self, tmp_path):
        result = assess_dataset_adapter_readiness("DS005620", str(tmp_path))
        assert isinstance(result, DatasetAdapterReadiness)

    def test_metadata_file_not_found_when_no_files(self, tmp_path):
        result = assess_dataset_adapter_readiness("DS005620", str(tmp_path))
        assert result.readiness_status == "metadata_file_not_found"
        assert result.can_activate_contract is False

    def test_needs_explicit_mapping_with_mock_metadata(self, tmp_path):
        ds_root = tmp_path / "DS005620"
        f = ds_root / "events.csv"
        _write_events_csv(f, ["cond_a", "cond_b"])
        result = assess_dataset_adapter_readiness("DS005620", str(ds_root))
        assert result.readiness_status == "needs_explicit_mapping"
        assert result.can_activate_contract is False
        assert result.suggested_label_column is not None

    def test_raises_on_unknown_dataset_id(self, tmp_path):
        with pytest.raises(ValueError, match="Unknown dataset_id"):
            assess_dataset_adapter_readiness("UNKNOWN_DS", str(tmp_path))

    def test_activation_blockers_present_when_not_ready(self, tmp_path):
        result = assess_dataset_adapter_readiness("DS005620", str(tmp_path))
        assert len(result.activation_blockers) > 0

    def test_best_probe_is_none_when_no_files(self, tmp_path):
        result = assess_dataset_adapter_readiness("DS005620", str(tmp_path))
        assert result.best_probe is None

    def test_best_probe_populated_when_file_found(self, tmp_path):
        ds_root = tmp_path / "DS005620"
        _write_events_csv(ds_root / "events.csv", ["x", "y"])
        result = assess_dataset_adapter_readiness("DS005620", str(ds_root))
        assert result.best_probe is not None

    def test_suggested_values_populated_when_mapping_needed(self, tmp_path):
        ds_root = tmp_path / "DS005620"
        _write_events_csv(ds_root / "events.csv", ["alpha", "beta"])
        result = assess_dataset_adapter_readiness("DS005620", str(ds_root))
        assert result.suggested_positive_values or result.suggested_negative_values


# ---------------------------------------------------------------------------
# assess_all_datasets
# ---------------------------------------------------------------------------

class TestAssessAllDatasets:
    def test_returns_summary_instance(self, tmp_path):
        summary = assess_all_datasets(str(tmp_path))
        assert isinstance(summary, LabelAdapterReadinessSummary)

    def test_n_datasets_is_six(self, tmp_path):
        summary = assess_all_datasets(str(tmp_path))
        assert summary.n_datasets == 6

    def test_per_dataset_has_all_six_keys(self, tmp_path):
        summary = assess_all_datasets(str(tmp_path))
        assert set(summary.per_dataset.keys()) == set(DATASET_IDS)

    def test_all_missing_when_no_files(self, tmp_path):
        summary = assess_all_datasets(str(tmp_path))
        assert summary.n_missing_metadata == 6

    def test_safe_claim_is_present(self, tmp_path):
        summary = assess_all_datasets(str(tmp_path))
        assert summary.safe_claim == _SAFE_CLAIM

    def test_no_banned_phrases_in_safe_claim(self):
        for phrase in _BANNED_PHRASES:
            assert phrase not in _SAFE_CLAIM.lower()


# ---------------------------------------------------------------------------
# write_adapter_readiness_outputs
# ---------------------------------------------------------------------------

class TestWriteAdapterReadinessOutputs:
    def _make_summary(self, tmp_path: Path) -> LabelAdapterReadinessSummary:
        return assess_all_datasets(str(tmp_path))

    def test_creates_adapter_readiness_summary_json(self, tmp_path):
        summary = self._make_summary(tmp_path / "data")
        outputs = write_adapter_readiness_outputs(summary, str(tmp_path / "out"))
        p = Path(tmp_path / "out" / "adapter_readiness_summary.json")
        assert p.is_file()
        data = json.loads(p.read_text())
        assert "n_datasets" in data

    def test_creates_omega_event_json_with_safe_claim(self, tmp_path):
        summary = self._make_summary(tmp_path / "data")
        write_adapter_readiness_outputs(summary, str(tmp_path / "out"))
        p = tmp_path / "out" / "omega_event.json"
        assert p.is_file()
        data = json.loads(p.read_text())
        assert "safe_claim" in data

    def test_creates_report_md(self, tmp_path):
        summary = self._make_summary(tmp_path / "data")
        write_adapter_readiness_outputs(summary, str(tmp_path / "out"))
        p = tmp_path / "out" / "report.md"
        assert p.is_file()

    def test_report_md_has_no_banned_phrases(self, tmp_path):
        summary = self._make_summary(tmp_path / "data")
        write_adapter_readiness_outputs(summary, str(tmp_path / "out"))
        text = (tmp_path / "out" / "report.md").read_text().lower()
        for phrase in _BANNED_PHRASES:
            assert phrase not in text

    def test_report_md_mentions_all_six_datasets(self, tmp_path):
        summary = self._make_summary(tmp_path / "data")
        write_adapter_readiness_outputs(summary, str(tmp_path / "out"))
        text = (tmp_path / "out" / "report.md").read_text()
        for ds_id in DATASET_IDS:
            assert ds_id in text

    def test_creates_per_dataset_plan_jsons(self, tmp_path):
        summary = self._make_summary(tmp_path / "data")
        outputs = write_adapter_readiness_outputs(summary, str(tmp_path / "out"))
        for ds_id in DATASET_IDS:
            key = f"adapter_plan_{ds_id}"
            assert key in outputs
            assert Path(outputs[key]).is_file()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

class TestCli:
    def test_list_datasets_shows_all_ids(self):
        cp = subprocess.run(
            [sys.executable, "-m",
             "sciencer_d.btc_icft.pipelines.plan_dataset_label_adapters",
             "--list-datasets"],
            capture_output=True, text=True,
        )
        assert cp.returncode == 0
        for ds_id in DATASET_IDS:
            assert ds_id in cp.stdout

    def test_mock_fixture_runs_successfully(self, tmp_path):
        cp = subprocess.run(
            [sys.executable, "-m",
             "sciencer_d.btc_icft.pipelines.plan_dataset_label_adapters",
             "--mock-fixture",
             "--out", str(tmp_path / "out")],
            capture_output=True, text=True,
        )
        assert cp.returncode == 0

    def test_mock_fixture_writes_summary(self, tmp_path):
        cp = subprocess.run(
            [sys.executable, "-m",
             "sciencer_d.btc_icft.pipelines.plan_dataset_label_adapters",
             "--mock-fixture",
             "--out", str(tmp_path / "out")],
            capture_output=True, text=True,
        )
        assert cp.returncode == 0
        p = tmp_path / "out" / "adapter_readiness_summary.json"
        assert p.is_file()
        data = json.loads(p.read_text())
        assert data["n_datasets"] >= 1

    def test_omega_event_has_safe_claim_key(self, tmp_path):
        subprocess.run(
            [sys.executable, "-m",
             "sciencer_d.btc_icft.pipelines.plan_dataset_label_adapters",
             "--mock-fixture",
             "--out", str(tmp_path / "out")],
            capture_output=True, text=True,
        )
        p = tmp_path / "out" / "omega_event.json"
        assert p.is_file()
        data = json.loads(p.read_text())
        assert "safe_claim" in data


# ---------------------------------------------------------------------------
# Guardrail integrity
# ---------------------------------------------------------------------------

class TestGuardrailIntegrity:
    def test_no_p12_label_contracts_imported_in_adapter_module(self):
        src = Path("sciencer_d/btc_icft/labels/dataset_label_adapter.py").read_text()
        assert "eeg_label_contracts" not in src
        assert "eeg_target_injection" not in src

    def test_no_p13_files_imported_in_pipeline(self):
        src = Path(
            "sciencer_d/btc_icft/pipelines/plan_dataset_label_adapters.py"
        ).read_text()
        assert "eeg_target_injection" not in src
        assert "inject_eeg_targets" not in src

    def test_config_lists_all_six_known_datasets(self):
        cfg = Path("configs/btc_icft/dataset_label_adapters.yaml").read_text()
        for ds_id in DATASET_IDS:
            assert ds_id in cfg

    def test_config_has_no_banned_phrases(self):
        cfg = Path("configs/btc_icft/dataset_label_adapters.yaml").read_text().lower()
        for phrase in _BANNED_PHRASES:
            assert phrase not in cfg
