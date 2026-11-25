"""Local-first literature evidence adapter for Awareness Studio.

Owned exclusively by claude/literature-evidence-adapter:
tools/literature_evidence/**, scripts/validate_literature_evidence.py,
tests/literature_evidence/**, docs/awareness_studio/literature_evidence.md.

Zero import dependency on the Awareness Studio orchestrator, the
research-cycle ledger, tools/research_claim_gate, tools/awareness_studio_research
(a separate, already-merged sibling package with a similar aim), or any
other package owned by another agent -- every primitive this package
needs (checksum, identifier validation, event log) is freshly,
independently implemented here, per this session's established
zero-cross-dependency convention for parallel-built tools.

This adapter records literature *identity* and *claims about it* --
it never adjudicates truth. Source identity (`LiteratureRecord`) is
kept structurally separate from claims (`ClaimRecord`): a claim always
references a source by id but is never merged into the source record
itself. Most importantly, this package can never promote a claim into
confirmed empirical evidence: `CLAIM_KINDS` and `EVIDENCE_CLASSES`
(see models.py) simply do not include an "empirical"/"confirmed" value
at all -- every claim defaults to, and can only ever be, a hypothesis
or a review-required item. Promotion to empirical status, if it ever
happens, is necessarily a decision made by a separate system this
package does not implement.

Network access is opt-in only: nothing in this package calls the
network unless a caller explicitly passes ``allow_network=True`` to a
function in ``network.py``. Default behavior end to end is fully local
and offline.
"""
from __future__ import annotations
