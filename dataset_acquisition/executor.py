"""Dry-run-first execution of a `DatasetAcquisitionPlanV1`.

`execute=False` (the default) always produces a `planned_only` manifest and
touches neither the network nor the filesystem beyond reading the plan
itself. `execute=True` still requires the plan to already carry every
safety flag (validated on construction by `dataset_acquisition.planner`)
and additionally requires the *executor's own* `allow_network`/
`allow_raw_data` to agree with the plan -- a caller cannot silently
escalate a plan's permissions at execution time.

v1 only ever writes files for `scan_existing_local`/`verify_existing_local`
(reading a fixture/root that is already present locally). Every other
`acquisition_mode` remains blocked/planned-only in this milestone -- see
`dataset_acquisition.validation._UNIMPLEMENTED_REMOTE_MODES`.
"""
from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
from typing import Any, Optional

from dataset_acquisition.acquisition_plan import DatasetAcquisitionPlanV1
from dataset_acquisition.manifest import DatasetAcquisitionManifestV1
from dataset_acquisition.store import validate_target_root
from dataset_acquisition.validation import _UNIMPLEMENTED_REMOTE_MODES

_REPO_ROOT = Path(__file__).resolve().parents[1]


class ExecutorError(ValueError):
    """Raised when execution cannot proceed at all (invalid plan, missing
    required safety flags, ...)."""


def _repo_commit() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=str(_REPO_ROOT), capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return "unknown"


def _sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _walk_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return sorted(p for p in root.rglob("*") if p.is_file())


def _base_manifest_kwargs(plan: DatasetAcquisitionPlanV1) -> dict[str, Any]:
    return dict(
        source_catalog=plan.source_catalog,
        source_dataset_id=plan.source_dataset_id,
        repo_commit=_repo_commit(),
        risks=["This manifest reflects a local filesystem scan/execution result only -- it is not evidence."],
        limitations=[
            "Acquired/scanned files are not preprocessed, feature-extracted, or otherwise analyzed by this "
            "package -- see adapters.mne_bids for the next, separate, explicit step."
        ],
        provenance=f"Produced by dataset_acquisition.executor.execute_acquisition_plan for plan_id={plan.plan_id}.",
    )


def _planned_only_manifest(plan: DatasetAcquisitionPlanV1, *, status: str = "planned_only") -> DatasetAcquisitionManifestV1:
    manifest = DatasetAcquisitionManifestV1.make(
        plan_id=plan.plan_id,
        candidate_id=plan.candidate_id,
        execution_status=status,
        **_base_manifest_kwargs(plan),
    )
    manifest.validate_or_raise()
    return manifest


def _scan_or_verify_local(
    plan: DatasetAcquisitionPlanV1, *, status: str, checksum_files: bool
) -> DatasetAcquisitionManifestV1:
    target_root = validate_target_root(plan.target_root)
    files = _walk_files(target_root)

    if not files:
        manifest = DatasetAcquisitionManifestV1.make(
            plan_id=plan.plan_id,
            candidate_id=plan.candidate_id,
            execution_status="failed",
            errors=[f"target_root '{plan.target_root}' does not exist or contains no files"],
            **_base_manifest_kwargs(plan),
        )
        manifest.validate_or_raise()
        return manifest

    acquired_paths = [str(p.relative_to(_REPO_ROOT)) for p in files]
    acquired_size_bytes = sum(p.stat().st_size for p in files)
    checksums = {str(p.relative_to(_REPO_ROOT)): _sha256_of(p) for p in files} if checksum_files else {}

    manifest = DatasetAcquisitionManifestV1.make(
        plan_id=plan.plan_id,
        candidate_id=plan.candidate_id,
        execution_status=status,
        acquired_paths=acquired_paths,
        acquired_file_count=len(acquired_paths),
        acquired_size_bytes=acquired_size_bytes,
        checksums=checksums,
        **_base_manifest_kwargs(plan),
    )
    manifest.validate_or_raise()
    return manifest


