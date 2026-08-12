"""Tests for `benchmark_packs.verification`: schema roundtrip/determinism
and `verify_benchmark_pack` behavior. Real already-committed contract
artifacts only -- no downloads, no job execution during verification."""
from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path

import pytest

from benchmark_packs.builder import build_benchmark_pack, make_builtin_demo_pack_spec
from benchmark_packs.pack_spec import BenchmarkPackSpecV1
from benchmark_packs.verification import (
    BenchmarkPackVerificationV1,
    compute_verification_id,
    verify_benchmark_pack,
)
from workflows.report_pipeline import ReportPipelineSpecV1

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SEED_REGISTRY = _REPO_ROOT / "benchmarks" / "registry_seed.json"
_DS005620_SOURCE = _REPO_ROOT / "contracts" / "btc_icft" / "ds005620" / "pitnn_cohort"


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    shutil.rmtree(_REPO_ROOT / "outputs" / "benchmark_packs", ignore_errors=True)
    shutil.rmtree(_REPO_ROOT / "outputs" / "jobs", ignore_errors=True)
    shutil.rmtree(_REPO_ROOT / "outputs" / "report_packs", ignore_errors=True)


def _valid_verification(**overrides):
    kwargs = dict(
        benchmark_pack_id="pack1", source_pack_path="outputs/benchmark_packs/x/BenchmarkPack.json",
        limitations=["test verification"], provenance="test",
        _now=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    kwargs.update(overrides)
    return BenchmarkPackVerificationV1.make(**kwargs)


# -- schema --


def test_to_dict_from_dict_roundtrip():
    v = _valid_verification(files_checked=["a.json"], errors=[])
    restored = BenchmarkPackVerificationV1.from_dict(v.to_dict())
    assert restored == v


def test_to_json_from_json_roundtrip():
    v = _valid_verification()
    restored = BenchmarkPackVerificationV1.from_json(v.to_json())
    assert restored == v


def test_verification_id_stable_for_identical_inputs():
    ts = datetime(2026, 1, 1, tzinfo=timezone.utc)
    a = _valid_verification(_now=ts)
    b = _valid_verification(_now=ts)
    assert a.verification_id == b.verification_id


def test_verification_id_changes_with_files_checked():
    a = _valid_verification(files_checked=["a.json"])
    b = _valid_verification(files_checked=["b.json"])
    assert a.verification_id != b.verification_id


def test_compute_verification_id_is_pure_and_deterministic():
    first = compute_verification_id(benchmark_pack_id="p1", source_pack_path="x.json", files_checked=["a.json"])
    second = compute_verification_id(benchmark_pack_id="p1", source_pack_path="x.json", files_checked=["a.json"])
    assert first == second
    assert len(first) == 16


def test_valid_verification_has_no_errors():
    v = _valid_verification()
    assert v.validate() == []
    v.validate_or_raise()


def test_empty_limitations_is_invalid():
    v = _valid_verification(limitations=[])
    errors = v.validate()
    assert any("limitations" in e for e in errors)


def test_empty_provenance_is_invalid():
    v = _valid_verification(provenance="")
    errors = v.validate()
    assert any("provenance" in e for e in errors)


def test_passed_status_requires_no_errors():
    v = _valid_verification(verification_status="passed", errors=["boom"])
    errors = v.validate()
    assert any("passed verification" in e for e in errors)


def test_failed_status_requires_errors():
    v = _valid_verification(verification_status="failed", errors=[])
    errors = v.validate()
    assert any("failed verification" in e for e in errors)


def test_passed_with_warnings_records_warnings():
    v = _valid_verification(verification_status="passed_with_warnings", warnings=["missing optional artifact"])
    assert v.validate() == []
    assert v.warnings


# -- behavior --


def _good_spec_dict(name: str) -> dict:
    return ReportPipelineSpecV1.make(
        input_mode="builtin_ds005620_cohort_summary", dataset_id="ds005620", modality="EEG",
        output_root=f"outputs/benchmark_packs/verify-test-{name}/reports/good",
        source_paths=[str(_DS005620_SOURCE)], registry_path=str(_SEED_REGISTRY), include_report=True,
        limitations=["verify test"], provenance="verify test",
    ).to_dict()


def test_valid_generated_benchmark_pack_verifies():
    spec = make_builtin_demo_pack_spec(output_root="outputs/benchmark_packs/verify-happy", include_html=True, run_immediately=True)
    build_benchmark_pack(spec)

    v = verify_benchmark_pack("outputs/benchmark_packs/verify-happy/BenchmarkPack.json")
    assert v.verification_status == "passed"
    assert v.errors == []
    assert v.artifact_link_status == "passed"
    assert v.guardrail_status == "passed"


def test_missing_report_pack_path_fails_strict_verification():
    spec = BenchmarkPackSpecV1.make(
        pack_name="missing-rp", output_root="outputs/benchmark_packs/verify-missing-rp",
        pipeline_specs=[_good_spec_dict("missing-rp")], run_immediately=True,
        limitations=["verify test"], provenance="verify test",
    )
    pack = build_benchmark_pack(spec)
    victim = Path(pack.generated_report_pack_paths[0])
    if not victim.is_absolute():
        victim = _REPO_ROOT / victim
    victim.unlink()

    v = verify_benchmark_pack("outputs/benchmark_packs/verify-missing-rp/BenchmarkPack.json")
    assert v.verification_status == "failed"
    assert any("missing generated_report_pack_path" in e for e in v.errors)


def test_missing_optional_html_path_warns_in_non_strict_mode():
    spec = BenchmarkPackSpecV1.make(
        pack_name="missing-html", output_root="outputs/benchmark_packs/verify-missing-html",
        pipeline_specs=[_good_spec_dict("missing-html")], requested_outputs=["report_pack", "html_report_pack"],
        include_html=True, run_immediately=True, limitations=["verify test"], provenance="verify test",
    )
    pack = build_benchmark_pack(spec)
    victim = Path(pack.generated_html_paths[0])
    if not victim.is_absolute():
        victim = _REPO_ROOT / victim
    victim.unlink()

    v_strict = verify_benchmark_pack("outputs/benchmark_packs/verify-missing-html/BenchmarkPack.json", strict=True)
    assert v_strict.verification_status == "failed"

    v_non_strict = verify_benchmark_pack("outputs/benchmark_packs/verify-missing-html/BenchmarkPack.json", strict=False)
    assert v_non_strict.verification_status == "passed_with_warnings"
    assert any("missing generated_html_path" in w for w in v_non_strict.warnings)


def test_id_mismatch_fails():
    import json

    spec = BenchmarkPackSpecV1.make(
        pack_name="id-mismatch", output_root="outputs/benchmark_packs/verify-id-mismatch",
        pipeline_specs=[_good_spec_dict("id-mismatch")], run_immediately=True,
        limitations=["verify test"], provenance="verify test",
    )
    build_benchmark_pack(spec)
    pack_path = _REPO_ROOT / "outputs/benchmark_packs/verify-id-mismatch/BenchmarkPack.json"
    doc = json.loads(pack_path.read_text(encoding="utf-8"))
    doc["report_pack_ids"] = ["tampered_id_not_real"]
    pack_path.write_text(json.dumps(doc), encoding="utf-8")

    v = verify_benchmark_pack(str(pack_path))
    assert v.verification_status == "failed"
    assert v.ids_failed


def test_raw_data_path_in_generated_files_fails(monkeypatch):
    spec = BenchmarkPackSpecV1.make(
        pack_name="raw-data", output_root="outputs/benchmark_packs/verify-raw-data",
        pipeline_specs=[_good_spec_dict("raw-data")], run_immediately=True,
        limitations=["verify test"], provenance="verify test",
    )
    pack = build_benchmark_pack(spec)

    import json
    rp_path = _REPO_ROOT / pack.generated_report_pack_paths[0]
    doc = json.loads(rp_path.read_text(encoding="utf-8"))
    doc["generated_files"].append("data/raw/ds005620/sub-01/eeg/sub-01_eeg.edf")
    rp_path.write_text(json.dumps(doc), encoding="utf-8")

    v = verify_benchmark_pack("outputs/benchmark_packs/verify-raw-data/BenchmarkPack.json")
    assert v.verification_status == "failed"
    assert v.raw_data_copy_status == "failed"


def test_claim_scope_at_pack_level_fails():
    """`BenchmarkPackV1.from_dict` only reads its fixed named fields, so a
    `claim_scope` key injected into the JSON file can never survive a
    reload -- the dataclass schema itself structurally prevents that
    injection path. What `validate_benchmark_pack` guards against is a
    caller directly attaching the attribute to an in-memory object (e.g.
    a future code change that adds the field), which is the reachable
    case this test exercises via `benchmark_pack.validate()` directly."""
    spec = BenchmarkPackSpecV1.make(
        pack_name="claim-scope", output_root="outputs/benchmark_packs/verify-claim-scope",
        pipeline_specs=[_good_spec_dict("claim-scope")], run_immediately=True,
        limitations=["verify test"], provenance="verify test",
    )
    pack = build_benchmark_pack(spec)
    pack.claim_scope = "definitive"  # simulates a future accidental field addition

    errors = pack.validate()
    assert any("claim_scope" in e for e in errors)


def test_guardrail_unsafe_text_fails():
    import json

    spec = BenchmarkPackSpecV1.make(
        pack_name="guardrail-fail", output_root="outputs/benchmark_packs/verify-guardrail",
        pipeline_specs=[_good_spec_dict("guardrail-fail")], run_immediately=True,
        limitations=["verify test"], provenance="verify test",
    )
    build_benchmark_pack(spec)
    pack_path = _REPO_ROOT / "outputs/benchmark_packs/verify-guardrail/BenchmarkPack.json"
    doc = json.loads(pack_path.read_text(encoding="utf-8"))
    doc["pack_purpose"] = "this run confirms diagnosis beyond doubt"
    pack_path.write_text(json.dumps(doc), encoding="utf-8")

    v = verify_benchmark_pack(str(pack_path))
    assert v.verification_status == "failed"
    assert v.guardrail_status == "failed"


def test_verify_benchmark_pack_never_touches_seed_registries_or_jobs():
    """Source-guard: verification must orchestrate no execution -- never
    call run_pipeline_job / batch execution, never mutate a registry."""
    src = (_REPO_ROOT / "benchmark_packs" / "verification.py").read_text(encoding="utf-8")
    assert "run_pipeline_job(" not in src
    assert "run_batch(" not in src
    assert "registry.save(" not in src
    assert "SeedRegistry(" not in src


def test_verify_missing_pack_file_returns_failed():
    v = verify_benchmark_pack("outputs/benchmark_packs/does-not-exist/BenchmarkPack.json")
    assert v.verification_status == "failed"
    assert v.errors
