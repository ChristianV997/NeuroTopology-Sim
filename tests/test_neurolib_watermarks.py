"""Neurolib evidence watermark stamps — no neurolib install required."""
from __future__ import annotations

from pipelines.run_neurolib import neurolib_evidence_watermarks


def test_neurolib_watermarks_are_non_empirical():
    marks = neurolib_evidence_watermarks()
    assert marks["metrics_are_empirical"] is False
    assert marks["scientific_pass"] is False
    assert marks["run_mode"] == "synthetic"
    assert "synthetic" in marks["evidence_class"]
    assert marks["metric_kind"] == "neural_mass_topology"


def test_neurolib_watermarks_survive_run_record_make():
    from runs.run_record import RunRecordV1

    marks = neurolib_evidence_watermarks()
    record = RunRecordV1.make(
        run_id="abcd1234abcd1234",
        run_kind="neural_mass",
        data_mode="synthetic",
        metrics={"Q_mean": 0.0},
        **marks,
    )
    payload = record.to_dict()
    assert payload["evidence_class"] == marks["evidence_class"]
    assert payload["run_mode"] == "synthetic"
    assert payload["metrics_are_empirical"] is False
    assert payload["scientific_pass"] is False
    assert payload["metric_kind"] == "neural_mass_topology"
