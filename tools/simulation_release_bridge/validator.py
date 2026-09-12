"""Rigorous validation engine for Simulation Release Bridge.

Implements:
1. Complete 8-stage chain verification:
   input provenance → configuration → code revision → seed → execution outcome → artifact manifest → validation → evidence review.
2. Rejection of fabricated provenance (placeholder run_id, source, revision, seed).
3. Rejection of incomplete manifests (missing RunRecord.json or summary/metrics).
4. Rejection of non-finite metrics (NaN, Inf, -Inf).
5. Rejection of output-root escapes (path traversal, absolute paths).
6. Rejection of temporary-only artifacts (scratch/tmp files without canonical outputs).
7. Fail-closed detection when canonical bounded runner is absent.
"""
from __future__ import annotations

import importlib
import math
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from .contracts import (
    CHAIN_STAGES,
    ExecutionOutcomeState,
    ReleasePromotionStatus,
    SimulationReleaseError,
    finite_value,
)

PLACEHOLDER_STRINGS = {
    "unknown",
    "null",
    "none",
    "n/a",
    "na",
    "placeholder",
    "synthetic-placeholder",
    "unspecified",
    "",
}

TEMP_PATTERNS = (
    re.compile(r"(^|[\\/])tmp", re.IGNORECASE),
    re.compile(r"(^|[\\/])temp", re.IGNORECASE),
    re.compile(r"\.tmp$", re.IGNORECASE),
    re.compile(r"pytest-", re.IGNORECASE),
    re.compile(r"\.scratch", re.IGNORECASE),
)

CANONICAL_OUTPUT_NAMES = {
    "runrecord.json",
    "summary.json",
    "metrics.json",
    "metrics.csv",
}


@dataclass
class ChainValidationResult:
    """Result of full 8-stage chain and guardrail validation."""
    is_valid: bool
    chain_complete: bool
    execution_state: str
    promotion_eligible: bool
    missing_stages: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    rejected_reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return finite_value(self)


def check_canonical_runner_presence() -> tuple[bool, str | None]:
    """Check whether the canonical bounded runner is present on current main."""
    try:
        mod = importlib.import_module("tools.simulation_execution.runner")
        if not hasattr(mod, "SCHEMA_VERSION"):
            return False, "tools.simulation_execution.runner lacks SCHEMA_VERSION"
        return True, None
    except (ImportError, ModuleNotFoundError) as exc:
        return False, f"canonical bounded runner absent from current main: {exc}"


def check_fabricated_provenance(
    provenance: Mapping[str, Any] | None,
    revision: Mapping[str, Any] | None,
    seed_spec: Mapping[str, Any] | None,
    run_id: str | None = None,
) -> list[str]:
    """Detect and reject placeholder or fabricated provenance fields."""
    errors: list[str] = []

    if not provenance:
        errors.append("missing input_provenance stage")
        return errors

    # Check run_id
    effective_run_id = (run_id or str(provenance.get("run_id", ""))).strip()
    if not effective_run_id or effective_run_id.lower() in PLACEHOLDER_STRINGS:
        errors.append(f"fabricated provenance: invalid or placeholder run_id '{effective_run_id}'")

    # Check source
    source = str(provenance.get("source", "")).strip()
    if not source or source.lower() in PLACEHOLDER_STRINGS:
        errors.append(f"fabricated provenance: invalid or placeholder source '{source}'")

    # Check dataset_id
    dataset_id = str(provenance.get("dataset_id", "")).strip()
    if not dataset_id or dataset_id.lower() in PLACEHOLDER_STRINGS:
        errors.append(f"fabricated provenance: invalid or placeholder dataset_id '{dataset_id}'")

    # Check data_mode
    data_mode = str(provenance.get("data_mode", "")).strip().lower()
    if not data_mode or data_mode in PLACEHOLDER_STRINGS:
        errors.append(f"fabricated provenance: missing or invalid data_mode '{data_mode}'")

    # Check code revision
    if not revision:
        errors.append("missing code_revision stage")
    else:
        code_rev = str(revision.get("code_revision", "")).strip()
        if not code_rev or code_rev.lower() in PLACEHOLDER_STRINGS:
            errors.append(f"fabricated provenance: invalid or placeholder code_revision '{code_rev}'")

    # Check seed
    if not seed_spec:
        errors.append("missing seed stage")
    else:
        raw_seed = seed_spec.get("seed")
        if raw_seed is None:
            errors.append("fabricated provenance: missing seed (seed is null)")
        elif isinstance(raw_seed, bool) or not isinstance(raw_seed, int):
            errors.append(f"fabricated provenance: seed must be a valid integer, got {type(raw_seed).__name__}")

    return errors


