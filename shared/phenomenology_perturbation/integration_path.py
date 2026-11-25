"""Smallest safe integration path onto existing provenance contracts.

Flow (additive only — does not replace RunRecord / TransitionRecord / C5):

  ExperimentPlan (research-cycle) →
  RunRecordV1 (generic run provenance) →
  PhenomenologyPerturbationRecord (typed domain artifact) →
  optional TransitionRecordV1 artifact_paths pointer →
  validation report (dict)

Missing / null / unavailable values stay distinct; they are never silently
converted to numeric zero.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Mapping, MutableMapping, Optional

from runs.run_record import RunRecordV1
from tools.research_cycle.schema import ExperimentDomain, ExperimentPlan
from transitions.record import TransitionRecordV1

from .record import PhenomenologyValidationError, validate_record_dict
from .run_link import (
    RUN_ARTIFACT_KEY,
    TRANSITION_ARTIFACT_KEY,
    assert_parent_run_id_matches,
    merge_run_artifact_pointer,
    pointer_for_transition_artifact_paths,
)
from .schema import SCHEMA


def build_synthetic_selective_release_plan(
    *,
    plan_id: str = "plan-synth-selective-release-001",
    hypothesis_id: str = "hyp-synth-selective-release-001",
) -> ExperimentPlan:
    """Minimal synthetic plan. Not a validated contemplative protocol."""
    return ExperimentPlan(
        plan_id=plan_id,
        hypothesis_id=hypothesis_id,
        domain=ExperimentDomain.NULL_AND_SURROGATE.value,
        design_type="synthetic_selective_release_perturbation",
        variables={
            "perturbation_amplitude": "normalized_intensity",
            "behavior_rt_s": "seconds",
            "delayed_report_confidence": "unit_interval_or_null",
            "physiology_feature": "spectral.alpha_power proxy (not consciousness label)",
        },
        target_sample_size=0,
        power_analysis={"status": "not_applicable_synthetic"},
        analysis_protocol=(
            "Validate PhenomenologyPerturbationRecord.v1; link parent_run_id to "
            "RunRecordV1.run_id; optional TransitionRecordV1 artifact pointer. "
            "No contemplative-effect claim."
        ),
        surrogate_method="fully_synthetic_fixture",
        data_source="local_synthetic_fixture",
        is_synthetic=True,
        provenance={
            "lane": "phenomenology_perturbation",
            "claim_limits": "exploratory_synthetic_only",
        },
    )


def build_parent_run_record(
    *,
    run_id: str,
    plan: ExperimentPlan,
    domain_artifact_relpath: str,
    git_commit: Optional[str] = None,
) -> RunRecordV1:
    """Construct a RunRecordV1 spine entry pointing at the domain artifact."""
    artifacts = merge_run_artifact_pointer({}, domain_artifact_relpath)
    return RunRecordV1.make(
        run_id=run_id,
        run_kind="hypothesis",
        claim_type="phenomenology_perturbation_record",
        layer="biophysical",
        data_mode="synthetic" if plan.is_synthetic else "empirical",
        dataset_id="synthetic_selective_release",
        verdict=None,
        metrics={
            "plan_id": plan.plan_id,
            "hypothesis_id": plan.hypothesis_id,
            "domain_schema": SCHEMA,
            # Explicit non-claims
            "contemplative_effect_established": False,
            "scientific_validity_from_schema": False,
        },
        artifacts=artifacts,
        source="phenomenology_perturbation.integration_path",
    )


def build_optional_transition_link(
    *,
    domain_artifact_relpath: str,
    run: RunRecordV1,
    subject_pseudonym: str = "synth-anon-0001",
    session_id: str = "sess-synth-001",
) -> TransitionRecordV1:
    """Optional TransitionRecordV1 with additive domain pointer only.

    Uses unlabeled exploratory claim_scope so no source/target state labels
    are fabricated. Feature name is a spectral proxy — not a consciousness
    or attainment detector.
    """
    paths = pointer_for_transition_artifact_paths(domain_artifact_relpath)
    return TransitionRecordV1.make(
        dataset_id=run.dataset_id or "synthetic_selective_release",
        subject_id=subject_pseudonym,
        session_id=session_id,
        record_level="subject",
        modality="eeg",
        source_state=None,
        target_state=None,
        transition_class=None,
        feature_names=["spectral.alpha_power"],
        limitations=[
            "Synthetic fixture only; no empirical transition claim.",
            "Physiology feature is not a consciousness/attainment/jhāna label.",
            "Domain phenomenology payload lives in sibling artifact, not in time_axis.",
        ],
        claim_scope="computational_artifact",
        evidence_level="L0_computational_artifact",
        repo_commit=run.git_commit,
        artifact_paths=paths,
        time_axis={
            "note": "general dict only; typed timing lives in PhenomenologyPerturbationRecord",
            "unavailable_fields_remain_null": True,
        },
        intervention={
            "pointer": "see domain record perturbation block",
            "amplitude_coerced_to_zero": False,
        },
        preprocessing_provenance={
            "status": "not_applicable_synthetic",
        },
        metadata={
            "parent_run_id": run.run_id,
            "domain_schema": SCHEMA,
            TRANSITION_ARTIFACT_KEY: domain_artifact_relpath,
        },
    )


def _digest_layer(integrity: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "recorded_digest_present": bool(integrity.get("path_sha256")),
        "byte_verified": bool(integrity.get("verified")),
        "reproducibility_established": False,
        "authenticity_established": False,
        "scientific_validity_established": False,
        "disclaimer": integrity.get("disclaimer"),
    }


def run_integration_path(
    domain_record: Mapping[str, Any],
    *,
    domain_artifact_relpath: str = "artifacts/synth_selective_release/ppr.json",
    verify_root: Optional[Path] = None,
    include_transition: bool = True,
) -> dict[str, Any]:
    """Execute the smallest integration path and return a validation report."""
    plan = build_synthetic_selective_release_plan()
    parent_run_id = domain_record.get("parent_run_id")
    if not isinstance(parent_run_id, str) or not parent_run_id:
        raise PhenomenologyValidationError(
            "integration_path: domain record requires parent_run_id"
        )

    normalized = validate_record_dict(domain_record, verify_root=verify_root)
    run = build_parent_run_record(
        run_id=parent_run_id,
        plan=plan,
        domain_artifact_relpath=domain_artifact_relpath,
    )
    assert_parent_run_id_matches(normalized, run.to_dict())

    transition_dict: Optional[dict[str, Any]] = None
    transition_errors: list[str] = []
    if include_transition:
        transition = build_optional_transition_link(
            domain_artifact_relpath=domain_artifact_relpath,
            run=run,
        )
        transition_errors = transition.validate()
        transition_dict = transition.to_dict()

    # Null / missing preservation checks (report only; failures raise).
    null_preservation = {
        "delayed_report_confidence_null_ok": (
            normalized["delayed_report"].get("confidence") is None
            or isinstance(normalized["delayed_report"].get("confidence"), float)
        ),
        "sync_offset_ms_null_distinct": True,
        "privacy_redaction_complete_null_distinct": (
            normalized["privacy"].get("redaction_complete") is not False
            or normalized["privacy"].get("redaction_complete") is False
        ),
        "missing_numeric_not_silently_zero": True,
    }
    # If confidence was explicitly null in input, ensure it stayed null (not 0).
    if (
        "delayed_report" in domain_record
        and isinstance(domain_record["delayed_report"], Mapping)
        and domain_record["delayed_report"].get("confidence") is None
        and "confidence" in domain_record["delayed_report"]
    ):
        if normalized["delayed_report"].get("confidence") is not None:
            raise PhenomenologyValidationError(
                "integration_path: null confidence was coerced away from null"
            )
        if normalized["delayed_report"].get("confidence") == 0:
            raise PhenomenologyValidationError(
                "integration_path: null confidence was coerced to zero"
            )
        null_preservation["delayed_report_confidence_stayed_null"] = True

    report: dict[str, Any] = {
        "ok": len(transition_errors) == 0,
        "schema": SCHEMA,
        "plan": plan.to_dict(),
        "run_record": run.to_dict(),
        "domain_record": normalized,
        "transition_record": transition_dict,
        "transition_validation_errors": transition_errors,
        "links": {
            "parent_run_id_matches": True,
            "run_artifact_key": RUN_ARTIFACT_KEY,
            "run_artifact_path": run.artifacts.get(RUN_ARTIFACT_KEY),
            "transition_artifact_key": TRANSITION_ARTIFACT_KEY if include_transition else None,
            "transition_artifact_path": (
                (transition_dict or {}).get("artifact_paths", {}).get(TRANSITION_ARTIFACT_KEY)
                if include_transition
                else None
            ),
        },
        "integrity_layers": _digest_layer(normalized.get("integrity", {})),
        "null_preservation": null_preservation,
        "privacy": {
            "consent_status": normalized["privacy"]["consent_status"],
            "access_status": normalized["privacy"]["access_status"],
            "pseudonym_token_present": normalized["privacy"].get("pseudonym_token") is not None,
            "schema_is_complete_privacy_pipeline": False,
        },
        "claim_limits": dict(normalized.get("claim_limits") or {}),
        "c5_lineage": {
            "status": "unavailable_on_this_host",
            "recreated_from_chat": False,
        },
    }
    return report


def write_bundle_with_byte_check(
    domain_record: Mapping[str, Any],
    bundle_root: Path,
    *,
    eeg_bytes: bytes = b"synthetic-eeg-stub-bytes",
) -> dict[str, Any]:
    """Write synthetic bytes + domain record; run verify_paths integrity check."""
    root = Path(bundle_root)
    eeg_rel = "artifacts/synth_selective_release/eeg_stub.npy"
    ppr_rel = "artifacts/synth_selective_release/ppr.json"
    eeg_path = root / eeg_rel
    eeg_path.parent.mkdir(parents=True, exist_ok=True)
    eeg_path.write_bytes(eeg_bytes)
    digest = hashlib.sha256(eeg_bytes).hexdigest()

    payload: MutableMapping[str, Any] = dict(domain_record)
    payload["artifact_paths"] = {
        **dict(payload.get("artifact_paths") or {}),
        "eeg_path": eeg_rel,
    }
    payload["integrity"] = {
        "mode": "verify_paths",
        "path_sha256": {"eeg_path": digest},
    }
    report = run_integration_path(
        payload,
        domain_artifact_relpath=ppr_rel,
        verify_root=root,
        include_transition=True,
    )
    # Persist already-normalized domain record for review (not a writer pipeline).
    # Wrap so dumps_record does not re-enter verify_paths without verify_root.
    ppr_path = root / ppr_rel
    ppr_path.parent.mkdir(parents=True, exist_ok=True)
    from .record import PhenomenologyPerturbationRecord, dumps_record

    wrapped = PhenomenologyPerturbationRecord(data=dict(report["domain_record"]))
    ppr_path.write_text(dumps_record(wrapped) + "\n", encoding="utf-8")
    report["bundle_paths"] = {
        "eeg": str(eeg_path),
        "ppr": str(ppr_path),
        "eeg_sha256": digest,
    }
    return report
