"""EvidenceBundleV1/EvidenceReportV1 integration + guardrail checks for
`adapters.mne_bids`. Synthetic miniature fixtures only.
"""
from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

from adapters.mne_bids import export_mne_bids_derived_transitions
from adapters.mne_bids_contract import AdapterEligibility, check_adapter_eligible

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SEED_REGISTRY = _REPO_ROOT / "benchmarks" / "registry_seed.json"


def _write_features_and_mapping(tmp_path: Path, dataset_id: str) -> tuple[Path, Path]:
    features = tmp_path / "features.csv"
    with features.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["subject_id", "source_state", "target_state", "feature_name", "source_value", "target_value", "feature_definition"])
        w.writerow(["sub-01", "awake", "sedated", "spectral.alpha_power", "1.5", "0.8", "Welch PSD alpha 8-12Hz mean power"])
        w.writerow(["sub-01", "awake", "sedated", "connectivity.mean_plv", "0.6", "0.3", "Mean pairwise PLV, 19-channel montage"])
        w.writerow(["sub-02", "awake", "sedated", "spectral.alpha_power", "1.2", "0.9", "Welch PSD alpha 8-12Hz mean power"])
        w.writerow(["sub-02", "awake", "sedated", "connectivity.mean_plv", "0.55", "0.35", "Mean pairwise PLV, 19-channel montage"])
    mapping = tmp_path / "mapping.json"
    mapping.write_text(json.dumps({
        "format": "long", "dataset_id": dataset_id, "modality": "EEG",
        "preprocessing_provenance": {"pipeline": "mne bandpass+notch+CAR", "source_tool_version": "mne==1.x"},
    }), encoding="utf-8")
    return features, mapping


# ── adapter contract / external-tool eligibility ─────────────────────────


def test_adapter_is_eligible_against_committed_registries():
    eligibility = check_adapter_eligible()
    assert isinstance(eligibility, AdapterEligibility)
    assert eligibility.tool.tool_id == "mne-bids"


def test_adapter_contract_output_targets_include_full_chain():
    eligibility = check_adapter_eligible()
    for target in ("DatasetRecordV1", "ArtifactRecordV1", "TransitionRecordV1", "EvidenceBundleV1", "EvidenceReportV1"):
        assert target in eligibility.contract.output_targets


def test_adapter_contract_validates_cleanly():
    eligibility = check_adapter_eligible()
    assert eligibility.contract.validate() == []
    assert eligibility.tool.validate() == []


def test_adapter_contract_claim_scope_capped_at_exploratory_metric():
    eligibility = check_adapter_eligible()
    assert eligibility.contract.allowed_claim_scope_ceiling == "exploratory_metric"


# ── evidence bundle / report integration ─────────────────────────────────


def test_include_evidence_bundle_produces_valid_bundle(tmp_path):
    features, mapping = _write_features_and_mapping(tmp_path, "integration_test_ds_1")
    out = tmp_path / "out"
    result = export_mne_bids_derived_transitions(
        features, mapping, out, registry_path=_SEED_REGISTRY,
        include_evidence_bundle=True, updated_registry_out=out / "reg.json",
    )
    bundle = result["evidence_bundle"]
    assert bundle is not None
    assert bundle.validate() == []
    assert (out / "EvidenceBundle.json").exists()


def test_include_report_produces_markdown_and_json(tmp_path):
    features, mapping = _write_features_and_mapping(tmp_path, "integration_test_ds_2")
    out = tmp_path / "out"
    result = export_mne_bids_derived_transitions(
        features, mapping, out, registry_path=_SEED_REGISTRY,
        include_evidence_bundle=True, include_report=True, updated_registry_out=out / "reg.json",
    )
    assert result["report"] is not None
    assert (out / "EvidenceReport.md").exists()
    assert (out / "EvidenceReport.json").exists()
    md = (out / "EvidenceReport.md").read_text(encoding="utf-8")
    assert "## Executive Summary" in md


