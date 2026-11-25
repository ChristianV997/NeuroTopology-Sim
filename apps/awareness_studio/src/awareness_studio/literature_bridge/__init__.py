"""Bridges `tools/literature_evidence` (a repo-root, read-only canonical
producer) into Awareness Studio's research-cycle input schema
(`awareness_studio.research_cycle.models`) as an input-only evidence
stream for hypotheses and research planning.

Owned exclusively by claude/awareness-studio-literature-bridge:
apps/awareness_studio/src/awareness_studio/literature_bridge/**,
apps/awareness_studio/tests/literature_bridge/**,
docs/awareness_studio/literature_bridge.md.

This package never modifies `tools/literature_evidence/**` or
`awareness_studio.research_cycle/**` -- it only imports (reads) from
both, and never writes to the research-cycle ledger itself (a caller
outside this package's scope owns actually appending the records this
bridge produces).

**This is an evidence-ingestion bridge, not scientific confirmation.**
A literature source or claim that maps cleanly through this bridge is,
at most, a well-formed `SourceSnapshot`/`Hypothesis` input to a research
cycle -- never a `Claim`, `EvidenceRecord`, or any other confirmed-result
type. `research_cycle.models`'s own guardrails (data_mode/evidence_class
consistency checks) are relied upon, never bypassed: this bridge never
constructs a record with `data_mode="empirical"`, never claims
`EvidenceClass.FORMAL_STATISTICAL_EVIDENCE`, and never resolves an
identifier over the network (identifier resolution is
`tools.literature_evidence`'s job, and only ever opt-in there).
"""
from __future__ import annotations

