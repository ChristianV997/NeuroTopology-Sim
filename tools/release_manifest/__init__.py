"""Deterministic release-candidate manifest builder for NeuroTopology-Sim.

Owned exclusively by claude/release-candidate-manifest:
tools/release_manifest/**, scripts/build_release_manifest.py,
tests/release_manifest/**, docs/release/release_candidate_manifest.md.

Zero import dependency on tools/integration_state, tools/integration_reconciliation,
or governance/merge_gate (all owned by sibling branches running in
parallel this round) -- every primitive this package needs (git
plumbing, commit classification, CI-state classification) is freshly,
independently implemented here. Read-only end to end: no push/merge/
rebase/checkout -b/branch -d anywhere in this package's call graph, and
no hidden network call -- GitHub-side facts come only from an optional
pre-fetched JSON snapshot this package reads, never fetches.
"""
from __future__ import annotations
