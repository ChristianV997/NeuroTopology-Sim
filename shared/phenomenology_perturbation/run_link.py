"""Minimal link helpers onto the existing RunRecord provenance spine.

Does **not** replace ``RunRecordV1``, ``TransitionRecordV1``, research-cycle
ledger types, or (when present) Gemini C5 sidecars. Produces additive artifact
pointers and parent-id equality checks only.
"""

from __future__ import annotations

from typing import Any, Mapping, MutableMapping, Optional

from .paths import safe_relative_path
from .record import PhenomenologyValidationError
from .schema import SCHEMA

# Stable key for RunRecordV1.artifacts / TransitionRecordV1.artifact_paths.
RUN_ARTIFACT_KEY = "phenomenology_perturbation_record"
TRANSITION_ARTIFACT_KEY = "phenomenology_perturbation"


def pointer_for_run_artifacts(record_relpath: str) -> dict[str, str]:
    """Return a one-key dict suitable for merging into ``RunRecordV1.artifacts``."""
    return {RUN_ARTIFACT_KEY: safe_relative_path(record_relpath)}


def pointer_for_transition_artifact_paths(record_relpath: str) -> dict[str, str]:
    """Return a one-key dict for ``TransitionRecordV1.artifact_paths`` (optional)."""
    return {TRANSITION_ARTIFACT_KEY: safe_relative_path(record_relpath)}


def merge_run_artifact_pointer(
    artifacts: Optional[Mapping[str, str]],
    record_relpath: str,
) -> dict[str, str]:
    """Copy ``artifacts`` and attach the domain-record pointer (non-mutating)."""
    out = dict(artifacts or {})
    out.update(pointer_for_run_artifacts(record_relpath))
    return out


def assert_parent_run_id_matches(
    domain_record: Mapping[str, Any],
    run_record: Mapping[str, Any],
) -> None:
    """Require ``parent_run_id`` equality with ``run_id`` when both are present.

    This is a *recorded link*, not byte verification of the parent RunRecord,
    not reproducibility of the computation, and not authenticity of authorship.
    """
    if domain_record.get("schema") != SCHEMA:
        raise PhenomenologyValidationError(
            f"run_link: domain schema mismatch (expected {SCHEMA!r})"
        )
    parent = domain_record.get("parent_run_id")
    run_id = run_record.get("run_id")
    if parent is None:
        raise PhenomenologyValidationError(
            "run_link: domain record has no parent_run_id to bind"
        )
    if not isinstance(run_id, str) or not run_id:
        raise PhenomenologyValidationError("run_link: run_record.run_id missing")
    if parent != run_id:
        raise PhenomenologyValidationError(
            f"run_link: parent_run_id {parent!r} != run_id {run_id!r}"
        )


def attach_pointer_into_run_dict(
    run_record: MutableMapping[str, Any],
    record_relpath: str,
) -> MutableMapping[str, Any]:
    """Attach pointer under ``artifacts`` on a *mutable* run dict (in place).

    Prefer ``merge_run_artifact_pointer`` when callers want a pure copy.
    """
    arts = run_record.get("artifacts")
    if arts is None:
        arts = {}
        run_record["artifacts"] = arts
    if not isinstance(arts, MutableMapping):
        raise PhenomenologyValidationError("run_link: run_record.artifacts must be a mapping")
    arts.update(pointer_for_run_artifacts(record_relpath))
    return run_record


def provenance_layer_map() -> dict[str, str]:
    """Static responsibility map for reviewers (not a second run-record system)."""
    return {
        "generic_run_provenance": "runs.RunRecordV1 (run_id, git, argv, metrics, artifact paths)",
        "transition_context": (
            "transitions.TransitionRecordV1 "
            "(time_axis/intervention/preprocessing_provenance as general dicts; "
            "optional artifact_paths pointer)"
        ),
        "research_cycle_ledger": (
            "tools.research_cycle HypothesisRecord / ExperimentPlan / EvidenceUpdate "
            "(claim lifecycle — not trial phenomenology)"
        ),
        "domain_trial_payload": SCHEMA,
        "parent_child_link": "PhenomenologyPerturbationRecord.parent_run_id == RunRecordV1.run_id",
        "stored_digest": "integrity.path_sha256 (record_only) — integrity candidate only",
        "byte_verification": "integrity.mode=verify_paths + verify_root — still not authenticity",
        "reproducibility": "out of scope here (requires code+config+inputs re-execution)",
        "authenticity_of_authorship": "not established by digests",
        "scientific_validity": "not established by schema compliance",
        "gemini_c5_sidecar": "absent on this host; not required for this additive link",
    }
