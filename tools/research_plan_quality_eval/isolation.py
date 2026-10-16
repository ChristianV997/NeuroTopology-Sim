"""Development / held-out access control.

The harness fits and tunes nothing. Its configuration is the rubric source
identity plus fixed constants (duplicate threshold, shingle size,
normalisation version, minimum split sizes). That configuration is
fingerprinted.

- Development-stage code refuses held-out records outright.
- Held-out evaluation runs only against an already-frozen development stage,
  checks that the configuration fingerprint still matches, and returns a new
  result. It never writes back to the development result.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from tools.research_plan_quality.models import RUBRIC_DIMENSIONS
from tools.research_plan_quality.rubric import evaluate_plan

from .errors import HarnessError, HeldOutAccessError
from .leakage import NEAR_DUPLICATE_THRESHOLD, SHINGLE_SIZE
from .manifest import rubric_dimensions_sha256, rubric_source_sha256
from .records import NORMALIZATION_VERSION, PlanRecord, canonical_json, sha256_hex
from .splits import DEVELOPMENT, LOCKED_INTERNAL_VALIDATION, MIN_GROUPS_PER_ROLE, MIN_PLANS_PER_ROLE


@dataclass(frozen=True)
class StageResult:
    role: str
    config_fingerprint: str
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


def run_development_stage(records: Sequence[PlanRecord]) -> StageResult:
    leaked = sorted(r.fixture_id for r in records if r.split != DEVELOPMENT)
    if leaked:
        raise HeldOutAccessError(f"development stage received held-out records: {leaked}")
    outcomes = tuple(_outcome(r) for r in sorted(records, key=lambda r: r.fixture_id))
    return StageResult(role=DEVELOPMENT, config_fingerprint=configuration_fingerprint(), outcomes=outcomes)


def run_held_out_stage(records: Sequence[PlanRecord], frozen: StageResult) -> StageResult:
    if frozen.role != DEVELOPMENT:
        raise HarnessError("held-out evaluation requires the frozen development stage")
    if frozen.config_fingerprint != configuration_fingerprint():
        raise HarnessError("configuration changed after the development stage was frozen")
    mismatched = sorted(r.fixture_id for r in records if r.split != LOCKED_INTERNAL_VALIDATION)
    if mismatched:
        raise HeldOutAccessError(f"held-out stage received non-held-out records: {mismatched}")
    outcomes = tuple(_outcome(r) for r in sorted(records, key=lambda r: r.fixture_id))
    return StageResult(role=LOCKED_INTERNAL_VALIDATION, config_fingerprint=frozen.config_fingerprint, outcomes=outcomes)
