"""Structural validation and banned-phrase scanning for
`PipelineJobV1`/`PipelineJobResultV1`.

Mirrors `workflows.validation`/`workflows.html_validation`'s split: pure
structural checks here, no filesystem access beyond validating an
*embedded* spec dict already in memory (never reading a path off disk --
that stays the runner's job, matching every other validation module in
this repository).
"""
from __future__ import annotations

from typing import Any

from dataset_acquisition.store import ALLOWED_TARGET_ROOT_PREFIXES
from phase_space.coordinate import scan_banned_phrases
from sciencer_d.btc_icft.report_guardrails import BANNED_REPORT_PHRASES
from transitions.governance import TRANSITION_EXTRA_BANNED_PHRASES
from workflows.validation import REPORT_PIPELINE_EXTRA_BANNED_PHRASES

ALLOWED_JOB_STATUSES: frozenset[str] = frozenset(
    {"created", "queued", "running", "completed", "completed_with_warnings", "failed", "cancelled", "blocked"}
)

ALLOWED_REQUESTED_OUTPUTS: frozenset[str] = frozenset({"report_pack", "html_report_pack", "json_manifests_only"})

# A job that never terminates after this many attempts is a bug or a
# structurally broken spec, not something worth retrying indefinitely --
# a ceiling, not a target.
MAX_ATTEMPTS_CEILING = 10

JOB_RUNNER_EXTRA_BANNED_PHRASES: tuple[str, ...] = REPORT_PIPELINE_EXTRA_BANNED_PHRASES

_ALL_JOB_BANNED_PHRASES: tuple[str, ...] = (
    BANNED_REPORT_PHRASES + TRANSITION_EXTRA_BANNED_PHRASES + JOB_RUNNER_EXTRA_BANNED_PHRASES
)


class JobStoreError(ValueError):
    """Raised for job-store-level problems (lock conflict, missing job, unsafe output_root, ...)."""


def scan_text_for_banned_phrases(text: str) -> list[str]:
    """Return every banned phrase (lowercased) found in `text` -- empty
    list means clean. Never raises."""
    low = text.lower()
    return [phrase for phrase in _ALL_JOB_BANNED_PHRASES if phrase in low]


def _scan_banned_phrases(value: Any, path: str, errors: list[str]) -> None:
    scan_banned_phrases(value, path, errors)
    if isinstance(value, str):
        low = value.lower()
        for phrase in JOB_RUNNER_EXTRA_BANNED_PHRASES:
            if phrase in low:
                errors.append(f"{path}: banned phrase detected: '{phrase}'")
    elif isinstance(value, dict):
        for key, sub in value.items():
            _scan_banned_phrases(sub, f"{path}.{key}", errors)
    elif isinstance(value, (list, tuple)):
        for idx, item in enumerate(value):
            _scan_banned_phrases(item, f"{path}[{idx}]", errors)


def validate_output_root(output_root: Any) -> list[str]:
    """String-level prefix check only (rule 4) -- the real traversal/
    containment safety check is `dataset_acquisition.store.validate_target_root`,
    applied at write time in the job store."""
    errors: list[str] = []
    if not output_root or not isinstance(output_root, str):
        errors.append("output_root is required (non-empty string) (rule 4)")
        return errors
    raw = output_root.strip()
    if raw.startswith("/") or raw.startswith("~") or ".." in raw.split("/"):
        errors.append(f"output_root must be a safe relative repository path, got {output_root!r} (rule 4)")
        return errors
    if not any(raw == prefix.rstrip("/") or raw.startswith(prefix) for prefix in ALLOWED_TARGET_ROOT_PREFIXES):
        errors.append(f"output_root must be under one of {ALLOWED_TARGET_ROOT_PREFIXES}, got {output_root!r} (rule 4)")
    return errors


