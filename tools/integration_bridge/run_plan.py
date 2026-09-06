"""Build an ordered analysis plan from discovered capabilities and the
requested metadata — a plan is a description of what will be invoked, not
an invocation. ``scripts/assemble_ecosystem_run.py``'s ``analyze`` stage
executes the plan by calling the named public adapters directly; nothing
in this module performs numerical work itself.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass(frozen=True)
class SignalHandle:
    """Local placeholder for the interop signal contract expected from the
    (currently unavailable) codex/interop-signal-contracts branch — see
    configs/integration/dependency_matrix.yaml. Intentionally the only
    place this shape is defined so a real contract can replace it in one
    file.
    """

    array: Any  # numpy.ndarray; typed Any so this module stays numpy-optional
    sample_rate_hz: float
    source_kind: str  # "synthetic_demo" | "empirical_local" | "empirical_csv"
    dataset_id: str
    seed: int


@dataclass(frozen=True)
class PlanStep:
    name: str
    adapter: str  # key into capabilities.ADAPTER_REQUIREMENTS
    reason_if_skipped: Optional[str] = None


@dataclass(frozen=True)
class RunPlan:
    steps: Tuple[PlanStep, ...]
    skipped: Tuple[PlanStep, ...]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "steps": [step.__dict__ for step in self.steps],
            "skipped": [step.__dict__ for step in self.skipped],
        }


# The full candidate set of analysis steps this integration knows how to
# request. Order matters only in that spatial/graph/chirality metrics are
# independent of each other and of the falsification gate, which always
# runs last since it consumes the macro signal directly, not their output.
_CANDIDATE_STEPS: Tuple[PlanStep, ...] = (
    PlanStep("spatial_winding_and_charge", "spatial_topology"),
    PlanStep("graph_beta1", "graph_beta1"),
    PlanStep("scalar_chirality_and_beta1_proxy", "scalar_chirality"),
    PlanStep("bayesian_falsification", "bayesian_falsification"),
)


def build_plan(
    adapters_available: Dict[str, bool],
    requested_steps: Optional[Tuple[str, ...]] = None,
) -> RunPlan:
    """Select which candidate steps actually run, given availability and an
    optional explicit subset requested by the caller (default: all
    candidates). A step whose required optional packages are missing is
    moved to ``skipped`` with a stated reason — it is never silently
    dropped."""
    candidates = _CANDIDATE_STEPS
    if requested_steps is not None:
        wanted = set(requested_steps)
        candidates = tuple(step for step in candidates if step.name in wanted)

    steps: List[PlanStep] = []
    skipped: List[PlanStep] = []
    for step in candidates:
        if adapters_available.get(step.adapter, False):
            steps.append(step)
        else:
            skipped.append(
                PlanStep(
                    step.name,
                    step.adapter,
                    reason_if_skipped=(
                        f"adapter '{step.adapter}' unavailable: required "
                        "optional dependency not installed"
                    ),
                )
            )
    return RunPlan(steps=tuple(steps), skipped=tuple(skipped))
