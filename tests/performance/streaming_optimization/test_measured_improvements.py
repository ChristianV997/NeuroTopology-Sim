"""Compare live behaviour against the pre-change baseline record.

Wall-clock numbers are host-dependent. This file asserts *structural*
improvements that the baseline measured as missing, and records live
timings for the report without treating them as scientific evidence.
"""
from __future__ import annotations

import json
from pathlib import Path

import data.bids_ingest as bi
import tools.streaming.base_runner as br

from tests.performance.streaming_optimization.conftest import requires_mne

BASELINE_PATH = Path(__file__).resolve().parent / "recorded_baseline.json"


def test_static_gates_against_recorded_baseline():
    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    src_runner = Path(br.__file__).read_text(encoding="utf-8")
    src_bids = Path(bi.__file__).read_text(encoding="utf-8")
    task_fn = src_runner.split("def list_s3_task_labels", 1)[1].split("def sync_s3_subject", 1)[0]

    assert "timeout=timeout_s" in src_runner
    assert "os.fsync" in src_runner
    assert "manifest_path.write_text" not in src_runner
    assert "_is_valid_work_unit" in src_runner
    assert 'manifest["failed_subjects"].pop(subject, None)' in src_runner
    assert "list_s3_subjects(" not in task_fn
    assert "if not batch" in src_runner
    assert 'rglob("*")' not in src_bids
    assert "_PREPROCESS_CACHE" in src_bids
    assert baseline["static"]["subprocess_run_has_timeout"] is False
    assert baseline["preprocess_read_reuse"]["preprocess_fresh_reads_after_window2"] == 2


@requires_mne
def test_preprocess_reuse_improves_on_baseline(tmp_path):
    from tests.fixtures.make_synthetic_bids import build

    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    root = build(str(tmp_path / "bids"), subjects=("01",), states=("awake",))
    path = bi.discover_bids_eeg(str(root))[0].path
    bi.clear_raw_cache()
    calls = {"fresh": 0}
    real = bi._read_raw

    def counting(p):
        calls["fresh"] += 1
        return real(p)

    bi._read_raw = counting
    preprocess = {"l_freq": 1.0, "h_freq": 40.0, "reference": None}
    try:
        bi.read_window_signal(path, 0.0, 2.0, pick="mean", max_channels=4, preprocess=preprocess)
        bi.read_window_signal(path, 2.0, 4.0, pick="mean", max_channels=4, preprocess=preprocess)
        bi.read_window_signal(path, 0.0, 2.0, pick="mean", max_channels=4, preprocess=preprocess)
    finally:
        bi._read_raw = real
        bi.clear_raw_cache()
    assert calls["fresh"] == 1
    assert (
        calls["fresh"]
        < baseline["preprocess_read_reuse"]["preprocess_fresh_reads_after_cached_window_replay"]
    )