def execute_acquisition_plan(
    plan: DatasetAcquisitionPlanV1,
    *,
    execute: bool = False,
    allow_network: bool = False,
    allow_raw_data: bool = False,
    force_unknown_size: bool = False,
) -> DatasetAcquisitionManifestV1:
    plan_errors = plan.validate()
    if plan_errors:
        raise ExecutorError(f"plan '{plan.plan_id}' fails its own validation: {'; '.join(plan_errors)}")

    if not execute:
        return _planned_only_manifest(plan)

    # execute=True from here on -- every remaining branch either performs a
    # real (local-only) filesystem read or fails closed with ExecutorError.
    if plan.requested_action == "scan_existing_local":
        return _scan_or_verify_local(plan, status="acquired", checksum_files=True)
    if plan.requested_action == "verify_existing_local":
        return _scan_or_verify_local(plan, status="verified_existing", checksum_files=True)
    if plan.requested_action == "metadata_only":
        return _planned_only_manifest(plan)

    if plan.requested_action in ("plan_download", "execute_download"):
        if plan.blocked_reasons:
            manifest = DatasetAcquisitionManifestV1.make(
                plan_id=plan.plan_id,
                candidate_id=plan.candidate_id,
                execution_status="blocked",
                errors=list(plan.blocked_reasons),
                **_base_manifest_kwargs(plan),
            )
            manifest.validate_or_raise()
            return manifest

        if plan.requested_action == "plan_download":
            return _planned_only_manifest(plan, status="planned_only")

        # requested_action == "execute_download", plan carries no
        # blocked_reasons -- the executor's own flags must independently
        # agree with the plan's before anything happens (no silent
        # escalation of a stale plan's permissions).
        if not (allow_network and plan.allow_network):
            raise ExecutorError("execute_acquisition_plan requires allow_network=True (and plan.allow_network=True)")
        if not (allow_raw_data and plan.allow_raw_data):
            raise ExecutorError("execute_acquisition_plan requires allow_raw_data=True (and plan.allow_raw_data=True)")
        if plan.disk_limit_bytes is None:
            raise ExecutorError("execute_acquisition_plan requires plan.disk_limit_bytes to be set")
        if plan.estimated_size_bytes is None and not (force_unknown_size and plan.metadata.get("force_unknown_size")):
            raise ExecutorError(
                "execute_acquisition_plan requires a known estimated_size_bytes unless force_unknown_size=True"
            )

        if plan.acquisition_mode in _UNIMPLEMENTED_REMOTE_MODES:
            # Validated already-unblocked plans never reach this branch in
            # practice (planner blocks unimplemented remote modes), but the
            # executor fails closed here too as an independent guard.
            raise ExecutorError(
                f"acquisition_mode='{plan.acquisition_mode}' has no implemented remote-fetch execution path in v1"
            )

        # No remaining v1-supported remote mode reaches this point.
        raise ExecutorError(f"requested_action='execute_download' is not executable for acquisition_mode='{plan.acquisition_mode}' in v1")

    raise ExecutorError(f"requested_action '{plan.requested_action}' is not executable")


def run_bids_handoff(manifest: DatasetAcquisitionManifestV1, *, target_root: str) -> dict[str, Any]:
    """Optional Phase E handoff: if `manifest` reflects a verified/acquired
    local root, run `adapters.mne_bids.scan_bids_metadata` over it and
    return conservative `DatasetRecordV1`/`ArtifactRecordV1` dicts.

    Never produces `TransitionRecordV1` -- no explicit derived-feature
    mapping is available at this stage, matching
    `adapters.mne_bids.make_dataset_record_from_bids(mapping_provided=False)`'s
    own conservative default."""
    if manifest.execution_status not in ("acquired", "verified_existing"):
        raise ExecutorError(
            f"run_bids_handoff requires execution_status in ('acquired', 'verified_existing'), got "
            f"'{manifest.execution_status}'"
        )

    from adapters.mne_bids import make_artifact_records_from_bids, make_dataset_record_from_bids, scan_bids_metadata

    resolved_root = validate_target_root(target_root)
    summary = scan_bids_metadata(resolved_root)
    dataset_record = make_dataset_record_from_bids(summary, mapping_provided=False)
    artifact_records = make_artifact_records_from_bids(summary)

    dataset_errors = dataset_record.validate()
    if dataset_errors:
        raise ExecutorError(f"BIDS handoff produced an invalid DatasetRecordV1: {'; '.join(dataset_errors)}")
    for art in artifact_records:
        art_errors = art.validate()
        if art_errors:
            raise ExecutorError(f"BIDS handoff produced an invalid ArtifactRecordV1: {'; '.join(art_errors)}")

    return {
        "bids_metadata_summary": {
            "dataset_id": summary.dataset_id,
            "n_subjects": summary.n_subjects,
            "modalities_declared": list(summary.modalities_declared),
        },
        "dataset_record": dataset_record.to_dict(),
        "artifact_records": [a.to_dict() for a in artifact_records],
    }
