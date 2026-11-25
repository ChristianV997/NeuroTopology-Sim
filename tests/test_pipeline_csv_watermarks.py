"""Fail-closed evidence watermarks for physics / qzt / external / fast_tr pipelines.

Stdlib-safe helpers are asserted without heavy deps; integration cases write
meta/RunRecord sidecars and require metrics_are_empirical=False.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

from pipelines.run_external import external_evidence_watermarks, run as run_external
from pipelines.run_fast_tr_validation import fast_tr_evidence_watermarks
from pipelines.run_physics import physics_evidence_watermarks, run_from_npy
from pipelines.run_qzt import qzt_evidence_watermarks, run as run_qzt
from runs.run_record import RunRecordV1


def _assert_non_empirical(marks: dict, *, evidence_substr: str, run_mode: str) -> None:
    assert marks["metrics_are_empirical"] is False
    assert marks["scientific_pass"] is False
    assert marks["run_mode"] == run_mode
    assert evidence_substr in marks["evidence_class"]
    assert marks["metric_kind"]


def test_physics_watermarks_are_non_empirical():
    _assert_non_empirical(
        physics_evidence_watermarks(),
        evidence_substr="physics",
        run_mode="synthetic",
    )


def test_qzt_watermarks_are_non_empirical():
    _assert_non_empirical(
        qzt_evidence_watermarks(),
        evidence_substr="qzt",
        run_mode="synthetic",
    )


def test_external_watermarks_are_non_empirical():
    _assert_non_empirical(
        external_evidence_watermarks(),
        evidence_substr="external",
        run_mode="external_ingest",
    )


def test_fast_tr_watermarks_are_non_empirical():
    _assert_non_empirical(
        fast_tr_evidence_watermarks(),
        evidence_substr="fast_tr",
        run_mode="synthetic",
    )


@pytest.mark.parametrize(
    "helper",
    [
        physics_evidence_watermarks,
        qzt_evidence_watermarks,
        external_evidence_watermarks,
        fast_tr_evidence_watermarks,
    ],
)
def test_pipeline_watermarks_survive_run_record_make(helper):
    marks = helper()
    record = RunRecordV1.make(
        run_id="abcd1234abcd1234",
        run_kind="pipeline_watermark_probe",
        data_mode="synthetic",
        metrics={"Q_mean": 0.0},
        **marks,
    )
    payload = record.to_dict()
    assert payload["evidence_class"] == marks["evidence_class"]
    assert payload["run_mode"] == marks["run_mode"]
    assert payload["metrics_are_empirical"] is False
    assert payload["scientific_pass"] is False
    assert payload["metric_kind"] == marks["metric_kind"]


def test_physics_run_writes_meta_and_runrecord(tmp_path):
    # The-Well loader expects last-axis (vx, vy) velocity components.
    npy = tmp_path / "sample.npy"
    yy, xx = np.mgrid[0:8, 0:8]
    field = np.stack([xx.astype(float), yy.astype(float)], axis=-1)
    np.save(npy, field)

    out = tmp_path / "the_well.csv"
    df = run_from_npy(npy, out)
    assert isinstance(df, pd.DataFrame)
    assert out.exists()

    meta_path = Path(str(out) + ".meta.json")
    assert meta_path.exists()
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert meta["metrics_are_empirical"] is False
    assert meta["scientific_pass"] is False
    assert meta["run_mode"] == "synthetic"
    assert "physics" in meta["evidence_class"]

    record_path = tmp_path / "RunRecord.json"
    assert record_path.exists()
    payload = json.loads(record_path.read_text(encoding="utf-8"))
    assert payload["metrics_are_empirical"] is False
    assert payload["scientific_pass"] is False
    assert payload["evidence_class"] == meta["evidence_class"]


def test_qzt_run_writes_evidence_meta_and_runrecord(tmp_path):
    from validation.synthetic import single_vortex

    cp = tmp_path / "step0"
    cp.mkdir()
    np.save(cp / "psi.npy", single_vortex(N=8))

    out = tmp_path / "out"
    qzt, ev = run_qzt(tmp_path, out)
    assert isinstance(qzt, pd.DataFrame)
    assert isinstance(ev, pd.DataFrame)

    meta_path = out / "evidence_meta.json"
    assert meta_path.exists()
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert meta["metrics_are_empirical"] is False
    assert meta["scientific_pass"] is False
    assert "qzt" in meta["evidence_class"]

    payload = json.loads((out / "RunRecord.json").read_text(encoding="utf-8"))
    assert payload["metrics_are_empirical"] is False
    assert payload["scientific_pass"] is False
    assert payload["run_kind"] == "qzt"


def test_external_run_stamps_meta_and_runrecord(tmp_path):
    sensor_path = tmp_path / "live.jsonl"
    records = [
        {"timestamp": 1.0, "sensor_id": "s1", "Q": 1.0, "Qabs": 1.0},
        {"timestamp": 2.0, "sensor_id": "s1", "phase_deltas": [1.0, -0.5, 0.5]},
    ]
    sensor_path.write_text("\n".join(json.dumps(r) for r in records), encoding="utf-8")

    cfg_path = tmp_path / "cfg.yaml"
    cfg_path.write_text(
        yaml.safe_dump(
            {
                "external": {
                    "connectors": [{"type": "file", "params": {"path": str(sensor_path)}}]
                }
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    out_csv = tmp_path / "live.csv"
    db_path = tmp_path / "runs.sqlite"
    df = run_external(cfg_path, out_csv, db_path, max_records=10)
    assert len(df) == 2

    meta = json.loads(Path(str(out_csv) + ".meta.json").read_text(encoding="utf-8"))
    assert meta["metrics_are_empirical"] is False
    assert meta["scientific_pass"] is False
    assert meta["run_mode"] == "external_ingest"
    assert "external" in meta["evidence_class"]

    payload = json.loads((tmp_path / "RunRecord.json").read_text(encoding="utf-8"))
    assert payload["metrics_are_empirical"] is False
    assert payload["scientific_pass"] is False
    assert payload["run_kind"] == "external"


def test_fast_tr_runrecord_carries_watermarks(tmp_path):
    pytest.importorskip("scipy")
    from pipelines.run_fast_tr_validation import run as run_fast_tr

    out = tmp_path / "fast_tr.json"
    record = run_fast_tr(
        output_csv=out,
        n_voxels=8,
        n_timepoints=16,
        tr=0.645,
        seed=0,
    )
    payload = record.to_dict()
    assert payload["metrics_are_empirical"] is False
    assert payload["scientific_pass"] is False
    assert payload["run_mode"] == "synthetic"
    assert "fast_tr" in payload["evidence_class"]
    assert out.exists()
    on_disk = json.loads(out.read_text(encoding="utf-8"))
    assert on_disk["scientific_pass"] is False
    assert on_disk["metrics_are_empirical"] is False
