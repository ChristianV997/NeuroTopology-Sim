"""Offline-first Awareness Studio evidence registry.

Owned exclusively by claude/awareness-studio-evidence-registry:
tools/awareness_studio_research/**, scripts/awareness_studio_research.py,
tests/awareness_studio_research/**, docs/awareness_studio/research_evidence_registry.md.

Zero import dependency on apps/awareness_studio (UI/FastAPI routes),
tools/literature_senses, or any other sibling package -- every primitive
this package needs (checksum, dedup, event log, query) is freshly,
independently implemented here.

This registry is a research *record*, not an autonomous authority: it
never asserts that a claim is true, never silently rewrites history, and
never fetches over the network unless a caller explicitly opts in
(`allow_network=True`). Default behavior end to end is offline, reading
only local fixtures/operator-supplied metadata.
"""
from __future__ import annotations