def check_output_root_escapes(
    artifacts: Sequence[Mapping[str, Any]],
    output_root: Path | str | None = None,
) -> list[str]:
    """Detect and reject paths escaping the output directory or containing path traversal."""
    errors: list[str] = []
    root_resolved = Path(output_root).resolve() if output_root else None

    for idx, item in enumerate(artifacts):
        rel = str(item.get("relative_path", "")).strip()
        if not rel:
            errors.append(f"artifact [{idx}] has empty relative_path")
            continue

        # Check for path traversal components
        parts = Path(rel).parts
        if ".." in parts:
            errors.append(f"output-root escape: artifact relative_path '{rel}' contains '..'")

        # Check for leading slashes or drive letters
        if rel.startswith(("/", "\\")) or (len(rel) >= 2 and rel[1] == ":"):
            errors.append(f"output-root escape: artifact relative_path '{rel}' is an absolute path")

        # If root directory is provided, verify containment after resolution
        if root_resolved:
            candidate = (root_resolved / rel).resolve()
            try:
                candidate.relative_to(root_resolved)
            except ValueError:
                errors.append(f"output-root escape: artifact '{rel}' resolves outside output root: {candidate}")

    return errors


def check_temporary_only_artifacts(artifacts: Sequence[Mapping[str, Any]]) -> list[str]:
    """Reject manifests that only contain temporary scratch files."""
    if not artifacts:
        return ["manifest contains no artifacts"]

    has_canonical = False
    temp_count = 0

    for item in artifacts:
        rel = str(item.get("relative_path", "")).strip()
        norm_name = Path(rel).name.lower()
        if norm_name in CANONICAL_OUTPUT_NAMES:
            has_canonical = True

        is_temp = any(pat.search(rel) for pat in TEMP_PATTERNS)
        if is_temp:
            temp_count += 1

    if not has_canonical and temp_count == len(artifacts):
        return ["temporary-only artifacts: manifest contains exclusively temporary scratch files"]

    return []


def check_manifest_completeness(artifacts: Sequence[Mapping[str, Any]]) -> list[str]:
    """Verify that required canonical artifacts exist in the manifest."""
    errors: list[str] = []
    if not artifacts:
        return ["manifest is empty: no artifacts declared"]

    names = {Path(str(item.get("relative_path", ""))).name.lower() for item in artifacts}

    if "runrecord.json" not in names:
        errors.append("incomplete manifest: missing RunRecord.json")

    has_summary_or_metrics = bool(
        names.intersection({"summary.json", "metrics.json", "metrics.csv"})
    )
    if not has_summary_or_metrics:
        errors.append("incomplete manifest: missing summary.json, metrics.json, or metrics.csv")

    return errors


def check_non_finite_metrics(value: Any, path: str = "$") -> list[str]:
    """Recursively search for NaN, Inf, or -Inf in metrics structures."""
    errors: list[str] = []
    if value is None:
        return errors
    if isinstance(value, float):
        if not math.isfinite(value):
            errors.append(f"non-finite metric at {path}: {value}")
    elif isinstance(value, str):
        # Look for literal string representations of NaN or Infinity
        lower = value.strip().lower()
        if lower in {"nan", "+nan", "-nan", "inf", "+inf", "-inf", "infinity", "+infinity", "-infinity"}:
            errors.append(f"non-finite token at {path}: '{value}'")
    elif isinstance(value, (list, tuple)):
        for idx, item in enumerate(value):
            errors.extend(check_non_finite_metrics(item, f"{path}[{idx}]"))
    elif isinstance(value, Mapping):
        for k, v in value.items():
            errors.extend(check_non_finite_metrics(v, f"{path}.{k}"))
    return errors


