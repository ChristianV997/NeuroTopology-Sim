"""Fixed allowlist of repository-owned callables for Batch 3 offline integration.

The harness never executes arbitrary commands from a manifest, never imports
harvested code, and never resolves callables by free-form strings at runtime
beyond this table.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, Optional, Tuple


@dataclass(frozen=True)
class StageSpec:
    stage_id: str
    order: int
    title: str
    module: str
    qualname: str
    required: bool
    depends_on: Tuple[str, ...]
    optional_dependency: bool = False
    # When True, the stage is an in-package fixture producer (not an upstream callable).
    is_fixture_producer: bool = False
    source_version_key: str = "module"


# Ordered synthetic research workflow stages composed from merged-main tools.
STAGE_SPECS: Tuple[StageSpec, ...] = (
    StageSpec(
        stage_id="load_synthetic_fixture",
        order=10,
        title="Load local synthetic workflow fixtures",
        module="tools.batch3_offline_integration.fixture_producers",
        qualname="load_workflow_request",
        required=True,
        depends_on=(),
        is_fixture_producer=True,
    ),
    StageSpec(
        stage_id="plan_quality",
        order=20,
        title="Research plan quality rubric",
        module="tools.research_plan_quality.rubric",
        qualname="evaluate_plan",
        required=True,
        depends_on=("load_synthetic_fixture",),
    ),
    StageSpec(
        stage_id="claim_gate",
        order=30,
        title="Scientific claim admissibility gate",
        module="tools.research_claim_gate.gate",
        qualname="evaluate_claim",
        required=True,
        depends_on=("load_synthetic_fixture",),
    ),
    StageSpec(
        stage_id="preflight",
        order=40,
        title="Research-cycle preflight composition",
        module="tools.research_cycle_preflight.compose",
        qualname="run_preflight",
        required=True,
        depends_on=("load_synthetic_fixture", "plan_quality", "claim_gate"),
    ),
    StageSpec(
        stage_id="registry_probe",
        order=50,
        title="Research-cycle registry register (synthetic)",
        module="tools.research_cycle.registry",
        qualname="ResearchCycleRegistry",
        required=True,
        depends_on=("preflight",),
    ),
    StageSpec(
        stage_id="release_evaluate",
        order=60,
        title="Research-cycle release evidence evaluate",
        module="tools.research_cycle_release.evaluator",
        qualname="evaluate_research_cycle_release",
        required=True,
        depends_on=("registry_probe",),
    ),
    StageSpec(
        stage_id="optional_artifact_lineage",
        order=70,
        title="Optional simulation artifact lineage",
        module="tools.simulation_artifacts.extractor",
        qualname="extract_run",
        required=False,
        depends_on=("load_synthetic_fixture",),
        optional_dependency=True,
    ),
)

STAGE_BY_ID: Dict[str, StageSpec] = {spec.stage_id: spec for spec in STAGE_SPECS}
STAGE_ORDER: Tuple[str, ...] = tuple(spec.stage_id for spec in STAGE_SPECS)


def resolve_callable(spec: StageSpec) -> tuple[Optional[Callable[..., object]], Optional[str]]:
    """Import an allowlisted callable. Returns (callable, missing_reason)."""
    try:
        import importlib

        module = importlib.import_module(spec.module)
    except Exception as exc:  # pragma: no cover - defensive
        return None, f"import_failed:{spec.module}:{type(exc).__name__}"
    target = module
    for part in spec.qualname.split("."):
        target = getattr(target, part, None)
        if target is None:
            return None, f"attr_missing:{spec.module}.{spec.qualname}"
    if not callable(target) and not isinstance(target, type):
        return None, f"not_callable:{spec.module}.{spec.qualname}"
    return target, None  # type: ignore[return-value]


def assert_stage_allowlisted(stage_id: str) -> StageSpec:
    if stage_id not in STAGE_BY_ID:
        raise KeyError(f"stage_id not in fixed allowlist: {stage_id}")
    return STAGE_BY_ID[stage_id]
