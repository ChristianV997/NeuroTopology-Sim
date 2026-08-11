"""EvidenceBundleV1/EvidenceReportV1 integration + guardrail checks for
`adapters.fmri_derivatives`. Synthetic miniature fixtures only.
"""
from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

from adapters.fmri_derivatives import export_fmri_derivative_transitions
from adapters.fmri_derivatives_contract import AdapterEligibility, check_adapter_eligible

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SEED_REGISTRY = _REPO_ROOT / "benchmarks" / "registry_seed.json"


def _write_features_and_mapping(tmp_path: Path, dataset_id: str) -> tuple[Path, Path]:
    features = tmp_path / "features.csv"
    with features.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["subject_id", "source_state", "target_state", "feature_name", "source_value", "target_value", "feature_definition", "atlas_or_parcellation"])
        w.writerow(["sub-01", "placebo", "drug", "connectivity.global_efficiency", "0.34", "0.29", "Graph global efficiency over Schaefer100 connectome", "Schaefer100"])
        w.writerow(["sub-01", "placebo", "drug", "connectivity.modularity", "0.31", "0.40", "Louvain modularity Q", "Schaefer100"])
        w.writerow(["sub-02", "placebo", "drug", "connectivity.global_efficiency", "0.30", "0.25", "Graph global efficiency over Schaefer100 connectome", "Schaefer100"])
        w.writerow(["sub-02", "placebo", "drug", "connectivity.modularity", "0.33", "0.42", "Louvain modularity Q", "Schaefer100"])
    mapping = tmp_path / "mapping.json"
    mapping.write_text(json.dumps({
        "format": "long", "dataset_id": dataset_id, "modality": "fMRI",
        "preprocessing_provenance": {"pipeline": "fmriprep 23.x + nilearn ConnectivityMeasure", "source_tool_version": "fmriprep==23.1.0"},
        "confound_policy": "24-param + aCompCor, high-pass 0.01Hz",
    }), encoding="utf-8")
    return features, mapping


# ── adapter contract / external-tool eligibility ─────────────────────────


def test_adapter_is_eligible_against_committed_registries():
    eligibility = check_adapter_eligible()
    assert isinstance(eligibility, AdapterEligibility)
    assert eligibility.tool.tool_id == "nilearn"


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


def test_adapter_contract_distinct_from_mne_bids_adapter():
    eligibility = check_adapter_eligible()
    from adapters.mne_bids_contract import check_adapter_eligible as check_mne_bids_eligible

    mne_eligibility = check_mne_bids_eligible()
    assert eligibility.contract.adapter_id != mne_eligibility.contract.adapter_id
    assert eligibility.tool.tool_id != mne_eligibility.tool.tool_id


# ── evidence bundle / report integration ─────────────────────────────────


def test_include_evidence_bundle_produces_valid_bundle(tmp_path):
    features, mapping = _write_features_and_mapping(tmp_path, "fmri_integration_test_ds_1")
    out = tmp_path / "out"
    result = export_fmri_derivative_transitions(
        features, mapping, out, registry_path=_SEED_REGISTRY,
        include_evidence_bundle=True, updated_registry_out=out / "reg.json",
    )
    bundle = result["evidence_bundle"]
    assert bundle is not None
    assert bundle.validate() == []
    assert (out / "EvidenceBundle.json").exists()


def test_include_report_produces_markdown_and_json(tmp_path):
    features, mapping = _write_features_and_mapping(tmp_path, "fmri_integration_test_ds_2")
    out = tmp_path / "out"
    result = export_fmri_derivative_transitions(
        features, mapping, out, registry_path=_SEED_REGISTRY,
        include_evidence_bundle=True, include_report=True, updated_registry_out=out / "reg.json",
    )
    assert result["report"] is not None
    assert (out / "EvidenceReport.md").exists()
    assert (out / "EvidenceReport.json").exists()
    md = (out / "EvidenceReport.md").read_text(encoding="utf-8")
    assert "## Executive Summary" in md


