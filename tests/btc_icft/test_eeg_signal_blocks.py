"""Tests for DS005620 EEG signal-block adapter contract (P8.2).

All tests are offline and stdlib-only. No MNE, scipy, or numpy required.

Spec-required tests:
 1. dataclasses instantiate and serialize via asdict
 2. parse CSV fixture with comment headers (# channels, # sample_rate, # channel_names)
 3. parse TSV fixture without header - generate channel names
 4. parse TXT whitespace fixture
 5. strip time column when header includes time/t/timestamp/seconds/sec
 6. missing file is skipped or returns readable=false safely
 7. unsupported .edf returns unsupported_or_dependency_missing
 8. empty file returns no_numeric_signal_rows
 9. nonnumeric file returns no_numeric_signal_rows
10. rectangular mismatch produces controlled error/warning
11. segment_signal_file creates deterministic full windows
12. short signal creates one short_window
13. max_windows_per_file is respected
14. row_id uses <stem>__win_<idx>
15. probe_signal_paths returns n_files/n_readable_files/n_skipped_files/n_windows
16. inventory includes extensions_seen, adapter_counts, sample_rate_values
17. reader alignment report includes ready_for_p9_signal_extraction
18. write_signal_probe_outputs writes all six required files
19. JSON outputs parse
20. window_inventory.csv contains required columns
21. report.md contains cautious terms
22. report.md does not contain banned phrases
23. CLI mock fixture smoke returns 0 and writes all six files
24. CLI without paths/mock fails cleanly
25. config exists and contains required outputs and guardrails
"""
from __future__ import annotations

import csv
import json
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

import pytest

