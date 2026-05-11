"""Tests for DS005620 EEG reader adapter contracts.

All tests use tmp_path only. No real EEG data.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from sciencer_d.btc_icft.io import (
    EEGReaderCapability,
    EEGFileReadability,
    EEGChannelInventory,
    inspect_eeg_file,
    inspect_eeg_files,
    build_reader_capability_report,
    build_channel_inventory,
    write_eeg_reader_outputs,
)
from sciencer_d.btc_icft.pipelines.inspect_eeg_readers import run as run_inspection


class TestEEGReaderCapability:
    """Tests for EEGReaderCapability dataclass."""

    def test_reader_capability_creation(self):
        """Create a reader capability descriptor."""
        cap = EEGReaderCapability(
            adapter_name="test_adapter",
            supported_extensions=[".csv"],
            dependency_required=None,
            dependency_available=True,
            status="available",
        )
        assert cap.adapter_name == "test_adapter"
        assert ".csv" in cap.supported_extensions


class TestEEGFileReadability:
    """Tests for EEGFileReadability dataclass."""

    def test_file_readability_creation(self):
        """Create a file readability result."""
        result = EEGFileReadability(
            path="/tmp/test.csv",
            extension=".csv",
            exists=False,
            readable=False,
            status="not_found",
        )
        assert result.path == "/tmp/test.csv"
        assert not result.exists
        assert not result.readable


class TestInspectEEGFile:
    """Tests for inspect_eeg_file()."""

    def test_missing_file_returns_not_found(self, tmp_path):
        """Missing file returns exists=false/readable=false."""
        missing = str(tmp_path / "missing.edf")
        result = inspect_eeg_file(missing)
        assert not result.exists
        assert not result.readable
        assert result.status == "not_found"
        assert result.errors

    def test_text_fixture_file_readable(self, tmp_path):
        """Text fixture file is readable by stdlib adapter."""
        csv_file = tmp_path / "data.csv"
        csv_file.write_text("# channels: 4\n# sample_rate: 128.0\nch1,ch2,ch3,ch4\n0.1,0.2,0.3,0.4\n")

        result = inspect_eeg_file(str(csv_file))
        assert result.exists
        assert result.readable
        assert result.adapter == "fixture_text"
        assert result.n_channels == 4
        assert result.sample_rate_hz == 128.0

    def test_unsupported_edf_without_mne(self, tmp_path):
        """Unsupported .edf without optional reader gives readable=false."""
        edf_file = tmp_path / "data.edf"
        edf_file.write_text("fake edf content")

        result = inspect_eeg_file(str(edf_file))
        assert result.exists
        assert not result.readable
        assert result.status == "unsupported_or_dependency_missing"

    def test_unknown_extension(self, tmp_path):
        """Unknown extension returns unknown_extension status."""
        unknown_file = tmp_path / "data.unknown"
        unknown_file.write_text("content")

        result = inspect_eeg_file(str(unknown_file))
        assert result.status == "unknown_extension"
        assert result.errors


class TestBuildReaderCapabilityReport:
    """Tests for build_reader_capability_report()."""

    def test_capability_report_includes_fixture_text(self):
        """Capability report includes fixture_text adapter."""
        report = build_reader_capability_report()
        assert "reader_adapters" in report
        assert "fixture_text" in report["reader_adapters"]

    def test_capability_report_includes_optional_mne(self):
        """Capability report includes optional_mne adapter."""
        report = build_reader_capability_report()
        assert "optional_mne" in report["reader_adapters"]
        mne_cap = report["reader_adapters"]["optional_mne"]
        assert mne_cap["dependency_required"] == "mne"

    def test_capability_report_has_summary(self):
        """Capability report includes summary statistics."""
        report = build_reader_capability_report()
        assert "summary" in report
        assert report["summary"]["total_adapters"] >= 1


class TestBuildChannelInventory:
    """Tests for build_channel_inventory()."""

    def test_inventory_counts_files(self):
        """Channel inventory counts total and readable files."""
        rows = [
            EEGFileReadability(path="a.csv", extension=".csv", exists=True, readable=True, adapter="fixture_text"),
            EEGFileReadability(path="b.csv", extension=".csv", exists=True, readable=False, adapter=None),
        ]
        inventory = build_channel_inventory(rows)
        assert inventory.n_files == 2
        assert inventory.n_readable_files == 1

    def test_inventory_counts_adapters(self):
        """Channel inventory counts adapters used."""
        rows = [
            EEGFileReadability(path="a.csv", extension=".csv", exists=True, readable=True, adapter="fixture_text"),
            EEGFileReadability(path="b.csv", extension=".csv", exists=True, readable=True, adapter="fixture_text"),
            EEGFileReadability(path="c.edf", extension=".edf", exists=True, readable=False, adapter=None),
        ]
        inventory = build_channel_inventory(rows)
        assert inventory.adapters_used.get("fixture_text") == 2

    def test_inventory_counts_extensions(self):
        """Channel inventory counts extension types."""
        rows = [
            EEGFileReadability(path="a.csv", extension=".csv", exists=True, readable=True, adapter="fixture_text"),
            EEGFileReadability(path="b.txt", extension=".txt", exists=True, readable=True, adapter="fixture_text"),
        ]
        inventory = build_channel_inventory(rows)
        assert ".csv" in inventory.extensions_seen
        assert ".txt" in inventory.extensions_seen


class TestWriteEEGReaderOutputs:
    """Tests for write_eeg_reader_outputs()."""

    def test_write_outputs_creates_json_files(self, tmp_path):
        """write_eeg_reader_outputs creates JSON files."""
        rows = [
            EEGFileReadability(path="a.csv", extension=".csv", exists=True, readable=True, adapter="fixture_text"),
        ]
        outputs = write_eeg_reader_outputs(rows, str(tmp_path))

        assert "reader_capability_report" in outputs
        assert "file_readability_report" in outputs
        assert "channel_inventory" in outputs

        cap_file = Path(outputs["reader_capability_report"])
        assert cap_file.exists()
        data = json.loads(cap_file.read_text())
        assert "reader_adapters" in data

    def test_write_outputs_creates_markdown_report(self, tmp_path):
        """write_eeg_reader_outputs creates markdown report."""
        rows = [
            EEGFileReadability(path="a.csv", extension=".csv", exists=True, readable=True, adapter="fixture_text"),
        ]
        outputs = write_eeg_reader_outputs(rows, str(tmp_path))

        md_file = Path(outputs["report"])
        assert md_file.exists()
        md_content = md_file.read_text()
        assert "DS005620 EEG Reader Adapter Inspection" in md_content

    def test_report_avoids_banned_phrases(self, tmp_path):
        """Markdown report avoids banned phrases."""
        rows = [
            EEGFileReadability(path="a.csv", extension=".csv", exists=True, readable=True, adapter="fixture_text"),
        ]
        outputs = write_eeg_reader_outputs(rows, str(tmp_path))

        md_file = Path(outputs["report"])
        md_content = md_file.read_text().lower()

        banned = [
            "proves consciousness",
            "consciousness proven",
            "soul proven",
            "afterlife proven",
            "liberation detected",
            "ontology solved",
            "ultimate reality",
        ]
        for phrase in banned:
            assert phrase not in md_content, f"Banned phrase found: {phrase}"

    def test_json_output_parses(self, tmp_path):
        """Output JSON files are valid JSON."""
        rows = [
            EEGFileReadability(path="a.csv", extension=".csv", exists=True, readable=True, adapter="fixture_text"),
        ]
        outputs = write_eeg_reader_outputs(rows, str(tmp_path))

        for name, path in outputs.items():
            if name != "report":
                file_path = Path(path)
                assert file_path.exists()
                data = json.loads(file_path.read_text())
                assert data is not None


class TestInspectionCLI:
    """Tests for CLI entry point."""

    def test_cli_mock_fixture_smoke(self, tmp_path):
        """CLI with --mock-fixture runs and writes outputs."""
        out_dir = str(tmp_path / "output")
        result = run_inspection(mock_fixture=True, out_dir=out_dir)

        assert result == 0
        assert Path(out_dir).exists()

        expected_files = [
            "reader_capability_report.json",
            "file_readability_report.json",
            "channel_inventory.json",
            "report.md",
        ]
        for fname in expected_files:
            file_path = Path(out_dir) / fname
            assert file_path.exists(), f"Missing {fname}"

    def test_cli_with_paths(self, tmp_path):
        """CLI with --paths inspects specified files."""
        csv_file = tmp_path / "test.csv"
        csv_file.write_text("# channels: 2\n# sample_rate: 100.0\n0.1,0.2\n")

        out_dir = str(tmp_path / "output")
        result = run_inspection(paths=[str(csv_file)], out_dir=out_dir)

        assert result == 0
        assert (Path(out_dir) / "file_readability_report.json").exists()

    def test_cli_missing_args_fails(self, tmp_path):
        """CLI without --paths or --mock-fixture fails."""
        out_dir = str(tmp_path / "output")
        result = run_inspection(out_dir=out_dir)
        assert result != 0


class TestConfigFile:
    """Tests for config file."""

    def test_config_file_exists(self):
        """Configuration file exists at expected path."""
        config_path = Path(__file__).parent.parent.parent / "configs" / "btc_icft" / "eeg_readers.yaml"
        assert config_path.exists(), f"Config not found at {config_path}"

    def test_config_has_required_fields(self):
        """Configuration includes required fields."""
        import yaml

        config_path = Path(__file__).parent.parent.parent / "configs" / "btc_icft" / "eeg_readers.yaml"
        with open(config_path) as f:
            config = yaml.safe_load(f)

        assert config.get("dataset_id") == "ds005620"
        assert "required_outputs" in config
        assert "guardrails" in config
        assert len(config["guardrails"]) > 0
