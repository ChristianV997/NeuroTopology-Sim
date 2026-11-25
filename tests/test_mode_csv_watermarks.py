"""Fail-closed evidence watermarks for eeg / physionet / cross-domain / synthetic modes.

Stdlib-safe helpers are asserted without heavy deps; integration cases write
meta/RunRecord sidecars and require metrics_are_empirical=False.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from main import synthetic_evidence_watermarks
from pipelines.run_cross_domain import cross_domain_evidence_watermarks, run as run_cross_domain
from pipelines.run_eeg import eeg_evidence_watermarks, run as run_eeg
from pipelines.run_physionet import physionet_evidence_watermarks, run as run_physionet
from runs.run_record import RunRecordV1


def _assert_non_empirical(marks: dict, *, evidence_substr: str, run_mode: str) -> None:
    assert marks["metrics_are_empirical"] is False
    assert marks["scientific_pass"] is False
    assert marks["run_mode"] == run_mode
    assert evidence_substr in marks["evidence_class"]
    assert marks["metric_kind"]


def test_eeg_watermarks_are_non_empirical():
    _assert_non_empirical(
        eeg_evidence_watermarks(),
        evidence_substr="eeg",
        run_mode="eeg_analytic_proxy",
    )


def test_physionet_watermarks_are_non_empirical():
    _assert_non_empirical(
        physionet_evidence_watermarks(),
        evidence_substr="physionet",
        run_mode="physionet_spectral_proxy",
    )


def test_cross_domain_watermarks_are_non_empirical():
    _assert_non_empirical(
        cross_domain_evidence_watermarks(),
        evidence_substr="cross_domain",
        run_mode="cross_domain_aggregate",
    )


def test_synthetic_watermarks_are_non_empirical():
    _assert_non_empirical(
        synthetic_evidence_watermarks(),
        evidence_substr="synthetic",
        run_mode="synthetic",
    )


@pytest.mark.parametrize(
    "helper",
    [
        eeg_evidence_watermarks,
        physionet_evidence_watermarks,
        cross_domain_evidence_watermarks,
        synthetic_evidence_watermarks,
    ],
)
def test_mode_watermarks_survive_run_record_make(helper):
    marks = helper()
    record = RunRecordV1.make(
        run_id="abcd1234abcd1234",
        run_kind="mode_watermark_probe",
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


def test_eeg_empty_run_writes_meta_and_runrecord(tmp_path):
    out = tmp_path / "metrics_test.csv"
    df = run_eeg(tmp_path, out, dataset="ds_test")
    assert isinstance(df, pd.DataFrame)
    assert out.exists()

    meta = json.loads(Path(str(out) + ".meta.json").read_text(encoding="utf-8"))
    assert meta["metrics_are_empirical"] is False
    assert meta["scientific_pass"] is False
    assert meta["run_mode"] == "eeg_analytic_proxy"
    assert "eeg" in meta["evidence_class"]

    payload = json.loads((tmp_path / "RunRecord.json").read_text(encoding="utf-8"))
    assert payload["metrics_are_empirical"] is False
    assert payload["scientific_pass"] is False
    assert payload["run_kind"] == "eeg"


def test_physionet_run_keeps_proxy_suffix_and_watermarks(tmp_path):
    rng = np.random.default_rng(0)
    n = 64
    smooth = np.sin(np.linspace(0, 4 * np.pi, n))
    noisy = rng.standard_normal(n)
    (tmp_path / "subA_val_spec.csv").write_text("\n".join(str(float(v)) for v in smooth))
    (tmp_path / "subB_val_spec.csv").write_text("\n".join(str(float(v)) for v in noisy))

    out = tmp_path / "metrics_physionet_gaba.csv"
    df = run_physionet(tmp_path, out)
    assert len(df) == 2
    assert {"Q_proxy", "Qabs_proxy", "metric_kind"}.issubset(df.columns)
    assert "Q" not in df.columns  # never promote proxy → topology alias
    assert set(df["metric_kind"]) == {"physionet_spectral_phase_proxy"}

    meta = json.loads(Path(str(out) + ".meta.json").read_text(encoding="utf-8"))
    assert meta["metrics_are_empirical"] is False
    assert meta["scientific_pass"] is False
    assert "physionet" in meta["evidence_class"]

    payload = json.loads((tmp_path / "RunRecord.json").read_text(encoding="utf-8"))
    assert payload["metrics_are_empirical"] is False
    assert payload["scientific_pass"] is False
    assert payload["run_kind"] == "physionet"


def test_cross_domain_physionet_q_proxy_not_silent_topology_alias(tmp_path):
    pytest.importorskip("sklearn")
    results = tmp_path / "results"
    phys = results / "physionet_gaba"
    phys.mkdir(parents=True)
    pd.DataFrame(
        {
            "file": ["a.csv", "b.csv"],
            "Q_proxy": [0.1, 0.2],
            "Qabs_proxy": [0.3, 0.4],
            "metric_kind": ["physionet_spectral_phase_proxy"] * 2,
        }
    ).to_csv(phys / "metrics_physionet_gaba.csv", index=False)

    eeg_dir = results / "ds002094"
    eeg_dir.mkdir(parents=True)
    pd.DataFrame(
        {
            "Q": [1.0, 1.5],
            "Qabs": [2.0, 2.5],
            "phase_grad": [0.1, 0.2],
            "pcist_proxy": [0.5, 0.6],
        }
    ).to_csv(eeg_dir / "metrics_ds002094.csv", index=False)

    out = tmp_path / "cross.csv"
    df = run_cross_domain(results, out)
    assert len(df) >= 1

    phys_rows = df[df["dataset"] == "physionet_gaba"]
    assert len(phys_rows) == 1
    assert phys_rows.iloc[0]["q_source"] == "Q_proxy"
    assert phys_rows.iloc[0]["metric_kind"] == "physionet_spectral_phase_proxy"

    eeg_rows = df[df["dataset"] == "ds002094"]
    assert len(eeg_rows) == 1
    assert eeg_rows.iloc[0]["q_source"] == "Q"

    meta = json.loads(Path(str(out) + ".meta.json").read_text(encoding="utf-8"))
    assert meta["metrics_are_empirical"] is False
    assert meta["scientific_pass"] is False
    assert meta["cluster_inputs_are_commensurate"] is False
    assert "cross_domain" in meta["evidence_class"]

    payload = json.loads((tmp_path / "RunRecord.json").read_text(encoding="utf-8"))
    assert payload["metrics_are_empirical"] is False
    assert payload["scientific_pass"] is False
    assert payload["run_kind"] == "cross_domain"


def test_synthetic_mode_stamps_watermarks(tmp_path, monkeypatch):
    from main import run_synthetic

    monkeypatch.chdir(tmp_path)
    run_synthetic()

    summary = tmp_path / "results" / "synthetic" / "synthetic_summary.csv"
    assert summary.exists()
    df = pd.read_csv(summary)
    assert (df["metrics_are_empirical"] == False).all()  # noqa: E712
    assert (df["scientific_pass"] == False).all()  # noqa: E712
    assert (df["run_mode"] == "synthetic").all()
    assert "pass_charge_check" in df.columns  # engineering only

    meta = json.loads(
        (tmp_path / "results" / "synthetic" / "evidence_meta.json").read_text(encoding="utf-8")
    )
    assert meta["metrics_are_empirical"] is False
    assert meta["scientific_pass"] is False

    payload = json.loads(
        (tmp_path / "results" / "synthetic" / "RunRecord.json").read_text(encoding="utf-8")
    )
    assert payload["metrics_are_empirical"] is False
    assert payload["scientific_pass"] is False
    assert payload["run_kind"] == "synthetic"
