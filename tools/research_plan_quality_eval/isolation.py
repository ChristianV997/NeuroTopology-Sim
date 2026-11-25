"""Development / held-out access control.

The harness fits and tunes nothing. Its configuration is the rubric source
identity plus fixed constants (duplicate threshold, shingle size,
normalisation version, minimum split sizes). That configuration is
fingerprinted.

- A stage takes the verified manifest, not records. It loads only its own
  role's plan files, so no caller can hand it held-out records.
- Held-out evaluation takes a development result and first reproduces it from
  the plan files, checking the configuration fingerprint and the split
  definition digest. A result that does not reproduce is refused.
- Neither stage writes back to the other's result.

The frozen result is still process-local. Single-use access to held-out
outcomes is not enforced here.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from tools.research_plan_quality.models import RUBRIC_DIMENSIONS
from tools.research_plan_quality.rubric import evaluate_plan

from .errors import HarnessError
from .leakage import NEAR_DUPLICATE_THRESHOLD, SHINGLE_SIZE
from .manifest import Manifest, load_plan_records, rubric_dimensions_sha256, rubric_source_sha256, split_definition_sha256
from .records import NORMALIZATION_VERSION, PlanRecord, canonical_json, sha256_hex
from .splits import DEVELOPMENT, LOCKED_INTERNAL_VALIDATION, MIN_GROUPS_PER_ROLE, MIN_PLANS_PER_ROLE


@dataclass(frozen=True)
class StageResult:
    role: str
    config_fingerprint: str
    split_definition_sha256: str
    outcomes: tuple[dict[str, Any], ...]


def harness_configuration() -> dict[str, Any]:
    return {
        "rubric_dimension_count": len(RUBRIC_DIMENSIONS),
        "rubric_dimensions_sha256": rubric_dimensions_sha256(),
        "rubric_source_sha256": rubric_source_sha256(),
        "near_duplicate_threshold": NEAR_DUPLICATE_THRESHOLD,
        "shingle_size": SHINGLE_SIZE,
        "normalization_version": NORMALIZATION_VERSION,
        "min_plans_per_role": MIN_PLANS_PER_ROLE,
        "min_groups_per_role": MIN_GROUPS_PER_ROLE,
    }


def configuration_fingerprint() -> str:
    return sha256_hex(canonical_json(harness_configuration()).encode("utf-8"))


def _outcome(record: PlanRecord) -> dict[str, Any]:
    result = evaluate_plan(record.plan)
    return {
        "fixture_id": record.fixture_id,
        "overall_status": result.overall_status,
        "overall_score": result.overall_score,
        "non_passing_dimensions": sorted(c.dimension for c in result.criteria if c.status != "pass"),
        "evidence_class": result.evidence_class,
    }


def run_development_stage(manifest: Manifest) -> StageResult:
    """Development outcomes, computed from development plan files only."""
    records = load_plan_records(manifest, roles={DEVELOPMENT})
    outcomes = tuple(_outcome(r) for r in sorted(records, key=lambda r: r.fixture_id))
    return StageResult(
        role=DEVELOPMENT,
        config_fingerprint=configuration_fingerprint(),
        split_definition_sha256=split_definition_sha256(manifest.entries),
        outcomes=outcomes,
    )


def run_held_out_stage(manifest: Manifest, frozen: StageResult) -> StageResult:
    """Held-out outcomes. Released only if the frozen development result reproduces from the plan files."""
    if frozen.role != DEVELOPMENT:
        raise HarnessError("held-out evaluation requires the frozen development stage")
    if frozen.config_fingerprint != configuration_fingerprint():
        raise HarnessError("configuration changed after the development stage was frozen")
    definition = split_definition_sha256(manifest.entries)
    if frozen.split_definition_sha256 != definition:
        raise HarnessError("split definition changed after the development stage was frozen")
    if run_development_stage(manifest) != frozen:
        raise HarnessError("frozen development stage does not reproduce from the plan files")
    records = load_plan_records(manifest, roles={LOCKED_INTERNAL_VALIDATION})
    outcomes = tuple(_outcome(r) for r in sorted(records, key=lambda r: r.fixture_id))
    return StageResult(
        role=LOCKED_INTERNAL_VALIDATION,
        config_fingerprint=frozen.config_fingerprint,
        split_definition_sha256=definition,
        outcomes=outcomes,
    )
