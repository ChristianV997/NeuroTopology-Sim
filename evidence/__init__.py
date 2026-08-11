"""Governed evidence bundles: the durable link between registry
authorization, TransitionRecordV1 artifacts, and PhaseSpaceCoordinateV1
artifacts for one source dataset/artifact.

See docs/governed_evidence_bundles.md for the full rationale. This package
orchestrates the existing `transitions/`, `phase_space/`, and `benchmarks/`
substrates -- it does not reimplement any of their logic, and it does not
implement Theory Competition, Koopman/DMD, Counterfactual Reachable Sets, a
Phenomenology parser, the Holo-Atlas interpreter, or a Consciousness Atlas.
A governed evidence bundle is still not a theory result: it is a
reproducible artifact manifest that future consumers should read instead of
guessing which transitions/coordinates/registry records/artifacts belong
together.

`evidence.builder` (the CLI, `evidence.export_bundle`) is deliberately NOT
re-exported here: eagerly importing a CLI module from this package's
__init__ causes Python to double-import it under `-m`, exactly the problem
`phase_space/__init__.py` and `benchmarks/__init__.py` already avoid for
their own CLI modules. Import it directly:
`from evidence.builder import build_evidence_bundle`.
"""
from __future__ import annotations

from evidence.bundle import EvidenceBundleV1
from evidence.store import EvidenceBundleStore

__all__ = ["EvidenceBundleV1", "EvidenceBundleStore"]
