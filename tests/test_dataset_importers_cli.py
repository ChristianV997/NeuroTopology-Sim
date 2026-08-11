"""Subprocess CLI tests for `python -m dataset_importers.export_candidates`.
Synthetic fixtures only -- no network access, no raw data download.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from dataset_importers.eegdash_importer import _is_eegdash_installed
from dataset_importers.moabb_importer import _is_moabb_installed

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "dataset_importers.export_candidates", *args],
        capture_output=True, text=True, cwd=str(_REPO_ROOT),
    )


def _write_moabb_fixture(tmp_path: Path) -> Path:
    path = tmp_path / "moabb_fixture.json"
    path.write_text(
        json.dumps(
            {
                "source_catalog": "moabb",
                "datasets": [
                    {
                        "code": "CliDs1", "name": "CLI test dataset", "paradigm": "imagery",
                        "event_id": {"left": 1, "right": 2}, "subject_count": 8,
                        "license": "CC0", "access_status": "public",
                    },
                    {"code": "CliDs2", "name": "CLI sparse dataset"},
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def test_cli_from_fixture_works(tmp_path):
    fixture = _write_moabb_fixture(tmp_path)
    out = tmp_path / "out.json"
    result = _run_cli("--from-fixture", str(fixture), "--out", str(out))
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["n_candidates"] == 2
    assert out.exists()
    written = json.loads(out.read_text(encoding="utf-8"))
    assert len(written["candidates"]) == 2


def test_cli_rank_works(tmp_path):
    fixture = _write_moabb_fixture(tmp_path)
    out = tmp_path / "out.json"
    result = _run_cli("--from-fixture", str(fixture), "--out", str(out), "--rank")
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert "top_candidates" in payload
    assert len(payload["top_candidates"]) == 2


def test_cli_top_limits_results(tmp_path):
    fixture = _write_moabb_fixture(tmp_path)
    out = tmp_path / "out.json"
    result = _run_cli("--from-fixture", str(fixture), "--out", str(out), "--rank", "--top", "1")
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert len(payload["top_candidates"]) == 1


def test_cli_to_benchmark_candidates_works(tmp_path):
    fixture = _write_moabb_fixture(tmp_path)
    out = tmp_path / "out.json"
    bench_out = tmp_path / "bench.json"
    result = _run_cli(
        "--from-fixture", str(fixture), "--out", str(out), "--to-benchmark-candidates", str(bench_out)
    )
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert "n_benchmark_dataset_records" in payload
    assert bench_out.exists()
    bench_payload = json.loads(bench_out.read_text(encoding="utf-8"))
    assert "dataset_records" in bench_payload
    assert "artifact_records" in bench_payload


def test_cli_prints_counts_by_role(tmp_path):
    fixture = _write_moabb_fixture(tmp_path)
    out = tmp_path / "out.json"
    result = _run_cli("--from-fixture", str(fixture), "--out", str(out))
    payload = json.loads(result.stdout)
    for role in ("blocked", "review_needed", "development_candidate", "exploration_candidate", "documentation_only"):
        assert role in payload["counts"]


def test_cli_missing_package_without_fixture_fails_clearly(tmp_path):
    if _is_moabb_installed():
        import pytest

        pytest.skip("moabb is installed in this environment; unavailable-path is not exercised here")
    out = tmp_path / "out.json"
    result = _run_cli("--source", "moabb", "--out", str(out))
    assert result.returncode == 1
    assert "FAILED" in result.stdout
    assert not out.exists()


def test_cli_all_source_succeeds_with_zero_candidates_when_no_live_query(tmp_path):
    """`--source all` without a fixture only fails if *every* source is
    unavailable; when eegdash is installed but live-query defaults off it
    contributes zero candidates without failing the whole run."""
    if not _is_eegdash_installed():
        import pytest

        pytest.skip("eegdash is not installed in this environment")
    out = tmp_path / "out.json"
    result = _run_cli("--source", "all", "--out", str(out))
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["n_candidates"] == 0


def test_cli_never_downloads_raw_data(tmp_path):
    """The CLI's own source code must never reference a raw-data download
    method -- a static guard against regressions, alongside the runtime
    behavior already exercised above."""
    source = (_REPO_ROOT / "dataset_importers" / "export_candidates.py").read_text(encoding="utf-8")
    for banned in (".get_data(", ".download(", "EEGDashDataset("):
        assert banned not in source


def test_cli_output_is_deterministic(tmp_path):
    """Two independent runs over the same fixture must agree on content and
    ordering (candidate_id order, sorted JSON keys) -- only each record's
    own `created_at` timestamp is allowed to differ between runs."""
    fixture = _write_moabb_fixture(tmp_path)
    out1 = tmp_path / "out1.json"
    out2 = tmp_path / "out2.json"
    _run_cli("--from-fixture", str(fixture), "--out", str(out1))
    _run_cli("--from-fixture", str(fixture), "--out", str(out2))

    def _strip_timestamps(payload):
        for candidate in payload["candidates"]:
            candidate.pop("created_at", None)
        return payload

    payload1 = _strip_timestamps(json.loads(out1.read_text(encoding="utf-8")))
    payload2 = _strip_timestamps(json.loads(out2.read_text(encoding="utf-8")))
    assert payload1 == payload2
    assert [c["candidate_id"] for c in payload1["candidates"]] == sorted(
        c["candidate_id"] for c in payload1["candidates"]
    )


def test_cli_from_fixture_eegdash(tmp_path):
    path = tmp_path / "eegdash_fixture.json"
    path.write_text(
        json.dumps(
            {
                "source_catalog": "eegdash",
                "datasets": [
                    {
                        "dataset_id": "dsCliEegdash", "name": "CLI eegdash test", "source": "openneuro",
                        "recording_modality": ["eeg"], "tasks": ["rest", "task"], "license": "CC0",
                        "demographics": {"subjects_count": 12},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    out = tmp_path / "out.json"
    result = _run_cli("--from-fixture", str(path), "--out", str(out))
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["n_candidates"] == 1


def test_cli_fixture_with_unknown_source_catalog_fails_clearly(tmp_path):
    path = tmp_path / "bad_fixture.json"
    path.write_text(json.dumps({"source_catalog": "not_a_real_catalog", "datasets": []}), encoding="utf-8")
    out = tmp_path / "out.json"
    result = _run_cli("--from-fixture", str(path), "--out", str(out))
    assert result.returncode == 1
    assert "FAILED" in result.stdout
