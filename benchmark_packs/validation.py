"""Structural validation and banned-phrase scanning for
`BenchmarkPackSpecV1`/`BenchmarkPackV1`/`BenchmarkPackIndexV1`.

Mirrors `job_runner.validation`'s split: pure structural checks here, no
filesystem access beyond validating an *embedded* pipeline spec dict
already in memory (never reading a path off disk -- that stays the
builder's job, matching every other validation module in this
repository).
"""
from __future__ import annotations

from typing import Any

from dataset_acquisition.store import ALLOWED_TARGET_ROOT_PREFIXES
from job_runner.validation import ALLOWED_REQUESTED_OUTPUTS
from phase_space.coordinate import scan_banned_phrases
from sciencer_d.btc_icft.report_guardrails import BANNED_REPORT_PHRASES
from transitions.governance import TRANSITION_EXTRA_BANNED_PHRASES
from workflows.validation import REPORT_PIPELINE_EXTRA_BANNED_PHRASES

ALLOWED_PACK_KINDS: frozenset[str] = frozenset(
    {"demo_pack", "methods_supplement", "internal_regression_pack", "commercial_sample_pack", "benchmark_candidate_pack"}
)

# A pack assembling an unbounded number of pipeline specs is a design
# smell, not a feature -- a ceiling, not a target.
MAX_PIPELINE_SPECS_CEILING = 200

BENCHMARK_PACK_EXTRA_BANNED_PHRASES: tuple[str, ...] = REPORT_PIPELINE_EXTRA_BANNED_PHRASES

_ALL_BENCHMARK_PACK_BANNED_PHRASES: tuple[str, ...] = (
    BANNED_REPORT_PHRASES + TRANSITION_EXTRA_BANNED_PHRASES + BENCHMARK_PACK_EXTRA_BANNED_PHRASES
)


class BenchmarkPackStoreError(ValueError):
    """Raised for benchmark-pack-store-level problems (unsafe output_root, missing pack, ...)."""


def scan_text_for_banned_phrases(text: str) -> list[str]:
    """Return every banned phrase (lowercased) found in `text` -- empty
    list means clean. Never raises."""
    low = text.lower()
    return [phrase for phrase in _ALL_BENCHMARK_PACK_BANNED_PHRASES if phrase in low]


def _scan_banned_phrases(value: Any, path: str, errors: list[str]) -> None:
    scan_banned_phrases(value, path, errors)
    if isinstance(value, str):
        low = value.lower()
        for phrase in BENCHMARK_PACK_EXTRA_BANNED_PHRASES:
            if phrase in low:
                errors.append(f"{path}: banned phrase detected: '{phrase}'")
    elif isinstance(value, dict):
        for key, sub in value.items():
            _scan_banned_phrases(sub, f"{path}.{key}", errors)
    elif isinstance(value, (list, tuple)):
        for idx, item in enumerate(value):
            _scan_banned_phrases(item, f"{path}[{idx}]", errors)


def _validate_repo_relative_root(value: Any, field_name: str) -> list[str]:
    """String-level prefix check only -- the real traversal/containment
    safety check is `dataset_acquisition.store.validate_target_root`,
    applied at write time by the builder/store."""
    errors: list[str] = []
    if not value or not isinstance(value, str):
        errors.append(f"{field_name} is required (non-empty string) (rule 5)")
        return errors
    raw = value.strip()
    if raw.startswith("/") or raw.startswith("~") or ".." in raw.split("/"):
        errors.append(f"{field_name} must be a safe relative repository path, got {value!r} (rule 5)")
        return errors
    if not any(raw == prefix.rstrip("/") or raw.startswith(prefix) for prefix in ALLOWED_TARGET_ROOT_PREFIXES):
        errors.append(f"{field_name} must be under one of {ALLOWED_TARGET_ROOT_PREFIXES}, got {value!r} (rule 5)")
    return errors