def test_include_report_without_evidence_bundle_reports_unsupported(tmp_path):
    features, mapping = _write_features_and_mapping(tmp_path, "fmri_integration_test_ds_3")
    out = tmp_path / "out"
    result = subprocess.run(
        [sys.executable, "-m", "adapters.fmri_derivatives",
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
    features, mapping = _write_features_and_mapping(tmp_path, "fmri_integration_test_ds_4")
    out = tmp_path / "out"
    result = export_fmri_derivative_transitions(
        features, mapping, out, registry_path=_SEED_REGISTRY,
        include_evidence_bundle=True, updated_registry_out=out / "reg.json",
    )
    bundle = result["evidence_bundle"]
    assert bundle.claim_scope_ceiling == "exploratory_metric"
    assert bundle.generated_claim_scope == "exploratory_metric"


def test_evidence_bundle_null_control_honest_not_provided(tmp_path):
    features, mapping = _write_features_and_mapping(tmp_path, "fmri_integration_test_ds_5")
    out = tmp_path / "out"
    result = export_fmri_derivative_transitions(
        features, mapping, out, registry_path=_SEED_REGISTRY,
        include_evidence_bundle=True, updated_registry_out=out / "reg.json",
    )
    assert result["evidence_bundle"].null_control_summary["status"] == "not_provided"


def test_evidence_bundle_with_phase_space_end_to_end(tmp_path):
    features, mapping = _write_features_and_mapping(tmp_path, "fmri_integration_test_ds_6")
    out = tmp_path / "out"
    result = export_fmri_derivative_transitions(
        features, mapping, out, registry_path=_SEED_REGISTRY,
        include_phase_space=True, include_evidence_bundle=True, include_report=True,
        updated_registry_out=out / "reg.json",
    )
    bundle = result["evidence_bundle"]
    assert bundle.validate() == []
    assert bundle.phase_space_coordinate_ids
    assert result["report"] is not None


def test_evidence_bundle_from_graph_summary_with_cohort(tmp_path):
    summary = tmp_path / "graph_summary.json"
    summary.write_text(json.dumps({
        "format": "graph_summary", "dataset_id": "fmri_integration_test_ds_7", "modality": "fMRI",
        "atlas_or_parcellation": "Schaefer100", "source_state": "placebo", "target_state": "drug",
        "preprocessing_provenance": {"pipeline": "fmriprep+nilearn", "source_tool_version": "fmriprep==23.1.0"},
        "confound_policy": "24-param + aCompCor",
        "feature_definitions": {"connectivity.global_efficiency": "Graph global efficiency"},
        "subjects": [
            {"subject_id": "sub-01", "metrics": {"connectivity.global_efficiency": {"source_value": 0.34, "target_value": 0.29}}},
            {"subject_id": "sub-02", "metrics": {"connectivity.global_efficiency": {"source_value": 0.30, "target_value": 0.25}}},
        ],
        "cohort": {
            "subject_count": 20,
            "metrics": {"connectivity.global_efficiency": {"source_value": 0.33, "target_value": 0.30, "p_value": 0.01}},
        },
    }), encoding="utf-8")
    out = tmp_path / "out"
    result = export_fmri_derivative_transitions(
        summary, None, out, registry_path=_SEED_REGISTRY,
        include_evidence_bundle=True, updated_registry_out=out / "reg.json",
    )
    bundle = result["evidence_bundle"]
    assert bundle.validate() == []
    assert "L4_cross_subject_dataset_specific" in bundle.generated_evidence_levels
    assert "L2_single_subject_real_signal" in bundle.generated_evidence_levels


# ── guardrails ─────────────────────────────────────────────────────────


def test_no_forbidden_overclaim_language_in_adapter_source():
    result = subprocess.run(
        [sys.executable, "tools/check_claim_guardrails.py",
         "adapters/fmri_derivatives.py", "adapters/fmri_derivatives_contract.py",
         "adapters/fmri_derivatives_features.py", "adapters/fmri_derivatives_validation.py",
         "external_tools/adapter_contract.py", "external_tools/adapter_contracts_seed.json"],
        capture_output=True, text=True, cwd=str(_REPO_ROOT),
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_generated_transition_report_passes_guardrail_scan(tmp_path):
    features, mapping = _write_features_and_mapping(tmp_path, "fmri_integration_test_ds_8")
    out = tmp_path / "out"
    export_fmri_derivative_transitions(
        features, mapping, out, registry_path=_SEED_REGISTRY,
        include_evidence_bundle=True, include_report=True, updated_registry_out=out / "reg.json",
    )
    result = subprocess.run(
        [sys.executable, "tools/check_claim_guardrails.py", str(out / "EvidenceReport.md"), str(out / "EvidenceReport.json")],
        capture_output=True, text=True, cwd=str(_REPO_ROOT),
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_transition_records_carry_no_clinical_diagnostic_language(tmp_path):
    features, mapping = _write_features_and_mapping(tmp_path, "fmri_integration_test_ds_9")
    out = tmp_path / "out"
    result = export_fmri_derivative_transitions(
        features, mapping, out, registry_path=_SEED_REGISTRY, updated_registry_out=out / "reg.json",
    )
    banned_substrings = ("clinical", "diagnos", "treatment", "biomarker", "consciousness_detect", "jhana", "cessation", "enlightenment")
    for record in result["records"]:
        text = json.dumps(record.to_dict()).lower()
        for token in banned_substrings:
            assert token not in text, f"found banned token '{token}' in transition record"


def test_atlas_labels_not_treated_as_anatomy_beyond_provided_string(tmp_path):
    """Atlas/parcellation identity is stored verbatim, never expanded into
    an anatomical claim not present in the source metadata."""
    features, mapping = _write_features_and_mapping(tmp_path, "fmri_integration_test_ds_10")
    out = tmp_path / "out"
    result = export_fmri_derivative_transitions(
        features, mapping, out, registry_path=_SEED_REGISTRY, updated_registry_out=out / "reg.json",
    )
    for record in result["records"]:
        assert record.metadata["atlas_or_parcellation"] == "Schaefer100"
        limitations_text = " ".join(record.limitations).lower()
        assert "anatomically accurate" in limitations_text or "not independently validated" in limitations_text
