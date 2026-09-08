"""Read-only authoritative integration-state verifier for NeuroTopology-Sim.

Owned exclusively by claude/integration-state-lock:
tools/integration_state/**, scripts/verify_integration_state.py,
tests/integration_state/**, docs/release/integration_state_lock.md.

Zero import dependency on tools/integration_reconciliation or
governance/merge_gate. Local git facts come from real, read-only git
plumbing (never a mutating verb); GitHub-side facts come from an
optional pre-fetched JSON snapshot this package only ever reads, never
fetches itself -- so its unit tests need no network.
"""
from __future__ import annotations
