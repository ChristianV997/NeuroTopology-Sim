"""Shared vocabulary for the research-cycle preflight.

Two decision axes are kept explicitly separate, per this task's
requirement: an *operational* readiness state (is it safe to spend
compute on this plan?) and a *scientific* admissibility state (would the
claim this cycle intends to report be admissible to the claim gate?).
Neither axis is a scientific conclusion, and the two are never merged
into one status so that a caller cannot mistake "safe to run" for
"proven true".
"""
from __future__ import annotations

OPERATIONAL_READINESS_STATES: tuple[str, ...] = ("READY", "NEEDS_REVISION", "BLOCKED")

SCIENTIFIC_ADMISSIBILITY_STATES: tuple[str, ...] = (
    "ADMISSIBLE",
    "REVIEW_REQUIRED",
    "DOWNGRADED",
    "BLOCKED",
    "INCOMPLETE",
    "NOT_APPLICABLE",
)

# Decisions this preflight is structurally forbidden from producing,
# regardless of what a caller's input claims about itself. Every report
# carries these literal values so a downstream reader never has to trust
# that they were merely omitted.
NEVER_EMITTED: dict[str, object] = {
    "scientific_pass": False,
    "formal_bayes_factor": None,
    "causal_confirmation": False,
    "biological_confirmation": False,
    "topology_confirmation": False,
}

SCHEMA_VERSION = "NeuroTopology.ResearchCyclePreflight.v1"
