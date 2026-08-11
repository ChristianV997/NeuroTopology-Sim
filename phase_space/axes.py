"""Operational phase-space axes and their source-feature mappings.

An **axis is not a dimension of consciousness**. Each axis here is an
operational summary of specific, named, measurable transition features --
nothing more. The axis names are deliberately suffixed `_proxy` wherever the
quantity is an indirect stand-in for something this repository cannot
measure directly, so a reader of a bare axis name is not misled.

Every axis declares:

  * `features` -- the exact canonical `transitions.features` names it will
    read. An axis can only be estimated from features actually present in a
    `TransitionRecordV1.feature_names`; nothing is inferred or substituted.
  * `max_confidence` -- a hard per-axis ceiling (see
    `phase_space.uncertainty`). Axes whose evidentiary basis is weak are
    capped at `low` regardless of how much data is present.
  * `direction_note` -- an explicit statement that the sign/magnitude of the
    coordinate carries no valence. Higher is not "better", "healthier",
    "more conscious", or "deeper".
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field

# Reuse the repo's existing name-level firewall rather than declaring another
# copy: an axis name must clear exactly the same forbidden-token bar that
# `transitions.features` applies to feature names.
from transitions.features import FORBIDDEN_NAME_TOKENS

_NO_VALENCE = (
    "Sign and magnitude are descriptive only; they carry no valence and do "
    "not indicate better/worse, healthier/sicker, more/less conscious, or "
    "deeper/shallower states."
)


class AxisError(ValueError):
    """Raised when an axis name is unknown or fails the name-safety firewall."""


@dataclass(frozen=True)
class Axis:
    name: str
    features: tuple[str, ...]
    description: str
    max_confidence: str = "moderate"
    direction_note: str = _NO_VALENCE
    notes: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "features": list(self.features),
            "description": self.description,
            "max_confidence": self.max_confidence,
            "direction_note": self.direction_note,
            "notes": list(self.notes),
        }


AXES: dict[str, Axis] = {
    "integration": Axis(
        name="integration",
        features=(
            "connectivity.mean_plv",
            "connectivity.global_efficiency",
            "connectivity.degree",
            "connectivity.modularity",
        ),
        description=(
            "Operational summary of change in graph-level connectivity "
            "features across the transition."
        ),
        notes=(
            "connectivity.modularity moves opposite to the other three under "
            "most graph conventions (higher modularity = more segregated). "
            "v1 does NOT sign-flip it: the raw per-feature contributions are "
            "reported as-is and listed in source_features, so a downstream "
            "reader can apply their own convention rather than inherit an "
            "undocumented one from this layer.",
        ),
    ),
    "differentiation": Axis(
        name="differentiation",
        features=(
            "complexity.entropy",
            "complexity.lz_complexity",
            "topology.persistence_landscape_area",
            "topology.betti1",
            "topology.spatial_defect_betti1",
        ),
        description=(
            "Operational summary of change in signal-complexity and "
            "loop-count/persistence features across the transition."
        ),
        notes=(
            "topology.betti1 (windowed persistent-homology mean) and "
            "topology.spatial_defect_betti1 (single-snapshot spatial count) "
            "are different measurements that this axis may read together; "
            "which ones actually contributed is always recorded in "
            "source_features.",
        ),
    ),
    "metastability": Axis(
        name="metastability",
        features=(
            "dynamics.kuramoto_metastability",
            "dynamics.leida_dwell_time",
            "dynamics.transition_probability",
            "transition.variance",
        ),
        description=(
            "Operational summary of change in dynamical-variability features "
            "across the transition."
        ),
    ),
    "accessibility_proxy": Axis(
        name="accessibility_proxy",
        features=(
            "complexity.pcist_proxy",
            "transition.hysteresis",
            "transition.velocity",
        ),
        description=(
            "Indirect operational proxy built from perturbational-complexity-"
            "style and path-asymmetry features. This is NOT a consciousness "
            "level, awareness measure, or responsiveness score."
        ),
        max_confidence="low",
        notes=(
            "Capped at 'low' confidence in v1 unconditionally: a defensible "
            "accessibility estimate would require direct perturbational "
            "(e.g. TMS-EEG) or behavioural-response evidence, and this layer "
            "has no mechanism to detect or verify either.",
        ),
    ),
    "precision_stability_proxy": Axis(
        name="precision_stability_proxy",
        features=(
            "qc.signal_quality",
            "transition.variance",
            "dynamics.kuramoto_r",
        ),
        description=(
            "Indirect operational proxy built from signal-quality and "
            "phase-consistency features. Note this axis mixes recording-"
            "quality and neural-dynamics features, so it is partly a "
            "measurement-stability summary, not purely a brain-state one."
        ),
        max_confidence="low",
        notes=(
            "Capped at 'low' confidence in v1 unconditionally: task-structure "
            "or prediction-error features would be required for a stronger "
            "reading, and none are available through this layer.",
            "qc.* features describe the recording, not the brain; a change in "
            "this axis may reflect data quality rather than physiology.",
        ),
    ),
    "topological_organization": Axis(
        name="topological_organization",
        features=(
            "topology.q_abs",
            "topology.q_net",
            "topology.f_dress",
            "topology.defect_density",
            "topology.betti1",
            "topology.spatial_defect_betti1",
            "topology.h1_persistence",
            "topology.bottleneck_distance",
            "topology.persistence_landscape_area",
        ),
        description=(
            "Operational summary of change in the topological feature family "
            "(winding/charge, defect density, Betti-style counts, persistence "
            "summaries) across the transition."
        ),
        notes=(
            "This axis deliberately spans several distinct topological "
            "measurement methods; source_features records exactly which ones "
            "contributed for any given coordinate.",
        ),
    ),
    "temporal_continuity": Axis(
        name="temporal_continuity",
        features=(
            "transition.velocity",
            "transition.acceleration",
            "transition.dwell_time",
            "transition.hysteresis",
        ),
        description=(
            "Operational summary of change in rate-of-change and "
            "path-asymmetry features across the transition."
        ),
    ),
    "generative_depth_proxy": Axis(
        name="generative_depth_proxy",
        features=("phenomenology.generative_depth",),
        description=(
            "Placeholder axis reserved for future phenomenological input. "
            "This repository has no phenomenology parser and produces no "
            "phenomenology.* features, so this axis returns insufficient_data "
            "in practice."
        ),
        max_confidence="low",
        notes=(
            "Expected to return insufficient_data for every record this "
            "repository can currently produce. It is registered so the axis "
            "name is reserved and documented, NOT because it is estimable.",
        ),
    ),
    "self_model_proxy": Axis(
        name="self_model_proxy",
        features=("phenomenology.self_reference",),
        description=(
            "Placeholder axis reserved for future explicit self-report or "
            "self-reference task markers. No such features are produced by "
            "this repository, so this axis returns insufficient_data in "
            "practice."
        ),
        max_confidence="low",
        notes=(
            "Expected to return insufficient_data for every record this "
            "repository can currently produce. Registering the name does not "
            "imply any capacity to detect selfhood, self-awareness, or "
            "self-modelling.",
        ),
    ),
}

AXIS_NAMES: tuple[str, ...] = tuple(AXES)

# Axes that are structurally expected to be unestimable with the feature
# families this repository currently produces. Used by tests and docs to
# assert honest behaviour rather than silent guessing.
PLACEHOLDER_AXES: frozenset[str] = frozenset(
    {"generative_depth_proxy", "self_model_proxy"}
)


def _normalize(name: str) -> str:
    folded = unicodedata.normalize("NFKD", name or "")
    folded = "".join(ch for ch in folded if not unicodedata.combining(ch))
    return folded.strip().lower().replace("-", "_").replace(" ", "_")


def validate_axis_name(name: str) -> None:
    """Raise AxisError if `name` is unsafe or not a registered axis.

    Applies the same forbidden-token firewall used for feature names, so an
    axis can never be introduced whose *name alone* asserts a diagnostic,
    clinical, or contemplative-attainment claim -- even by a caller passing
    an arbitrary string.
    """
    if not name or not isinstance(name, str):
        raise AxisError("axis name must be a non-empty string")

    normalized = _normalize(name)
    for token in FORBIDDEN_NAME_TOKENS:
        if token in normalized:
            raise AxisError(
                f"axis name '{name}' contains forbidden token '{token}' -- axis "
                "names must not imply diagnosis, treatment, clinical biomarker "
                "status, consciousness detection, or contemplative "
                "attainment/cessation/enlightenment detection"
            )

    if name not in AXES:
        raise AxisError(
            f"unknown axis '{name}'; registered axes: {sorted(AXES)}"
        )


def get_axis(name: str) -> Axis:
    validate_axis_name(name)
    return AXES[name]


def axis_feature_map() -> dict[str, list[str]]:
    """The explicit axis -> source-feature mapping, for docs and tests."""
    return {name: list(axis.features) for name, axis in AXES.items()}
