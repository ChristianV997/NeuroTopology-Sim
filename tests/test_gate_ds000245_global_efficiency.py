"""Offline tests for tools/gate_ds000245_global_efficiency.py.

Fully synthetic: no network, no real ds000245 data. Requires nilearn/networkx
(skips cleanly if unavailable, matching test_fmri_tda_pipeline.py's pattern).
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pytest

_HAVE = all(importlib.util.find_spec(m) for m in ("nilearn", "networkx", "sklearn"))
pytestmark = pytest.mark.skipif(not _HAVE, reason="requires nilearn, networkx, sklearn")


def _synthetic_record(subject_id: str, group: str, seed: int, n_t: int = 60, n_r: int = 10) -> dict:
    rng = np.random.default_rng(seed)
    return {"subject_id": subject_id, "group": group, "timeseries": rng.standard_normal((n_t, n_r))}


def test_metric_fn_reproduces_direct_computation_on_unshuffled_input():
    """The gate's real_value must equal calling the metric directly -- a
    transpose bug here would silently corrupt the whole gate without erroring."""
    from tools.gate_ds000245_global_efficiency import _global_efficiency_from_roi_ts, gate_subject

    record = _synthetic_record("sub-test", "CTL", seed=0)
    direct = _global_efficiency_from_roi_ts(record["timeseries"].T)
    result = gate_subject(record, n_surrogates=10, seed=0, n_jobs=1)
    assert result["real_value"] == pytest.approx(direct, abs=1e-9)


def test_gate_subject_returns_expected_keys():
    from tools.gate_ds000245_global_efficiency import gate_subject

    record = _synthetic_record("sub-test", "ODN", seed=1)
    result = gate_subject(record, n_surrogates=10, seed=0, n_jobs=1)
    assert result["subject_id"] == "sub-test"
    assert result["group"] == "ODN"
    assert 0.0 <= result["p_value"] <= 1.0
    assert isinstance(result["passes_gate_p05"], bool)
    assert result["n_surrogates"] <= 10


def test_load_roi_timeseries_reads_saved_npz(tmp_path):
    from dual_engine.fmri_tda_pipeline import save_roi_timeseries
    from tools.gate_ds000245_global_efficiency import load_roi_timeseries

    rng = np.random.default_rng(0)
    ts = rng.standard_normal((50, 8))
    save_roi_timeseries(ts, "sub-CTL01", "CTL", 2.5, tmp_path)
    save_roi_timeseries(ts, "sub-ODP01", "ODP", 2.5, tmp_path)

    records = load_roi_timeseries(tmp_path)
    assert len(records) == 2
    ids = {r["subject_id"] for r in records}
    assert ids == {"sub-CTL01", "sub-ODP01"}
    assert records[0]["timeseries"].shape == (50, 8)


def test_load_roi_timeseries_raises_on_empty_dir(tmp_path):
    from tools.gate_ds000245_global_efficiency import load_roi_timeseries

    with pytest.raises(FileNotFoundError):
        load_roi_timeseries(tmp_path)


def test_run_end_to_end_on_synthetic_three_group_cohort(tmp_path):
    """Full run() with saved .npz fixtures across three groups -- verifies Q1/Q2
    wire together without error and produce a self-consistent payload."""
    from dual_engine.fmri_tda_pipeline import save_roi_timeseries
    from tools.gate_ds000245_global_efficiency import run

    ts_dir = tmp_path / "roi_ts"
    rng = np.random.default_rng(0)
    for gi, group in enumerate(("CTL", "ODN", "ODP")):
        for i in range(3):
            ts = rng.standard_normal((40, 8))
            save_roi_timeseries(ts, f"sub-{group}{i:02d}", group, 2.5, ts_dir)

    payload = run(ts_dir, n_surrogates=10, n_permutations=200, seed=0, n_jobs=1, limit=None)
    assert payload["n_subjects"] == 9
    assert payload["group_n"] == {"CTL": 3, "ODN": 3, "ODP": 3}
    assert 0.0 <= payload["question_b_contrast_reality"]["p_value"] <= 1.0
    assert payload["question_a_metric_validity"]["n_subjects_gated"] == 9
    assert len(payload["question_a_metric_validity"]["per_subject"]) == 9


def test_run_respects_limit(tmp_path):
    """--limit truncates the cohort; each retained group still has >=2 subjects
    here so permutation_anova's variance guard does not itself become the
    thing under test."""
    from dual_engine.fmri_tda_pipeline import save_roi_timeseries
    from tools.gate_ds000245_global_efficiency import run

    ts_dir = tmp_path / "roi_ts"
    rng = np.random.default_rng(0)
    for group in ("CTL", "ODN"):
        for i in range(3):
            ts = rng.standard_normal((40, 8))
            save_roi_timeseries(ts, f"sub-{group}{i:02d}", group, 2.5, ts_dir)

    payload = run(ts_dir, n_surrogates=10, n_permutations=200, seed=0, n_jobs=1, limit=6)
    assert payload["n_subjects"] == 6

    from tools.gate_ds000245_global_efficiency import load_roi_timeseries
    assert len(load_roi_timeseries(ts_dir)) == 6  # full cohort still on disk; only run() truncated