def validate_stages(
    stages: Mapping[str, Any],
    *,
    output_root: Path | str | None = None,
    require_canonical_runner: bool = True,
) -> ChainValidationResult:
    """Validate full 8-stage chain continuity, integrity, and guardrails."""
    missing_stages: list[str] = []
    errors: list[str] = []
    warnings: list[str] = []
    rejected_reasons: list[str] = []

    # 1. Verify 8-stage chain presence
    for stage_name in CHAIN_STAGES:
        if stage_name not in stages or stages[stage_name] is None:
            missing_stages.append(stage_name)

    chain_complete = len(missing_stages) == 0
    if not chain_complete:
        errors.append(f"incomplete chain: missing stages {missing_stages}")

    # 2. Canonical runner check
    if require_canonical_runner:
        runner_ok, runner_err = check_canonical_runner_presence()
        if not runner_ok:
            errors.append(f"fail-closed prerequisite: {runner_err}")
            rejected_reasons.append("MISSING_CANONICAL_RUNNER")

    # 3. Extract stage contents
    provenance = stages.get("input_provenance") or {}
    config = stages.get("configuration") or {}
    revision = stages.get("code_revision") or {}
    seed_spec = stages.get("seed") or {}
    outcome = stages.get("execution_outcome") or {}
    manifest = stages.get("artifact_manifest") or {}
    validation = stages.get("validation") or {}
    review = stages.get("evidence_review") or {}

    # 4. Check provenance
    run_id_val = (
        provenance.get("run_id")
        or stages.get("run_id")
        or outcome.get("run_id")
        or config.get("spec_id")
    )
    prov_errors = check_fabricated_provenance(provenance, revision, seed_spec, run_id=run_id_val)
    if prov_errors:
        errors.extend(prov_errors)
        rejected_reasons.append("FABRICATED_PROVENANCE")

    # 5. Check execution outcome state
    state_str = str(outcome.get("state", "NOT_RUN")).upper()
    try:
        outcome_state = ExecutionOutcomeState(state_str)
    except ValueError:
        outcome_state = ExecutionOutcomeState.NOT_RUN
        errors.append(f"invalid execution outcome state '{state_str}'")

    # 6. Check artifact manifest
    artifacts = manifest.get("artifacts", [])
    if isinstance(artifacts, (list, tuple)):
        # Escapes
        escape_errors = check_output_root_escapes(artifacts, output_root=output_root)
        if escape_errors:
            errors.extend(escape_errors)
            rejected_reasons.append("OUTPUT_ROOT_ESCAPE")

        # Temporary-only
        temp_errors = check_temporary_only_artifacts(artifacts)
        if temp_errors:
            errors.extend(temp_errors)
            rejected_reasons.append("TEMPORARY_ONLY_ARTIFACTS")

        # Completeness
        comp_errors = check_manifest_completeness(artifacts)
        if comp_errors:
            errors.extend(comp_errors)
            rejected_reasons.append("INCOMPLETE_MANIFEST")
    else:
        errors.append("artifact_manifest.artifacts must be a sequence")
        rejected_reasons.append("INVALID_MANIFEST")

    # 7. Check non-finite metrics in config, outcome, and provenance
    metric_errors: list[str] = []
    if "metrics" in provenance:
        metric_errors.extend(check_non_finite_metrics(provenance["metrics"], "provenance.metrics"))
    if "parameters" in config:
        metric_errors.extend(check_non_finite_metrics(config["parameters"], "configuration.parameters"))
    if "metrics" in outcome:
        metric_errors.extend(check_non_finite_metrics(outcome["metrics"], "execution_outcome.metrics"))

    if metric_errors:
        errors.extend(metric_errors)
        rejected_reasons.append("NON_FINITE_METRICS")

    # 8. Check validation report
    validation_passed = bool(validation.get("passed", False))
    if not validation_passed and outcome_state == ExecutionOutcomeState.PASS:
        warnings.append("execution outcome is PASS but validation report passed is False")

    # 9. Determine promotion eligibility
    # Promotion requires:
    # - Chain is complete
    # - Zero fatal errors
    # - Execution outcome is strictly PASS
    # - Validation passed is True
    promotion_eligible = (
        chain_complete
        and len(errors) == 0
        and outcome_state == ExecutionOutcomeState.PASS
        and validation_passed
    )

    is_valid = len(errors) == 0

    return ChainValidationResult(
        is_valid=is_valid,
        chain_complete=chain_complete,
        execution_state=outcome_state.value,
        promotion_eligible=promotion_eligible,
        missing_stages=missing_stages,
        errors=errors,
        warnings=warnings,
        rejected_reasons=rejected_reasons,
    )
