"""Canonical, governance-aware representation of state transitions.

See docs/transition_science_foundation.md for the full rationale. This
package is deliberately narrow: it defines a durable artifact schema
(`TransitionRecordV1`), a feature-namespace validator, a claim/evidence
governance validator, generic trajectory metrics, a filesystem store, and a
CLI exporter from existing metric outputs. It does not implement any
downstream consumer (phase space, theory competition, Koopman/DMD,
counterfactual reachability, phenomenology, or the holo-atlas interpreter).
"""
from __future__ import annotations

from transitions.record import TransitionRecordV1
from transitions.store import TransitionStore

__all__ = ["TransitionRecordV1", "TransitionStore"]
