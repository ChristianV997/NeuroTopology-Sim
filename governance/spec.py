"""
Dataclasses for HypothesisSpec — Awareness Research v0.2 governance.

A HypothesisSpec encodes a single hypothesis run with all metadata needed
for machine-checkable governance:
  - claim_type: M (Marker), K (Known), C (Causal)
  - K/C require discriminator, controls, and readouts
  - C also requires alternatives_considered and non-empty pass_fail.thresholds
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Discriminator:
    description: str
    mode: str  # "stimulus_sweep" | "dataset_contrast" | "transition_probe"
    config: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Readout:
    name: str
    module: str = ""


@dataclass
class Control:
    name: str
    config: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DataSpec:
    mode: str  # "openneuro" | "synthetic" | "external" | "tribe_future"
    dataset_id: str = ""
    params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PassFail:
    criteria: str = ""
    thresholds: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ArtifactsSpec:
    expected: List[str] = field(default_factory=list)


@dataclass
class HypothesisSpec:
    """Full hypothesis specification for governance-gated runs."""

    id: str
    title: str
    claim_type: str  # "M" | "K" | "C"
    layer: str       # "Marker" | "Topology" | "Substrate"
    summary: str

    discriminator: Optional[Discriminator] = None
    readouts: List[Readout] = field(default_factory=list)
    controls: List[Control] = field(default_factory=list)

    data: Optional[DataSpec] = None
    pass_fail: PassFail = field(default_factory=PassFail)
    artifacts: ArtifactsSpec = field(default_factory=ArtifactsSpec)

    # Required for claim_type == "C"
    alternatives_considered: List[str] = field(default_factory=list)