def test_include_report_without_evidence_bundle_reports_unsupported(tmp_path):
    """Mission Phase E: if a flag combination the adapter cannot support is
    requested, the CLI must explicitly report it rather than silently
    ignoring the flag."""
    features, mapping = _write_features_and_mapping(tmp_path, "integration_test_ds_3")
    out = tmp_path / "out"
    result = subprocess.run(
        [sys.executable, "-m", "adapters.mne_bids",
         "--features", str(features), "--mapping", str(mapping), "--out", str(out),
         "--registry", str(_SEED_REGISTRY), "--updated-registry-out", str(out / "reg.json"),
         "--include-report"],
        capture_output=True, text=True, cwd=str(_REPO_ROOT),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["report"] == "not built (requires --include-evidence-bundle)"
    assert not (out / "EvidenceReport.md").exists()


def test_evidence_bundle_does_not_promote_claim_scope(tmp_path):
    features, mapping = _write_features_and_mapping(tmp_path, "integration_test_ds_4")
    out = tmp_path / "out"
    result = export_mne_bids_derived_transitions(
        features, mapping, out, registry_path=_SEED_REGISTRY,
        include_evidence_bundle=True, updated_registry_out=out / "reg.json",
    )
    bundle = result["evidence_bundle"]
    assert bundle.claim_scope_ceiling == "exploratory_metric"
    assert bundle.generated_claim_scope == "exploratory_metric"


def test_evidence_bundle_null_control_honest_not_provided(tmp_path):
    features, mapping = _write_features_and_mapping(tmp_path, "integration_test_ds_5")
    out = tmp_path / "out"
    result = export_mne_bids_derived_transitions(
        features, mapping, out, registry_path=_SEED_REGISTRY,
        include_evidence_bundle=True, updated_registry_out=out / "reg.json",
    )
    assert result["evidence_bundle"].null_control_summary["status"] == "not_provided"


def test_evidence_bundle_with_phase_space_end_to_end(tmp_path):
    features, mapping = _write_features_and_mapping(tmp_path, "integration_test_ds_6")
    out = tmp_path / "out"
    result = export_mne_bids_derived_transitions(
        features, mapping, out, registry_path=_SEED_REGISTRY,
        include_phase_space=True, include_evidence_bundle=True, include_report=True,
        updated_registry_out=out / "reg.json",
    )
    bundle = result["evidence_bundle"]
    assert bundle.validate() == []
    assert bundle.phase_space_coordinate_ids
    assert result["report"] is not None


# ── guardrails ─────────────────────────────────────────────────────────


def test_no_forbidden_overclaim_language_in_adapter_source():
    result = subprocess.run(
        [sys.executable, "tools/check_claim_guardrails.py",
         "adapters/", "external_tools/adapter_contract.py", "external_tools/adapter_contracts_seed.json",
         "evidence/builder.py"],
        capture_output=True, text=True, cwd=str(_REPO_ROOT),
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_generated_transition_report_passes_guardrail_scan(tmp_path):
    features, mapping = _write_features_and_mapping(tmp_path, "integration_test_ds_7")
    out = tmp_path / "out"
    export_mne_bids_derived_transitions(
        features, mapping, out, registry_path=_SEED_REGISTRY,
        include_evidence_bundle=True, include_report=True, updated_registry_out=out / "reg.json",
    )
    result = subprocess.run(
        [sys.executable, "tools/check_claim_guardrails.py", str(out / "EvidenceReport.md"), str(out / "EvidenceReport.json")],
        capture_output=True, text=True, cwd=str(_REPO_ROOT),
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_transition_records_carry_no_clinical_diagnostic_language(tmp_path):
    features, mapping = _write_features_and_mapping(tmp_path, "integration_test_ds_8")
    out = tmp_path / "out"
    result = export_mne_bids_derived_transitions(
        features, mapping, out, registry_path=_SEED_REGISTRY, updated_registry_out=out / "reg.json",
    )
    banned_substrings = ("clinical", "diagnos", "treatment", "biomarker", "consciousness_detect", "jhana", "cessation", "enlightenment")
    for record in result["records"]:
        text = json.dumps(record.to_dict()).lower()
        for token in banned_substrings:
            assert token not in text, f"found banned token '{token}' in transition record"