def validate_benchmark_pack_spec(spec: Any) -> list[str]:
    """Return a list of error strings (empty = valid). Never raises;
    never reads a path off disk -- only validates already-embedded
    `pipeline_specs` dicts (pure, in-memory) if present."""
    errors: list[str] = []

    if not getattr(spec, "benchmark_pack_spec_id", None):
        errors.append("benchmark_pack_spec_id is required")

    # Rule 1.
    if not getattr(spec, "limitations", None):
        errors.append("limitations must be a non-empty list (rule 1)")

    # Rule 2.
    if not getattr(spec, "provenance", None):
        errors.append("provenance is required (rule 2)")

    # Rule 3.
    pack_kind = getattr(spec, "pack_kind", None)
    if pack_kind not in ALLOWED_PACK_KINDS:
        errors.append(f"pack_kind '{pack_kind}' must be one of {sorted(ALLOWED_PACK_KINDS)} (rule 3)")

    # Rule 4.
    requested_outputs = getattr(spec, "requested_outputs", None) or []
    if not requested_outputs:
        errors.append("requested_outputs must be a non-empty list (rule 4)")
    for item in requested_outputs:
        if item not in ALLOWED_REQUESTED_OUTPUTS:
            errors.append(f"requested_outputs: '{item}' must be one of {sorted(ALLOWED_REQUESTED_OUTPUTS)} (rule 4)")

    # Rule 5.
    errors.extend(_validate_repo_relative_root(getattr(spec, "output_root", None), "output_root"))
    errors.extend(_validate_repo_relative_root(getattr(spec, "jobs_root", None), "jobs_root"))

    pipeline_specs = getattr(spec, "pipeline_specs", None) or []
    pipeline_spec_paths = getattr(spec, "pipeline_spec_paths", None) or []
    if not pipeline_specs and not pipeline_spec_paths:
        errors.append("at least one of pipeline_specs or pipeline_spec_paths is required")
    total_specs = len(pipeline_specs) + len(pipeline_spec_paths)
    if total_specs > MAX_PIPELINE_SPECS_CEILING:
        errors.append(f"pipeline_specs + pipeline_spec_paths must not exceed {MAX_PIPELINE_SPECS_CEILING}, got {total_specs}")

    # Rule 6: embedded pipeline specs must validate -- checked in-memory
    # only; a bare pipeline_spec_paths entry (no embedded dict) is
    # checked for real by the builder at build time.
    if pipeline_specs:
        from workflows.report_pipeline import ReportPipelineSpecV1

        for idx, pipeline_spec in enumerate(pipeline_specs):
            spec_errors = ReportPipelineSpecV1.from_dict(pipeline_spec).validate()
            errors.extend(f"pipeline_specs[{idx}]: {e} (rule 6)" for e in spec_errors)

    max_jobs = getattr(spec, "max_jobs", None)
    if max_jobs is not None and (not isinstance(max_jobs, int) or isinstance(max_jobs, bool) or max_jobs < 1):
        errors.append(f"max_jobs must be a positive integer when set, got {max_jobs!r}")

    # Rule 8/9 (+11 field-level): no claim/evidence promotion field.
    if hasattr(spec, "claim_scope") or hasattr(spec, "evidence_level") or hasattr(spec, "validation_ready"):
        errors.append("BenchmarkPackSpecV1 must not carry its own claim_scope/evidence_level/validation_ready field (rule 8/9)")

    # Rule 7 (+ banned-phrase scan).
    for field_name in ("pack_name", "pack_purpose", "provenance"):
        _scan_banned_phrases(getattr(spec, field_name, None) or "", field_name, errors)
    _scan_banned_phrases(getattr(spec, "limitations", None) or [], "limitations", errors)
    _scan_banned_phrases(getattr(spec, "metadata", None) or {}, "metadata", errors)

    return errors


def validate_benchmark_pack(pack: Any) -> list[str]:
    """Return a list of error strings (empty = valid). Never raises."""
    errors: list[str] = []

    if not getattr(pack, "benchmark_pack_id", None):
        errors.append("benchmark_pack_id is required")

    # Rule 1.
    if not getattr(pack, "limitations", None):
        errors.append("limitations must be a non-empty list (rule 1)")
    if not getattr(pack, "blocked_interpretations", None):
        errors.append("blocked_interpretations must be a non-empty list (rule 1)")

    pack_kind = getattr(pack, "pack_kind", None)
    if pack_kind not in ALLOWED_PACK_KINDS:
        errors.append(f"pack_kind '{pack_kind}' must be one of {sorted(ALLOWED_PACK_KINDS)} (rule 3)")

    if not getattr(pack, "execution_summary", None):
        errors.append("execution_summary is required (non-empty dict)")
    if not getattr(pack, "coverage_summary", None):
        errors.append("coverage_summary is required (non-empty dict)")

    # Rule 8/9.
    if hasattr(pack, "claim_scope") or hasattr(pack, "evidence_level") or hasattr(pack, "validation_ready"):
        errors.append("BenchmarkPackV1 must not carry its own claim_scope/evidence_level/validation_ready field (rule 8/9)")

    # Rule 7 (+ banned-phrase scan).
    for field_name in ("pack_name", "pack_purpose"):
        _scan_banned_phrases(getattr(pack, field_name, None) or "", field_name, errors)
    for field_name in ("limitations", "blocked_interpretations", "reproducibility_commands"):
        _scan_banned_phrases(getattr(pack, field_name, None) or [], field_name, errors)
    _scan_banned_phrases(getattr(pack, "metadata", None) or {}, "metadata", errors)

    return errors


def validate_benchmark_pack_index(index: Any) -> list[str]:
    """Return a list of error strings (empty = valid). Never raises."""
    errors: list[str] = []

    if not getattr(index, "index_id", None):
        errors.append("index_id is required")
    if not getattr(index, "benchmark_pack_id", None):
        errors.append("benchmark_pack_id is required")

    # Rule 1.
    if not getattr(index, "limitations", None):
        errors.append("limitations must be a non-empty list (rule 1)")
    if not getattr(index, "blocked_interpretations", None):
        errors.append("blocked_interpretations must be a non-empty list (rule 1)")

    if hasattr(index, "claim_scope") or hasattr(index, "evidence_level") or hasattr(index, "validation_ready"):
        errors.append("BenchmarkPackIndexV1 must not carry its own claim_scope/evidence_level/validation_ready field (rule 8/9)")

    # Rule 7 (+ banned-phrase scan).
    _scan_banned_phrases(getattr(index, "title", None) or "", "title", errors)
    for field_name in ("limitations", "blocked_interpretations"):
        _scan_banned_phrases(getattr(index, field_name, None) or [], field_name, errors)
    _scan_banned_phrases(getattr(index, "metadata", None) or {}, "metadata", errors)

    return errors