def validate_pipeline_job(job: Any) -> list[str]:
    """Return a list of error strings (empty = valid). Never raises; never
    reads a path off disk -- only validates an already-embedded spec dict
    (pure, in-memory) if one is present."""
    errors: list[str] = []

    if not getattr(job, "job_id", None):
        errors.append("job_id is required")

    # Rule 1.
    if not getattr(job, "limitations", None):
        errors.append("limitations must be a non-empty list (rule 1)")

    # Rule 2.
    if not getattr(job, "provenance", None):
        errors.append("provenance is required (rule 2)")

    # Rule 3: pipeline_spec must validate -- checked in-memory only when a
    # spec dict is already embedded; a bare pipeline_spec_path (no
    # embedded dict) is checked for real by the runner at execution time,
    # matching the "no I/O in validate()" discipline this repository's
    # other validation modules already follow.
    pipeline_spec_path = getattr(job, "pipeline_spec_path", None)
    pipeline_spec = getattr(job, "pipeline_spec", None)
    if not pipeline_spec_path and not pipeline_spec:
        errors.append("one of pipeline_spec_path or pipeline_spec (embedded) is required (rule 3)")
    if pipeline_spec:
        from workflows.report_pipeline import ReportPipelineSpecV1

        spec_errors = ReportPipelineSpecV1.from_dict(pipeline_spec).validate()
        errors.extend(f"pipeline_spec: {e} (rule 3)" for e in spec_errors)

    # Rule 4.
    errors.extend(validate_output_root(getattr(job, "output_root", None)))

    # Rule 5.
    job_status = getattr(job, "job_status", None)
    if job_status not in ALLOWED_JOB_STATUSES:
        errors.append(f"job_status '{job_status}' must be one of {sorted(ALLOWED_JOB_STATUSES)} (rule 5)")

    # Rule 6.
    max_attempts = getattr(job, "max_attempts", None)
    if not isinstance(max_attempts, int) or isinstance(max_attempts, bool) or not (1 <= max_attempts <= MAX_ATTEMPTS_CEILING):
        errors.append(f"max_attempts must be an integer in [1, {MAX_ATTEMPTS_CEILING}], got {max_attempts!r} (rule 6)")

    # Rule 7.
    if job_status == "running" and not getattr(job, "started_at", None):
        errors.append("a running job must have started_at set (rule 7)")

    # Rule 8.
    if job_status in {"completed", "completed_with_warnings"} and not getattr(job, "completed_at", None):
        errors.append("a completed job must have completed_at set (rule 8)")

    # Rule 9.
    if job_status == "failed" and not getattr(job, "error_summary", None):
        errors.append("a failed job must record error_summary (rule 9)")

    # Rule 10.
    requested_outputs = getattr(job, "requested_outputs", None) or []
    if not requested_outputs:
        errors.append("requested_outputs must be a non-empty list (rule 10)")
    for item in requested_outputs:
        if item not in ALLOWED_REQUESTED_OUTPUTS:
            errors.append(f"requested_outputs: '{item}' must be one of {sorted(ALLOWED_REQUESTED_OUTPUTS)} (rule 10)")

    # Rule 11.
    if hasattr(job, "claim_scope") or hasattr(job, "evidence_level"):
        errors.append("PipelineJobV1 must not carry its own claim_scope/evidence_level field (rule 11)")

    # Rule 14 (+ 12/13 phrase coverage): banned-phrase scan.
    for field_name in ("job_name", "provenance"):
        _scan_banned_phrases(getattr(job, field_name, None) or "", field_name, errors)
    _scan_banned_phrases(getattr(job, "limitations", None) or [], "limitations", errors)
    _scan_banned_phrases(getattr(job, "error_summary", None) or "", "error_summary", errors)
    _scan_banned_phrases(getattr(job, "metadata", None) or {}, "metadata", errors)

    return errors


def validate_pipeline_job_result(result: Any) -> list[str]:
    """Return a list of error strings (empty = valid). Never raises."""
    errors: list[str] = []

    if not getattr(result, "job_id", None):
        errors.append("job_id is required")

    # Rule 1.
    if not getattr(result, "limitations", None):
        errors.append("limitations must be a non-empty list (rule 1)")

    # Rule 2.
    if not getattr(result, "provenance", None):
        errors.append("provenance is required (rule 2)")

    # Rule 5.
    job_status = getattr(result, "job_status", None)
    if job_status not in ALLOWED_JOB_STATUSES:
        errors.append(f"job_status '{job_status}' must be one of {sorted(ALLOWED_JOB_STATUSES)} (rule 5)")

    # Rule 9.
    if job_status == "failed" and not getattr(result, "errors", None):
        errors.append("a failed result must record errors (rule 9)")

    # Rule 11.
    if hasattr(result, "claim_scope") or hasattr(result, "evidence_level"):
        errors.append("PipelineJobResultV1 must not carry its own claim_scope/evidence_level field (rule 11)")

    # Rule 14 (+ 12 phrase coverage): banned-phrase scan.
    _scan_banned_phrases(getattr(result, "provenance", None) or "", "provenance", errors)
    for field_name in ("limitations", "errors", "warnings", "generated_files"):
        _scan_banned_phrases(getattr(result, field_name, None) or [], field_name, errors)
    _scan_banned_phrases(getattr(result, "metadata", None) or {}, "metadata", errors)

    return errors
