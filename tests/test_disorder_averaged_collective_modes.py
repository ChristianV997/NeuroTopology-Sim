"""Offline fixture tests for disorder-averaged collective modes + RunRecord sidecar."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from scripts.run_disorder_averaged_collective_modes import (
    CAMPAIGN_FILENAME,
    CAMPAIGN_SCHEMA,
    RUN_RECORD_SIDECAR_FILENAME,
    _append_checkpoint,
    _initialize_checkpoint,
    _load_checkpoint,
    _run_fingerprint,
    _signed_permutation_pvalue,
    _as_int,
    _finite_float,
    _sidecar_verdict,
    _summarize,
    build_run_record_sidecar,
    parser,
    run,
    sidecar_to_dict,
    write_run_record_sidecar,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]
_CONTRACT_PATH = (
    _REPO_ROOT / "contracts" / "campaign" / "disorder_averaged_collective_modes_run_record.contract.json"
)
_BANNED_NETWORK = (
    "requests.get(",
    "urllib.request",
    "http.client",
    "boto3",
    "s3.download",
    "nilearn.datasets.fetch",
    "openneuro",
    "airtable",
)


def test_exact_sign_flip_pvalue_is_deterministic_and_two_sided() -> None:
    values = np.array([0.4, 0.3, 0.2, 0.1])
    assert _signed_permutation_pvalue(values) == _signed_permutation_pvalue(-values)
    assert 0.0 < _signed_permutation_pvalue(values) <= 1.0


def test_summary_uses_matched_disorder_and_null_adjustment() -> None:
    records = []
    for seed in (10, 11):
        for spacing, candidate_tau, null_tau in ((3.0, 4.0, 2.0), (18.0, 2.0, 2.0)):
            records.extend((
                {"spacing_nm": spacing, "collective_rate_s": 0.0, "disorder_seed": seed, "converged": True, "tau_subradiant_s": null_tau},
                {"spacing_nm": spacing, "collective_rate_s": 1e7, "disorder_seed": seed, "converged": True, "tau_subradiant_s": candidate_tau},
            ))
    summary = _summarize(records, [3.0, 18.0], [0.0, 1e7])[0]
    assert summary["paired_disorder_samples"] == 2
    assert summary["mean_log_short_vs_long_null_adjusted_contrast"] == np.log(2.0)


def test_summary_rejects_nonfinite_lifetime_pairs():
    records = [
        {"spacing_nm": 3.0, "collective_rate_s": 0.0, "disorder_seed": 10, "converged": True, "tau_subradiant_s": np.inf},
        {"spacing_nm": 18.0, "collective_rate_s": 0.0, "disorder_seed": 10, "converged": True, "tau_subradiant_s": 2.0},
        {"spacing_nm": 3.0, "collective_rate_s": 1e7, "disorder_seed": 10, "converged": True, "tau_subradiant_s": 4.0},
        {"spacing_nm": 18.0, "collective_rate_s": 1e7, "disorder_seed": 10, "converged": True, "tau_subradiant_s": 2.0},
    ]
    summary = _summarize(records, [3.0, 18.0], [0.0, 1e7])[0]
    assert summary["paired_disorder_samples"] == 0
    assert summary["invalid_disorder_samples"] == 1
    assert summary["mean_log_short_vs_long_null_adjusted_contrast"] is None


def test_checkpoint_round_trip_and_fingerprint_guard(tmp_path):
    path = tmp_path / "records.jsonl"
    fingerprint = "abc123"
    _initialize_checkpoint(path, fingerprint)
    record = {"point_id": "spacing=3;collective_rate=0;seed=1", "converged": True}
    _append_checkpoint(path, record)
    assert _load_checkpoint(path, fingerprint) == {record["point_id"]: record}
    with pytest.raises(ValueError):
        _load_checkpoint(path, "different")


def _fixture_records(*, finite: bool) -> list[dict]:
    records = []
    short_null = 2.0 if finite else float("inf")
    for seed in (10, 11):
        for spacing, candidate_tau, null_tau in ((3.0, 4.0, short_null), (18.0, 2.0, 2.0)):
            records.extend((
                {"spacing_nm": spacing, "collective_rate_s": 0.0, "disorder_seed": seed, "converged": True, "tau_subradiant_s": null_tau},
                {"spacing_nm": spacing, "collective_rate_s": 1e7, "disorder_seed": seed, "converged": True, "tau_subradiant_s": candidate_tau},
            ))
    return records


def _fixture_payload(*, finite: bool = True, campaign_decision: str | None = None) -> dict:
    records = _fixture_records(finite=finite)
    summaries = _summarize(records, [3.0, 18.0], [0.0, 1e7])
    if campaign_decision is None:
        campaign_decision = "EFFECT_CANDIDATE" if finite else "NOT_SUPPORTED"
    for summary in summaries:
        summary["pre_registered_decision"] = campaign_decision
    return {
        "schema": CAMPAIGN_SCHEMA,
        "configuration": {
            "spacings_nm": [3.0, 18.0],
            "collective_rates_s": [0.0, 1e7],
            "disorder_samples": 2,
            "seed": 20260727,
            "min_abs_log_contrast": float(np.log(1.25)),
            "alpha": 0.05,
        },
        "records": records,
        "summaries": summaries,
        "scientific_note": "Finite dipolar lattice calculations test model sensitivity only. They do not establish biological subradiance or quantum coherence.",
    }


def _fake_evaluate(task: dict) -> dict:
    spacing = task["spacing_nm"]
    rate = task["collective_rate_s"]
    if rate == 0.0:
        tau = 2.0
    elif spacing == 3.0:
        tau = 4.0
    else:
        tau = 2.0
    return {
        **task,
        "dimension": 2,
        "method": "fixture",
        "converged": True,
        "tau_subradiant_s": tau,
        "gap_s": 1.0,
        "trace_preservation_residual_s": 0.0,
        "failure": None,
    }


def _assert_campaign_omits_sidecar_flag(payload: dict) -> None:
    assert "write_run_record" not in payload["configuration"]
    for record in payload["records"]:
        assert "write_run_record" not in record


def _parse_run_args(tmp_path: Path, *, write_run_record: bool, seed: int = 20260727) -> object:
    flags = [
        "--disorder-samples", "2",
        "--workers", "1",
        "--spacings-nm", "3", "18",
        "--collective-rates-s", "0", "1e7",
        "--seed", str(seed),
        "--progress-every", "0",
        "--output-dir", str(tmp_path),
    ]
    if write_run_record:
        flags.append("--write-run-record")
    return parser().parse_args(flags)


def test_write_run_record_flag_does_not_change_fingerprint(tmp_path):
    off = _parse_run_args(tmp_path, write_run_record=False)
    on = _parse_run_args(tmp_path, write_run_record=True)
    assert _run_fingerprint(off) == _run_fingerprint(on)


def test_sidecar_builder_schema_and_stable_run_id(tmp_path):
    payload = _fixture_payload(finite=True)
    campaign = tmp_path / CAMPAIGN_FILENAME
    campaign.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    first = build_run_record_sidecar(payload, campaign, fingerprint="abc")
    second = build_run_record_sidecar(payload, campaign, fingerprint="abc")
    dumped = sidecar_to_dict(first)
    assert dumped["schema_version"] == "0.1"
    assert dumped["run_kind"] == "disorder_averaged_collective_modes"
    assert first.run_id == second.run_id
    assert len(first.run_id) == 16
    assert first.verdict in {"NOT_SUPPORTED", "INCONCLUSIVE"}
    assert first.verdict != "PASS"
    assert first.artifacts["campaign_json"] == CAMPAIGN_FILENAME
    assert first.artifacts["campaign_schema"] == CAMPAIGN_SCHEMA
    assert first.artifacts["campaign_sha256"] == hashlib.sha256(campaign.read_bytes()).hexdigest()
    assert dumped["input"]["seed"] == 20260727
    assert dumped["notes"] == payload["scientific_note"]
    assert dumped["guardrails"]["pass_reserved_for_bayes_factor_k_gt_100"] is True
    assert "input" not in first.to_dict()
    assert "notes" not in first.to_dict()
    assert "guardrails" not in first.to_dict()


def test_atomic_sidecar_write_keeps_provenance_fields(tmp_path):
    payload = _fixture_payload(finite=True)
    campaign = tmp_path / CAMPAIGN_FILENAME
    campaign.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    record = build_run_record_sidecar(payload, campaign, fingerprint="abc")
    path = tmp_path / RUN_RECORD_SIDECAR_FILENAME
    write_run_record_sidecar(record, path)
    written = json.loads(path.read_text(encoding="utf-8"))
    assert written["schema_version"] == "0.1"
    assert written["input"] == sidecar_to_dict(record)["input"]
    assert written["notes"] == payload["scientific_note"]
    assert written["guardrails"]["sidecar_does_not_replace_campaign_json"] is True
    assert not list(tmp_path.glob(".RunRecord.json.*.tmp"))


def test_sidecar_never_promotes_effect_candidate_to_pass():
    payload = _fixture_payload(finite=True)
    assert payload["summaries"][0]["pre_registered_decision"] == "EFFECT_CANDIDATE"
    assert _sidecar_verdict(payload) == "NOT_SUPPORTED"


def test_sidecar_accepts_numpy_scalars_for_identity_and_verdict(tmp_path):
    python_payload = _fixture_payload(finite=True)
    numpy_payload = _fixture_payload(finite=True)
    numpy_payload["configuration"]["seed"] = np.int64(20260727)
    numpy_payload["configuration"]["alpha"] = np.float64(0.05)
    summary = numpy_payload["summaries"][0]
    summary["paired_disorder_samples"] = np.int64(summary["paired_disorder_samples"])
    summary["invalid_disorder_samples"] = np.int64(summary["invalid_disorder_samples"])
    summary["mean_log_short_vs_long_null_adjusted_contrast"] = np.float64(
        summary["mean_log_short_vs_long_null_adjusted_contrast"]
    )
    campaign = tmp_path / CAMPAIGN_FILENAME
    campaign.write_text(json.dumps(python_payload, sort_keys=True), encoding="utf-8")
    python_record = build_run_record_sidecar(python_payload, campaign, fingerprint="abc")
    numpy_record = build_run_record_sidecar(numpy_payload, campaign, fingerprint="abc")
    assert python_record.run_id == numpy_record.run_id
    assert _sidecar_verdict(numpy_payload) == "NOT_SUPPORTED"
    assert _finite_float(np.float64(1.25)) == 1.25
    assert _as_int(np.int64(2)) == 2


def test_missing_or_invalid_campaign_stays_not_supported_or_inconclusive(tmp_path):
    invalid_payload = _fixture_payload(finite=False)
    assert invalid_payload["summaries"][0]["pre_registered_decision"] == "NOT_SUPPORTED"
    assert invalid_payload["summaries"][0]["paired_disorder_samples"] == 0
    assert _sidecar_verdict(invalid_payload) in {"NOT_SUPPORTED", "INCONCLUSIVE"}
    assert _sidecar_verdict(invalid_payload) != "PASS"
    missing = build_run_record_sidecar({"schema": "not-a-campaign"}, tmp_path / "missing.json")
    assert missing.verdict == "INCONCLUSIVE"
    assert missing.verdict != "PASS"


def test_opt_in_run_writes_sidecar_and_keeps_campaign_json(tmp_path, monkeypatch):
    import scripts.run_disorder_averaged_collective_modes as campaign

    monkeypatch.setattr(campaign, "_evaluate", _fake_evaluate)
    first_dir = tmp_path / "run1"
    second_dir = tmp_path / "run2"
    first = run(_parse_run_args(first_dir, write_run_record=True))
    second = run(_parse_run_args(second_dir, write_run_record=True))
    campaign_path = first_dir / CAMPAIGN_FILENAME
    sidecar_path = first_dir / RUN_RECORD_SIDECAR_FILENAME
    assert campaign_path.is_file()
    assert sidecar_path.is_file()
    assert first["schema"] == CAMPAIGN_SCHEMA
    campaign_doc = json.loads(campaign_path.read_text(encoding="utf-8"))
    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    assert campaign_doc["schema"] == CAMPAIGN_SCHEMA
    assert sidecar["schema_version"] == "0.1"
    assert sidecar["run_id"] == json.loads((second_dir / RUN_RECORD_SIDECAR_FILENAME).read_text(encoding="utf-8"))["run_id"]
    assert sidecar["verdict"] in {"NOT_SUPPORTED", "INCONCLUSIVE"}
    assert sidecar["verdict"] != "PASS"
    assert sidecar["artifacts"]["campaign_sha256"] == hashlib.sha256(campaign_path.read_bytes()).hexdigest()
    _assert_campaign_omits_sidecar_flag(campaign_doc)
    _assert_campaign_omits_sidecar_flag(first)
    assert sidecar["input"]["seed"] == 20260727
    assert sidecar["notes"]
    assert sidecar["guardrails"]["pass_reserved_for_bayes_factor_k_gt_100"] is True
    assert second["schema"] == CAMPAIGN_SCHEMA


def test_default_run_does_not_write_sidecar(tmp_path, monkeypatch):
    import scripts.run_disorder_averaged_collective_modes as campaign

    monkeypatch.setattr(campaign, "_evaluate", _fake_evaluate)
    run(_parse_run_args(tmp_path, write_run_record=False))
    assert (tmp_path / CAMPAIGN_FILENAME).is_file()
    assert not (tmp_path / RUN_RECORD_SIDECAR_FILENAME).exists()
    payload = json.loads((tmp_path / CAMPAIGN_FILENAME).read_text(encoding="utf-8"))
    assert payload["schema"] == CAMPAIGN_SCHEMA
    _assert_campaign_omits_sidecar_flag(payload)


def test_sidecar_matches_contract_stub(tmp_path):
    contract = json.loads(_CONTRACT_PATH.read_text(encoding="utf-8"))
    payload = _fixture_payload(finite=True)
    campaign = tmp_path / CAMPAIGN_FILENAME
    campaign.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    dumped = sidecar_to_dict(build_run_record_sidecar(payload, campaign))
    for key in contract["required_top_level_keys"]:
        assert key in dumped
    for key in contract["required_artifact_keys"]:
        assert key in dumped["artifacts"]
    assert dumped["schema_version"] == contract["sidecar_schema_version"]
    assert dumped["run_kind"] == contract["run_kind"]
    assert dumped["verdict"] in contract["allowed_verdicts"]
    assert dumped["verdict"] not in contract["forbidden_verdicts"]
    identity_includes = " ".join(contract["identity"]["includes"])
    assert "n_summaries" in identity_includes
    assert "n_pre_registered_effect_candidate" in identity_includes
    assert "n_pre_registered_not_supported" in identity_includes
    assert "n_summaries" in dumped["metrics"]


def test_campaign_and_sidecar_sources_have_no_network_calls():
    source = (_REPO_ROOT / "scripts" / "run_disorder_averaged_collective_modes.py").read_text(encoding="utf-8")
    for banned in _BANNED_NETWORK:
        assert banned not in source
