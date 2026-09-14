"""Deterministic, read-only preflight that composes existing research-plan,
claim, provenance, artifact, and data-access validators before any
expensive simulation is launched.

This package does not reimplement any of those validators. It imports
and calls them exactly as published:

- ``tools.research_plan_quality`` -- the 20-dimension research plan rubric.
- ``tools.research_claim_gate`` -- the scientific claim gate.
- ``tools.simulation_artifacts`` -- the read-only simulation-artifact
  lineage extractor.
- ``tools.data_access.policy_enforcement.policy`` -- the declared
  data-access policy (read as a reference contract, never mutated).

See ``docs/research/research_cycle_preflight.md`` for the full
requirement-by-requirement mapping.
"""
