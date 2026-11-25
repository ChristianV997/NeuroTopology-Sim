"""Read-only post-integration scientific-release audit for NeuroTopology-Sim.

Owned exclusively by claude/integrated-scientific-release-audit:
tools/release_scientific_audit/**, scripts/audit_integrated_release.py,
tests/release_scientific_audit/**, docs/release/scientific_release_audit.md.

This package has zero import dependency on tools/integration_reconciliation,
governance/merge_gate, or sim/pitnn/bayesian_falsification -- it consumes
already-produced report documents (JSON) describing their outputs, never
their live code. It performs no scientific computation of its own and
never adjusts a scientific verdict to make a release look better.
"""
from __future__ import annotations
