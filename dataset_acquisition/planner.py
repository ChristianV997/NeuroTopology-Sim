"""Turns a `DatasetCandidateRecordV1` into a `DatasetAcquisitionPlanV1` --
always dry-run by construction unless every safety flag is explicitly
supplied and nothing is blocked. Never invents a file size, never marks a
plan clean when license/access disqualifies it.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional, Union

from dataset_acquisition.acquisition_plan import DatasetAcquisitionPlanV1
from dataset_acquisition.store import validate_target_root
from dataset_acquisition.validation import (
    _DISQUALIFYING_ACCESS_STATUS,
    _DISQUALIFYING_LICENSE_RISK,
    _UNIMPLEMENTED_REMOTE_MODES,
)
from dataset_importers.candidate_record import DatasetCandidateRecordV1

_DEFAULT_MODE_BY_CATALOG: dict[str, str] = {
    "eegdash": "eegdash_metadata_query",
    "moabb": "moabb_planned_fetch",
    "openneuro_manual": "openneuro_external_cli_plan",
    "nemar_manual": "openneuro_external_cli_plan",
    "repo_manual": "local_bids_scan",
    "synthetic_fixture": "fixture_only",
}


class PlannerError(ValueError):
    """Raised when a candidate cannot be planned at all (e.g. it fails its
    own structural validation)."""


def choose_default_acquisition_mode(candidate: DatasetCandidateRecordV1) -> str:
    return _DEFAULT_MODE_BY_CATALOG.get(candidate.source_catalog, "manual_url_manifest")


def _planned_steps_for(requested_action: str, acquisition_mode: str, blocked: bool) -> list[str]:
    if requested_action == "metadata_only":
        return ["record candidate metadata into a plan only", "no local files created", "no network access"]
    if requested_action == "plan_download":
        return [
            "compute disk/size feasibility against disk_limit_bytes",
            "write a plan_download plan for a later --execute run",
            "no download performed by this step",
        ]
    if requested_action in ("scan_existing_local", "verify_existing_local"):
        return [f"{requested_action} against target_root", "no network access"]
    # execute_download
    if blocked:
        return ["blocked -- see blocked_reasons; no download performed"]
    if acquisition_mode in _UNIMPLEMENTED_REMOTE_MODES:
        return [
            f"acquisition_mode='{acquisition_mode}' has no implemented remote-fetch path in v1",
            "no download performed",
        ]
    return ["create target_root", "execute the local-only supported fetch path", "record a manifest"]


def make_acquisition_plan(
    candidate: DatasetCandidateRecordV1,
    *,
    target_root: str,
    requested_action: str = "metadata_only",
    disk_limit_bytes: Optional[int] = None,
    allow_network: bool = False,
    allow_raw_data: bool = False,
    acquisition_mode: Optional[str] = None,
    force_unknown_size: bool = False,
    explicit_execute_confirmed: bool = False,
) -> DatasetAcquisitionPlanV1:
    candidate_errors = candidate.validate()
    if candidate_errors:
        raise PlannerError(f"candidate '{candidate.candidate_id}' fails its own validation: {'; '.join(candidate_errors)}")

    # Fail closed on an unsafe target_root before anything else.
    validate_target_root(target_root)

    acquisition_mode = acquisition_mode or choose_default_acquisition_mode(candidate)

    estimated_size_bytes = candidate.metadata.get("estimated_size_bytes")
    if estimated_size_bytes is not None and not isinstance(estimated_size_bytes, int):
        estimated_size_bytes = None  # never guess/coerce a non-integer size

    blocked_reasons: list[str] = []
    if candidate.benchmark_role_recommendation == "blocked":
        blocked_reasons.append("candidate is blocked by dataset_importers scouting (benchmark_role_recommendation=blocked)")

    if requested_action == "execute_download":
        if candidate.license_risk in _DISQUALIFYING_LICENSE_RISK:
            blocked_reasons.append(f"license_risk='{candidate.license_risk}' blocks execute_download")
        if candidate.access_status in _DISQUALIFYING_ACCESS_STATUS:
            blocked_reasons.append(f"access_status='{candidate.access_status}' blocks execute_download")
        if disk_limit_bytes is None:
            blocked_reasons.append("disk_limit_bytes is required for execute_download")
        elif estimated_size_bytes is not None and estimated_size_bytes > disk_limit_bytes:
            blocked_reasons.append("estimated_size_bytes exceeds disk_limit_bytes")
        elif estimated_size_bytes is None and not force_unknown_size:
            blocked_reasons.append("estimated_size_bytes is unknown; pass force_unknown_size=True to override")
        if not allow_network:
            blocked_reasons.append("allow_network=False blocks execute_download")
        if not allow_raw_data:
            blocked_reasons.append("allow_raw_data=False blocks execute_download")
        if not explicit_execute_confirmed:
            blocked_reasons.append("explicit execute confirmation was not supplied")
        if acquisition_mode in _UNIMPLEMENTED_REMOTE_MODES:
            blocked_reasons.append(
                f"acquisition_mode='{acquisition_mode}' has no implemented remote-fetch execution path in v1"
            )

    dry_run = not (requested_action == "execute_download" and not blocked_reasons)

    risks = [
        "This plan reflects the source candidate's own catalog metadata; it was not independently "
        "re-verified against the dataset's current real-world license/access terms.",
    ]
    if estimated_size_bytes is None:
        risks.append("estimated_size_bytes is unknown -- actual disk usage cannot be predicted from this plan alone.")

    limitations = [
        "This plan does not itself perform any network access or file write -- see "
        "dataset_acquisition.executor.execute_acquisition_plan for the executable step.",
    ]

    provenance = (
        f"Derived from DatasetCandidateRecordV1(candidate_id={candidate.candidate_id}, "
        f"source_catalog={candidate.source_catalog}, source_dataset_id={candidate.source_dataset_id}) "
        "via dataset_acquisition.planner.make_acquisition_plan."
    )

    plan = DatasetAcquisitionPlanV1.make(
        candidate_id=candidate.candidate_id,
        requested_action=requested_action,
        acquisition_mode=acquisition_mode,
        target_root=str(target_root),
        disk_limit_bytes=disk_limit_bytes,
        source_catalog=candidate.source_catalog,
        source_dataset_id=candidate.source_dataset_id,
        display_name=candidate.display_name,
        source_url=candidate.public_url,
        source_repository=candidate.repository_url,
        license=candidate.license,
        license_risk=candidate.license_risk,
        access_status=candidate.access_status,
        estimated_size_bytes=estimated_size_bytes,
        expected_file_count=candidate.metadata.get("expected_file_count")
        if isinstance(candidate.metadata.get("expected_file_count"), int)
        else None,
        allow_network=bool(allow_network),
        allow_raw_data=bool(allow_raw_data),
        dry_run=dry_run,
        execution_required_flags=["--execute", "--allow-network", "--allow-raw-data", "--disk-limit-mb"],
        planned_steps=_planned_steps_for(requested_action, acquisition_mode, bool(blocked_reasons)),
        blocked_reasons=blocked_reasons,
        risks=risks,
        limitations=limitations,
        provenance=provenance,
        metadata={
            "explicit_execute_confirmed": bool(explicit_execute_confirmed),
            "force_unknown_size": bool(force_unknown_size),
            "candidate_benchmark_role_recommendation": candidate.benchmark_role_recommendation,
        },
    )
    plan.validate_or_raise()
    return plan


def plan_from_candidate_file(
    candidates_json: Union[str, Path],
    candidate_id: str,
    *,
    target_root: str,
    requested_action: str = "metadata_only",
    disk_limit_bytes: Optional[int] = None,
    allow_network: bool = False,
    allow_raw_data: bool = False,
    acquisition_mode: Optional[str] = None,
    force_unknown_size: bool = False,
    explicit_execute_confirmed: bool = False,
) -> DatasetAcquisitionPlanV1:
    data = json.loads(Path(candidates_json).read_text(encoding="utf-8"))
    entries = data.get("candidates") or []
    matches = [c for c in entries if c.get("candidate_id") == candidate_id]
    if not matches:
        raise PlannerError(f"candidate_id '{candidate_id}' not found in {candidates_json}")
    candidate = DatasetCandidateRecordV1.from_dict(matches[0])
    return make_acquisition_plan(
        candidate,
        target_root=target_root,
        requested_action=requested_action,
        disk_limit_bytes=disk_limit_bytes,
        allow_network=allow_network,
        allow_raw_data=allow_raw_data,
        acquisition_mode=acquisition_mode,
        force_unknown_size=force_unknown_size,
        explicit_execute_confirmed=explicit_execute_confirmed,
    )