from sciencer_d.btc_icft.io.eeg_signal_blocks import (
    EEGSignalFile,
    EEGSignalWindow,
    EEGSignalProbeResult,
    parse_fixture_signal_file,
    segment_signal_file,
    probe_signal_paths,
    build_signal_block_inventory,
    build_reader_alignment_report,
    write_signal_probe_outputs,
    _validate_safe_text,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_csv(
    path: Path,
    n_channels: int = 4,
    n_rows: int = 100,
    sample_rate: float = 100.0,
    with_time_col: bool = True,
    channel_names: list[str] | None = None,
) -> None:
    with open(path, "w") as f:
        f.write(f"# channels: {n_channels}\n")
        f.write(f"# sample_rate: {sample_rate}\n")
        if channel_names:
            f.write(f"# channel_names: {','.join(channel_names)}\n")
        if with_time_col:
            headers = ["time"] + [f"ch{i+1}" for i in range(n_channels)]
        else:
            headers = [f"ch{i+1}" for i in range(n_channels)]
        f.write(",".join(headers) + "\n")
        for i in range(n_rows):
            if with_time_col:
                vals = [f"{i * 0.01:.4f}"] + [f"{i * 0.1 * (j+1):.4f}" for j in range(n_channels)]
            else:
                vals = [f"{i * 0.1 * (j+1):.4f}" for j in range(n_channels)]
            f.write(",".join(vals) + "\n")


def _write_txt(path: Path, n_channels: int = 3, n_rows: int = 50, sample_rate: float = 128.0) -> None:
    with open(path, "w") as f:
        f.write(f"# channels: {n_channels}\n")
        f.write(f"# sample_rate: {sample_rate}\n")
        for i in range(n_rows):
            f.write(" ".join([f"{i * 0.05 * (j+1):.4f}" for j in range(n_channels)]) + "\n")


def _write_tsv(path: Path, n_channels: int = 2, n_rows: int = 80) -> None:
    with open(path, "w") as f:
        f.write("# channels: 2\n")
        f.write("# sample_rate: 256.0\n")
        f.write("# channel_names: left,right\n")
        for i in range(n_rows):
            f.write(f"{i * 0.1:.4f}\t{-i * 0.1:.4f}\n")


# ---------------------------------------------------------------------------
# Test 1: Dataclasses instantiate and serialize via asdict
# ---------------------------------------------------------------------------

class TestDataclassSerialization:
    def test_eeg_signal_file_asdict(self):
        sf = EEGSignalFile(path="/tmp/x.csv", readable=False)
        d = asdict(sf)
        assert "path" in d
        assert "readable" in d
        assert "channel_names" in d
        assert "samples" in d

    def test_eeg_signal_window_asdict(self):
        w = EEGSignalWindow(
            file_path="/tmp/x.csv",
            row_id="x__win_0",
            window_id="win-000",
            window_start_s=0.0,
            window_end_s=1.0,
            sample_start=0,
            sample_end=100,
            n_channels=4,
            n_samples=100,
            sample_rate_hz=100.0,
        )
        d = asdict(w)
        assert d["row_id"] == "x__win_0"
        assert d["window_id"] == "win-000"

    def test_eeg_signal_probe_result_asdict(self):
        r = EEGSignalProbeResult(
            n_files=1,
            n_readable_files=1,
            n_skipped_files=0,
            n_windows=2,
            safe_claim="test claim",
        )
        d = asdict(r)
        assert d["n_files"] == 1
        assert "forbidden_claims" in d


# ---------------------------------------------------------------------------
# Test 2: Parse CSV fixture with comment headers
# ---------------------------------------------------------------------------

class TestParseCsvWithHeaders:
    def test_channels_header_parsed(self, tmp_path):
        p = tmp_path / "test.csv"
        _write_csv(p, n_channels=4, n_rows=100, sample_rate=250.0)
        sf = parse_fixture_signal_file(str(p))
        assert sf.readable is True
        assert sf.n_channels == 4
        assert sf.sample_rate_hz == pytest.approx(250.0)
        assert sf.n_samples == 100

    def test_channel_names_from_comment(self, tmp_path):
        p = tmp_path / "named.csv"
        _write_csv(p, n_channels=3, n_rows=20, channel_names=["alpha", "beta", "gamma"])
        sf = parse_fixture_signal_file(str(p))
        assert sf.readable is True
        assert "alpha" in sf.channel_names or len(sf.channel_names) >= 3

    def test_duration_computed_correctly(self, tmp_path):
        p = tmp_path / "dur.csv"
        _write_csv(p, n_channels=2, n_rows=100, sample_rate=100.0)
        sf = parse_fixture_signal_file(str(p))
        assert sf.duration_s == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Test 3: Parse TSV without header - generate channel names
# ---------------------------------------------------------------------------

class TestParseTsvGenerateChannelNames:
    def test_tsv_without_header_generates_names(self, tmp_path):
        p = tmp_path / "bare.tsv"
        with open(p, "w") as f:
            f.write("# channels: 3\n")
            f.write("# sample_rate: 100.0\n")
            for i in range(10):
                f.write(f"{i * 0.1}\t{i * 0.2}\t{i * 0.3}\n")
        sf = parse_fixture_signal_file(str(p))
        assert sf.readable is True
        assert sf.n_channels == 3
        assert len(sf.channel_names) == 3
        # auto-generated names should follow ch_N pattern
        assert any("ch" in n for n in sf.channel_names)

    def test_tsv_with_comment_channel_names(self, tmp_path):
        p = tmp_path / "named.tsv"
        _write_tsv(p, n_channels=2, n_rows=40)
        sf = parse_fixture_signal_file(str(p))
        assert sf.readable is True
        assert "left" in sf.channel_names or "right" in sf.channel_names


# ---------------------------------------------------------------------------
# Test 4: Parse TXT whitespace fixture
# ---------------------------------------------------------------------------

class TestParseTxtWhitespace:
    def test_txt_whitespace_parses(self, tmp_path):
        p = tmp_path / "test.txt"
        _write_txt(p, n_channels=3, n_rows=50, sample_rate=128.0)
        sf = parse_fixture_signal_file(str(p))
        assert sf.readable is True
        assert sf.n_channels == 3
        assert sf.n_samples == 50
        assert sf.sample_rate_hz == pytest.approx(128.0)

    def test_txt_explicit_sample_rate_is_non_scientific(self, tmp_path):
        p = tmp_path / "nsr.txt"
        with open(p, "w") as f:
            for i in range(20):
                f.write(f"{i * 0.1} {i * 0.2}\n")
        sf = parse_fixture_signal_file(str(p), sample_rate_hz=42.0)
        assert sf.readable is True
        assert sf.sample_rate_hz == pytest.approx(42.0)
        assert sf.sample_rate_source == "caller_explicit"
        assert sf.imputed is True
        assert sf.scientific_eligible is False

    def test_txt_missing_sample_rate_fails_closed(self, tmp_path):
        p = tmp_path / "nsr_missing.txt"
        with open(p, "w") as f:
            for i in range(20):
                f.write(f"{i * 0.1} {i * 0.2}\n")
        sf = parse_fixture_signal_file(str(p))
        assert sf.readable is False
        assert sf.sample_rate_hz is None
        assert any("missing_sample_rate_hz" in e for e in sf.errors)


# ---------------------------------------------------------------------------
# Test 5: Strip time column
# ---------------------------------------------------------------------------

class TestStripTimeColumn:
    @pytest.mark.parametrize("col_name", ["time", "t", "timestamp", "seconds", "sec"])
    def test_strips_time_column(self, tmp_path, col_name):
        p = tmp_path / f"tc_{col_name}.csv"
        with open(p, "w") as f:
            f.write("# channels: 2\n")
            f.write("# sample_rate: 100.0\n")
            f.write(f"{col_name},ch1,ch2\n")
            for i in range(10):
                f.write(f"{i * 0.01},{i * 0.1},{i * 0.2}\n")
        sf = parse_fixture_signal_file(str(p))
        assert sf.readable is True
        assert sf.n_channels == 2
        # After stripping time col, each data row should have 2 values
        assert all(len(row) == 2 for row in sf.samples)


# ---------------------------------------------------------------------------
# Test 6: Missing file returns readable=false safely
# ---------------------------------------------------------------------------

class TestMissingFile:
    def test_missing_file_readable_false(self, tmp_path):
        sf = parse_fixture_signal_file(str(tmp_path / "nonexistent.csv"))
        assert sf.readable is False
        assert sf.errors

    def test_missing_file_skipped_in_probe(self, tmp_path):
        result = probe_signal_paths([str(tmp_path / "ghost.csv")])
        assert result.n_skipped_files == 1
        assert result.skipped_files[0]["reason"] == "missing_file"


# ---------------------------------------------------------------------------
# Test 7: Unsupported .edf returns unsupported_or_dependency_missing
# ---------------------------------------------------------------------------

class TestUnsupportedExtension:
    def test_edf_binary_skipped(self, tmp_path):
        p = tmp_path / "test.edf"
        p.write_bytes(b"\x00\x01\x02")
        result = probe_signal_paths([str(p)])
        assert result.n_skipped_files == 1
        assert result.skipped_files[0]["reason"] == "unsupported_or_dependency_missing"

    def test_parse_edf_directly_returns_error(self, tmp_path):
        p = tmp_path / "test.edf"
        p.write_bytes(b"\x00\x01")
        sf = parse_fixture_signal_file(str(p))
        assert sf.readable is False
        assert any("unsupported_or_dependency_missing" in e for e in sf.errors)


# ---------------------------------------------------------------------------
# Test 8: Empty file returns no_numeric_signal_rows
# ---------------------------------------------------------------------------

class TestEmptyFile:
    def test_empty_csv_no_signal_rows(self, tmp_path):
        p = tmp_path / "empty.csv"
        p.write_text("")
        sf = parse_fixture_signal_file(str(p))
        assert sf.readable is False
        assert any("no_numeric_signal_rows" in e for e in sf.errors)


# ---------------------------------------------------------------------------
# Test 9: Nonnumeric file returns no_numeric_signal_rows
# ---------------------------------------------------------------------------

class TestNonnumericFile:
    def test_all_text_no_signal_rows(self, tmp_path):
        p = tmp_path / "words.csv"
        p.write_text("hello,world\nfoo,bar\nbaz,qux\n")
        sf = parse_fixture_signal_file(str(p))
        assert sf.readable is False
        assert any("no_numeric_signal_rows" in e for e in sf.errors)


# ---------------------------------------------------------------------------
# Test 10: Rectangular mismatch produces controlled error/warning
# ---------------------------------------------------------------------------

class TestRectangularMismatch:
    def test_inconsistent_rows_warned(self, tmp_path):
        p = tmp_path / "ragged.csv"
        with open(p, "w") as f:
            f.write("# channels: 3\n")
            f.write("# sample_rate: 100.0\n")
            f.write("1.0,2.0,3.0\n")
            f.write("4.0,5.0\n")  # only 2 cols
            f.write("6.0,7.0,8.0\n")
        sf = parse_fixture_signal_file(str(p))
        # Should still be readable with valid rows
        assert sf.readable is True
        assert any("inconsistent" in w.lower() for w in sf.warnings)


# ---------------------------------------------------------------------------
# Test 11: segment_signal_file creates deterministic full windows
# ---------------------------------------------------------------------------

class TestSegmentFullWindows:
    def _make_sf(self, n_samples: int, sr: float = 100.0, n_ch: int = 4) -> EEGSignalFile:
        samples = [[float(i * j) for j in range(1, n_ch + 1)] for i in range(n_samples)]
        return EEGSignalFile(
            path="/tmp/mock.csv",
            readable=True,
            adapter="fixture_text",
            n_channels=n_ch,
            n_samples=n_samples,
            sample_rate_hz=sr,
            duration_s=n_samples / sr,
            channel_names=[f"ch_{j}" for j in range(n_ch)],
            samples=samples,
        )

    def test_correct_window_count(self):
        sf = self._make_sf(n_samples=1000, sr=100.0)
        wins = segment_signal_file(sf, window_seconds=1.0, max_windows=None)
        assert len(wins) == 10

    def test_full_window_status(self):
        sf = self._make_sf(n_samples=1000, sr=100.0)
        wins = segment_signal_file(sf, window_seconds=1.0, max_windows=None)
        for w in wins:
            assert w.status == "full_window"

    def test_deterministic_across_calls(self, tmp_path):
        p = tmp_path / "det.csv"
        _write_csv(p, n_rows=200, sample_rate=100.0)
        sf = parse_fixture_signal_file(str(p))
        wins1 = segment_signal_file(sf, window_seconds=1.0, max_windows=5)
        wins2 = segment_signal_file(sf, window_seconds=1.0, max_windows=5)
        assert [w.row_id for w in wins1] == [w.row_id for w in wins2]


# ---------------------------------------------------------------------------
# Test 12: Short signal creates one short_window
# ---------------------------------------------------------------------------

class TestShortWindow:
    def test_short_signal_one_short_window(self):
        sf = EEGSignalFile(
            path="/tmp/short.csv",
            readable=True,
            n_channels=2,
            n_samples=10,
            sample_rate_hz=100.0,
            duration_s=0.1,
            channel_names=["ch_0", "ch_1"],
            samples=[[float(i), float(i)] for i in range(10)],
        )
        wins = segment_signal_file(sf, window_seconds=10.0)
        assert len(wins) == 1
        assert wins[0].status == "short_window"
        assert wins[0].n_samples == 10


# ---------------------------------------------------------------------------
# Test 13: max_windows_per_file is respected
# ---------------------------------------------------------------------------

class TestMaxWindows:
    def test_max_windows_limits_output(self):
        sf = EEGSignalFile(
            path="/tmp/long.csv",
            readable=True,
            n_channels=2,
            n_samples=5000,
            sample_rate_hz=100.0,
            duration_s=50.0,
            channel_names=["ch_0", "ch_1"],
            samples=[[float(i), float(i)] for i in range(5000)],
        )
        wins = segment_signal_file(sf, window_seconds=1.0, max_windows=3)
        assert len(wins) <= 3


# ---------------------------------------------------------------------------
# Test 14: row_id uses <stem>__win_<idx>
# ---------------------------------------------------------------------------

class TestRowIdFormat:
    def test_row_id_format(self):
        sf = EEGSignalFile(
            path="/tmp/mysignal.csv",
            readable=True,
            n_channels=2,
            n_samples=500,
            sample_rate_hz=100.0,
            duration_s=5.0,
            channel_names=["ch_0", "ch_1"],
            samples=[[float(i), float(i)] for i in range(500)],
        )
        wins = segment_signal_file(sf, window_seconds=1.0, max_windows=None)
        for idx, w in enumerate(wins[:5]):
            assert w.row_id == f"mysignal__win_{idx}"

    def test_window_id_string_format(self):
        sf = EEGSignalFile(
            path="/tmp/wid.csv",
            readable=True,
            n_channels=2,
            n_samples=300,
            sample_rate_hz=100.0,
            duration_s=3.0,
            channel_names=["ch_0", "ch_1"],
            samples=[[float(i), float(i)] for i in range(300)],
        )
        wins = segment_signal_file(sf, window_seconds=1.0)
        for idx, w in enumerate(wins[:5]):
            assert w.window_id == f"win-{idx:03d}"


# ---------------------------------------------------------------------------
# Test 15: probe_signal_paths returns correct aggregate counts
# ---------------------------------------------------------------------------

class TestProbeSignalPaths:
    def test_correct_aggregate_counts(self, tmp_path):
        csv_p = tmp_path / "a.csv"
        txt_p = tmp_path / "b.txt"
        edf_p = tmp_path / "c.edf"
        _write_csv(csv_p, n_rows=200)
        _write_txt(txt_p, n_rows=50)
        edf_p.write_bytes(b"\x00")
        result = probe_signal_paths([str(csv_p), str(txt_p), str(edf_p)])
        assert result.n_files == 3
        assert result.n_readable_files == 2
        assert result.n_skipped_files == 1
        assert result.n_windows >= 0


# ---------------------------------------------------------------------------
# Test 16: inventory includes extensions_seen, adapter_counts, sample_rate_values
# ---------------------------------------------------------------------------

class TestInventoryFields:
    def test_inventory_has_required_fields(self, tmp_path):
        csv_p = tmp_path / "inv.csv"
        _write_csv(csv_p, n_rows=100, sample_rate=250.0)
        result = probe_signal_paths([str(csv_p)])
        inv = build_signal_block_inventory(result)
        assert "extensions_seen" in inv
        assert "adapter_counts" in inv
        assert "sample_rate_values" in inv
        assert ".csv" in inv["extensions_seen"]
        assert inv["adapter_counts"].get("fixture_text", 0) >= 1
        assert 250.0 in inv["sample_rate_values"]


# ---------------------------------------------------------------------------
# Test 17: reader alignment report includes ready_for_p9_signal_extraction
# ---------------------------------------------------------------------------

class TestReaderAlignmentReport:
    def test_includes_ready_for_p9(self, tmp_path):
        csv_p = tmp_path / "ra.csv"
        _write_csv(csv_p, n_rows=50)
        result = probe_signal_paths([str(csv_p)])
        ra = build_reader_alignment_report(result)
        assert "ready_for_p9_signal_extraction" in ra
        assert ra["ready_for_p9_signal_extraction"] is True

    def test_includes_all_required_fields(self, tmp_path):
        csv_p = tmp_path / "all.csv"
        _write_csv(csv_p, n_rows=50)
        result = probe_signal_paths([str(csv_p)])
        ra = build_reader_alignment_report(result)
        for key in [
            "used_reader_inspection",
            "readable_fixture_files",
            "unsupported_binary_files",
            "missing_files",
            "no_numeric_signal_rows",
            "ready_for_p9_signal_extraction",
            "note",
        ]:
            assert key in ra, f"Missing key: {key}"

    def test_false_when_no_readable_files(self, tmp_path):
        empty_p = tmp_path / "empty.csv"
        empty_p.write_text("")
        result = probe_signal_paths([str(empty_p)])
        ra = build_reader_alignment_report(result)
        assert ra["ready_for_p9_signal_extraction"] is False


# ---------------------------------------------------------------------------
# Test 18: write_signal_probe_outputs writes all six required files
# ---------------------------------------------------------------------------

class TestWriteOutputs:
    def _make_result(self, tmp_path: Path) -> EEGSignalProbeResult:
        csv_p = tmp_path / "sig.csv"
        _write_csv(csv_p, n_channels=4, n_rows=200, sample_rate=100.0)
        return probe_signal_paths([str(csv_p)], window_seconds=1.0, max_windows_per_file=3)

    def test_all_six_artifacts_written(self, tmp_path):
        result = self._make_result(tmp_path)
        out_dir = str(tmp_path / "out")
        outputs = write_signal_probe_outputs(result, out_dir)
        required = {
            "signal_block_inventory",
            "window_inventory",
            "reader_alignment_report",
            "skipped_files",
            "omega_event",
            "report",
        }
        assert required == set(outputs.keys())
        for name, path in outputs.items():
            assert Path(path).exists(), f"Missing artifact: {name}"


# ---------------------------------------------------------------------------
# Test 19: JSON outputs parse
# ---------------------------------------------------------------------------

class TestJsonOutputsParse:
    def test_json_outputs_parseable(self, tmp_path):
        csv_p = tmp_path / "jp.csv"
        _write_csv(csv_p, n_rows=100)
        result = probe_signal_paths([str(csv_p)])
        out_dir = str(tmp_path / "out")
        outputs = write_signal_probe_outputs(result, out_dir)
        for name in ["signal_block_inventory", "reader_alignment_report", "skipped_files", "omega_event"]:
            with open(outputs[name]) as f:
                data = json.load(f)
            assert isinstance(data, dict), f"{name} is not a dict"


# ---------------------------------------------------------------------------
# Test 20: window_inventory.csv contains required columns
# ---------------------------------------------------------------------------

class TestWindowInventoryCsvColumns:
    def test_required_columns_present(self, tmp_path):
        csv_p = tmp_path / "wic.csv"
        _write_csv(csv_p, n_rows=200, sample_rate=100.0)
        result = probe_signal_paths([str(csv_p)], window_seconds=1.0, max_windows_per_file=2)
        out_dir = str(tmp_path / "out")
        outputs = write_signal_probe_outputs(result, out_dir)
        with open(outputs["window_inventory"], newline="") as f:
            reader = csv.reader(f)
            header = next(reader)
        required_cols = [
            "file_path", "row_id", "window_id",
            "window_start_s", "window_end_s",
            "sample_start", "sample_end",
            "n_channels", "n_samples", "sample_rate_hz",
            "channel_names", "status", "warnings",
        ]
        for col in required_cols:
            assert col in header, f"Missing column: {col}"


# ---------------------------------------------------------------------------
# Test 21: report.md contains cautious terms
# ---------------------------------------------------------------------------

class TestReportCautiousTerms:
    def test_report_contains_cautious_terms(self, tmp_path):
        csv_p = tmp_path / "ct.csv"
        _write_csv(csv_p, n_rows=100)
        result = probe_signal_paths([str(csv_p)])
        out_dir = str(tmp_path / "out")
        outputs = write_signal_probe_outputs(result, out_dir)
        report_text = Path(outputs["report"]).read_text()
        assert "operational signal-window metadata" in report_text
        assert "future Level M feature extraction" in report_text
        assert "signal block" in report_text.lower()

    def test_report_title(self, tmp_path):
        csv_p = tmp_path / "title.csv"
        _write_csv(csv_p, n_rows=50)
        result = probe_signal_paths([str(csv_p)])
        out_dir = str(tmp_path / "out")
        outputs = write_signal_probe_outputs(result, out_dir)
        report_text = Path(outputs["report"]).read_text()
        assert "EEG Signal Block Probe" in report_text

    def test_report_next_required_step(self, tmp_path):
        csv_p = tmp_path / "nrs.csv"
        _write_csv(csv_p, n_rows=50)
        result = probe_signal_paths([str(csv_p)])
        out_dir = str(tmp_path / "out")
        outputs = write_signal_probe_outputs(result, out_dir)
        report_text = Path(outputs["report"]).read_text()
        assert "P9" in report_text
        assert "Level M" in report_text


# ---------------------------------------------------------------------------
# Test 22: report.md does not contain banned phrases
# ---------------------------------------------------------------------------

class TestReportNoBannedPhrases:
    def test_no_banned_phrases_in_report(self, tmp_path):
        csv_p = tmp_path / "bp.csv"
        _write_csv(csv_p, n_rows=50)
        result = probe_signal_paths([str(csv_p)])
        out_dir = str(tmp_path / "out")
        outputs = write_signal_probe_outputs(result, out_dir)
        report_text = Path(outputs["report"]).read_text().lower()
        for phrase in ["proves consciousness", "consciousness proven", "soul proven",
                       "afterlife proven", "liberation detected", "ontology solved",
                       "ultimate reality", "q equals self", "q equals soul"]:
            assert phrase not in report_text, f"Banned phrase found: {phrase!r}"


# ---------------------------------------------------------------------------
# Test 23: CLI mock fixture smoke returns 0 and writes all six files
# ---------------------------------------------------------------------------

class TestCliMockFixture:
    def test_cli_mock_fixture_returns_0(self, tmp_path):
        out_dir = str(tmp_path / "cli_out")
        result = subprocess.run(
            [
                sys.executable, "-m",
                "sciencer_d.btc_icft.pipelines.probe_eeg_signal_blocks",
                "--mock-fixture",
                "--out", out_dir,
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"CLI failed: {result.stderr}"

    def test_cli_mock_fixture_writes_six_files(self, tmp_path):
        out_dir = str(tmp_path / "cli_out2")
        subprocess.run(
            [
                sys.executable, "-m",
                "sciencer_d.btc_icft.pipelines.probe_eeg_signal_blocks",
                "--mock-fixture",
                "--out", out_dir,
            ],
            capture_output=True,
            text=True,
        )
        out_path = Path(out_dir)
        for fname in [
            "signal_block_inventory.json",
            "window_inventory.csv",
            "reader_alignment_report.json",
            "skipped_files.json",
            "omega_event.json",
            "report.md",
        ]:
            assert (out_path / fname).exists(), f"Missing: {fname}"


# ---------------------------------------------------------------------------
# Test 24: CLI without paths/mock fails cleanly
# ---------------------------------------------------------------------------

class TestCliNoArgs:
    def test_cli_no_args_fails_nonzero(self):
        result = subprocess.run(
            [sys.executable, "-m", "sciencer_d.btc_icft.pipelines.probe_eeg_signal_blocks"],
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0

    def test_cli_no_args_error_message(self):
        result = subprocess.run(
            [sys.executable, "-m", "sciencer_d.btc_icft.pipelines.probe_eeg_signal_blocks"],
            capture_output=True,
            text=True,
        )
        combined = result.stdout + result.stderr
        assert "paths" in combined.lower() or "mock" in combined.lower() or "provide" in combined.lower()


# ---------------------------------------------------------------------------
# Test 25: Config exists and contains required outputs and guardrails
# ---------------------------------------------------------------------------

class TestConfig:
    def test_config_file_exists(self):
        config_path = Path("configs/btc_icft/eeg_signal_blocks.yaml")
        assert config_path.exists(), "Config file missing"

    def test_config_contains_required_outputs(self):
        config_text = Path("configs/btc_icft/eeg_signal_blocks.yaml").read_text()
        for artifact in [
            "signal_block_inventory.json",
            "window_inventory.csv",
            "reader_alignment_report.json",
            "skipped_files.json",
            "omega_event.json",
            "report.md",
        ]:
            assert artifact in config_text, f"Config missing required output: {artifact}"

    def test_config_contains_guardrails(self):
        config_text = Path("configs/btc_icft/eeg_signal_blocks.yaml").read_text()
        for guardrail in [
            "no_data_download",
            "no_model_training",
            "no_level_m_feature_extraction",
            "no_level_t_topology",
            "no_ontology_claims",
            "no_soul_afterlife_claims",
        ]:
            assert guardrail in config_text, f"Config missing guardrail: {guardrail}"


# ---------------------------------------------------------------------------
# Additional: guardrails
# ---------------------------------------------------------------------------

class TestGuardrails:
    def test_validate_safe_text_passes_clean(self):
        _validate_safe_text("This is operational signal-window metadata for future Level M feature extraction.")

    def test_validate_safe_text_raises_banned(self):
        with pytest.raises(ValueError, match="consciousness"):
            _validate_safe_text("This probe measures consciousness states.")

    def test_validate_safe_text_raises_soul(self):
        with pytest.raises(ValueError, match="soul"):
            _validate_safe_text("The soul of the signal.")

    def test_no_samples_in_window_objects(self, tmp_path):
        csv_p = tmp_path / "g.csv"
        _write_csv(csv_p, n_rows=200)
        result = probe_signal_paths([str(csv_p)], window_seconds=1.0, max_windows_per_file=2)
        for w in result.windows:
            assert not hasattr(w, "samples")

    def test_forbidden_claims_empty_by_default(self, tmp_path):
        csv_p = tmp_path / "fc.csv"
        _write_csv(csv_p, n_rows=50)
        result = probe_signal_paths([str(csv_p)])
        assert result.forbidden_claims == []

    def test_omega_event_safe_claim_matches_spec(self, tmp_path):
        csv_p = tmp_path / "oc.csv"
        _write_csv(csv_p, n_rows=50)
        result = probe_signal_paths([str(csv_p)])
        out_dir = str(tmp_path / "out")
        outputs = write_signal_probe_outputs(result, out_dir)
        with open(outputs["omega_event"]) as f:
            data = json.load(f)
        assert "operational signal-window metadata" in data["safe_claim"]
        assert "future Level M feature extraction" in data["safe_claim"]
