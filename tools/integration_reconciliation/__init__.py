"""Read-only integration reconciliation for NeuroTopology-Sim.

Owned exclusively by claude/integration-reconciliation
(tools/integration_reconciliation/**,
scripts/verify_integration_reconciliation.py,
tests/integration_reconciliation/**, docs/integration_reconciliation/**).

Every function in this package is read-only: it inspects git history and
(optionally) a previously-fetched GitHub metadata snapshot, and produces a
report. Nothing here pushes, merges, closes, rebases, or deletes a branch,
and nothing here edits any file outside its own owned paths.
"""
from __future__ import annotations
