"""Deterministic, template-based evidence reports.

See docs/evidence_report_generator.md for the full rationale. This package
consumes `evidence.bundle.EvidenceBundleV1` and renders it into a
human-readable `EvidenceReportV1` (Markdown/JSON) -- no LLM call, no
scientific recomputation, no randomness. It does not implement Theory
Competition, Koopman/DMD, Counterfactual Reachable Sets, a Phenomenology
parser, the Holo-Atlas interpreter, or a Consciousness Atlas.

`reports.export_report` (the CLI) is deliberately NOT re-exported here:
eagerly importing a CLI module from this package's __init__ causes Python
to double-import it under `-m`, exactly the problem `phase_space/__init__.py`,
`benchmarks/__init__.py`, and `evidence/__init__.py` already avoid for their
own CLI modules. Import it directly:
`from reports.evidence_report import build_report`.
"""
from __future__ import annotations

from reports.evidence_report import EvidenceReportV1

__all__ = ["EvidenceReportV1"]
