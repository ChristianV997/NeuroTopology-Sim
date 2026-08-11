"""Operational phase-space coordinates derived from TransitionRecordV1.

A phase-space coordinate is **not a consciousness measure**. It is an
operational summary of named, measurable transition features carrying
explicit provenance, confidence, missing-feature status, limitations, and
claim scope. See `docs/phase_space_coordinates.md`.

This package consumes the transition layer only. Raw EEG/fMRI pipeline
output must be converted to a `TransitionRecordV1` before it can reach here.

Deliberately NOT implemented here: Theory Competition, Koopman/DMD,
Counterfactual Reachable Sets, phenomenology parsing, Holo-Atlas
interpretation, and the Consciousness Atlas. This package is the substrate
those would consume, not any of them.
"""
from __future__ import annotations

from phase_space.axes import AXES, AXIS_NAMES, Axis, get_axis
from phase_space.coordinate import PhaseSpaceCoordinateV1
from phase_space.estimators import estimate_axis, estimate_coordinates
from phase_space.store import PhaseSpaceStore
from phase_space.trajectory import PhaseSpaceTrajectoryV1

__all__ = [
    "AXES",
    "AXIS_NAMES",
    "Axis",
    "get_axis",
    "PhaseSpaceCoordinateV1",
    "PhaseSpaceTrajectoryV1",
    "PhaseSpaceStore",
    "estimate_axis",
    "estimate_coordinates",
]
