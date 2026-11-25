"""Fail-closed watermarks for mock MNE extract fixtures."""

from __future__ import annotations

import json

from sciencer_d.btc_icft.io.eeg_mne_adapter import (
    mne_extract_evidence_watermarks,
    write_mne_signal_outputs,
)
from sciencer_d.btc_icft.pipelines.extract_mne_signal_blocks import _mock_result
from tools.check_eeg_artifact_watermarks import main as watermark_scan_main


def test_mne_extract_watermarks_mock_are_non_empirical():
    marks = mne_extract_evidence_watermarks(mock_fixture=True)
    assert marks["scientific_pass"] is False
    assert marks["metrics_are_empirical"] is False
    assert marks["run_mode"] == "mock"
    assert "mock" in marks["evidence_class"]


def test_mock_result_windows_never_claim_scientific_pass():
    r = _mock_result("DS005620", "mock.edf")
    assert r.scientific_pass is False
    assert r.run_mode == "mock"
    assert r.metrics_are_empirical is False
    assert r.n_windows == 2
    assert r.omega_event["n_windows"] == 2
    assert r.omega_event["scientific_pass"] is False
    for win in r.windows:
        assert win["scientific_pass"] is False
        assert win["is_valid"] is True  # finite synthetic values
        assert win["run_mode"] == "mock"


def test_mock_fixture_artifacts_pass_watermark_scanner(tmp_path):
    out = tmp_path / "out"
    r = _mock_result("DS005620", "mock.edf")
    write_mne_signal_outputs(r, str(out))
    assert watermark_scan_main([str(out)]) == 0

    # Inject a false scientific_pass claim and ensure scanner rejects.
    bad = json.loads((out / "mne_extraction_report.json").read_text())
    bad["scientific_pass"] = True
    (out / "mne_extraction_report.json").write_text(json.dumps(bad), encoding="utf-8")
    assert watermark_scan_main([str(out)]) != 0
