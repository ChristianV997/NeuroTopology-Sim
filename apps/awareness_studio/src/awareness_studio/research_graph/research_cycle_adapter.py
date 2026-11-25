"""Reads records from a live `awareness_studio.research_cycle.ledger.ResearchCycleLedger`
and projects them into the manifest-dict shape `research_graph.loader.load_from_dict`
consumes.

Before this module existed, `research_graph` (despite its own module
docstring calling itself "the research-cycle evidence graph projection
subsystem") had **zero code-level connection** to
`awareness_studio.research_cycle` -- the two packages independently
defined their own record shapes and vocabularies with no adapter
between them. This module is that adapter: strictly read-only against
the ledger, and it never invents a stronger evidence classification
than the source record's own fields support.

`research_cycle.models.EvidenceClass` has more values than
`research_graph.types.EvidenceClass` (nine vs. five) -- the two are
NOT the same vocabulary and reconciling them fully is out of scope
here (see the vocabulary-reconciliation backlog item). This module
only ever translates the few values that have an honest equivalent;
everything else (including `HYPOTHESIS`, which every literature-derived
record uses) is deliberately left unmapped so `research_graph`'s own
`_classify_evidence` falls back to `UNKNOWN` -- never a guessed
`EMPIRICAL`.
"""
from __future__ import annotations

from typing import Any

from awareness_studio.research_cycle.ledger import ResearchCycleLedger
from awareness_studio.research_cycle.models import Claim, SourceSnapshot

# Only research_cycle EvidenceClass values with an honest, unambiguous
# research_graph equivalent are translated. Every other value (HYPOTHESIS,
# SPECULATION, ENGINEERING_FACT, BENCHMARK_RESULT, UNSUPPORTED_CLAIM) is
# intentionally absent so the resulting dict carries no evidence_class key
# at all for those records -- research_graph's own _classify_evidence then
# falls through to data_mode-based checks and finally UNKNOWN, never a
# fabricated EMPIRICAL/FORMAL.
#
# "formal_statistical_evidence" -> "formal" is shared by both sources and
# claims. research_graph._classify_evidence only accepts a bare
# evidence_class="formal" as FORMAL when the SAME manifest entry also
# carries preregistered=True and held_out_split_locked=True -- otherwise it
# downgrades to EMPIRICAL. A research_cycle Claim has no metadata field at
# all to source those two flags from, so a Claim translated this way always
# downgrades to EMPIRICAL -- but research_graph's
# EMPIRICAL_CLAIM_WITHOUT_VERIFICATION guardrail checks CLAIM nodes as well
# as SOURCE_SNAPSHOT ones precisely so that downgrade is never silent.
_EVIDENCE_CLASS_TRANSLATION: dict[str, str] = {
    "synthetic_demonstration": "synthetic",
    "proxy_inference": "proxy",
    "formal_statistical_evidence": "formal",
    "descriptive_empirical": "empirical",
}

# Metadata keys forwarded verbatim from a SourceSnapshot's own metadata,
# never fabricated -- these are exactly the signals research_graph's
# _classify_evidence (preregistered/held_out_split_locked) and
# EMPIRICAL_CLAIM_WITHOUT_VERIFICATION guardrail (the other three) look
# for. Claim has no metadata field to forward these from at all.
_SOURCE_METADATA_PASSTHROUGH_KEYS = (
    "verification_status", "peer_review_status", "review_status",
    "preregistered", "held_out_split_locked",
)

# research_cycle.models.VALID_STATUSES -> research_graph.types.NodeStatus.
# Three values (INCONCLUSIVE, BLOCKED, REVIEW_REQUIRED) share the exact
# same spelling and meaning in both vocabularies; the rest are mapped to
# their closest honest equivalent, never silently collapsed to "active"
# across the board.
_STATUS_TRANSLATION: dict[str, str] = {
    "PENDING": "proposed",
    "IN_PROGRESS": "active",
    "COMPLETED": "active",
    "INCONCLUSIVE": "inconclusive",
    "BLOCKED": "blocked",
    "FAILED": "rejected",
    "NOT_IMPLEMENTED": "blocked",
    "REVIEW_REQUIRED": "review_required",
    "FINALIZED": "active",
}


def _translate_status(research_cycle_status: str) -> str:
    return _STATUS_TRANSLATION.get(research_cycle_status, "review_required")


def _source_snapshot_to_dict(record: SourceSnapshot) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "source_id": record.snapshot_id,
        "title": record.metadata.get("literature_source_id", record.snapshot_id),
        "status": _translate_status(record.status),
        "data_mode": record.data_mode,
        "source_uri": record.source_uri,
        "source_sha256": record.source_sha256,
    }
    translated = _EVIDENCE_CLASS_TRANSLATION.get(record.evidence_class.value)
    if translated is not None:
        entry["evidence_class"] = translated
    # Pass through metadata fields that feed research_graph's
    # _classify_evidence FORMAL gate and its EMPIRICAL_CLAIM_WITHOUT_VERIFICATION
    # guardrail, if present -- never fabricated here, only forwarded if the
    # research_cycle record already carries them.
    for key in _SOURCE_METADATA_PASSTHROUGH_KEYS:
        if key in record.metadata:
            entry[key] = record.metadata[key]
    entry["scientific_limitations"] = list(record.scientific_limitations)
    entry["metadata"] = dict(record.metadata)
    return entry


def _claim_to_dict(record: Claim) -> dict[str, Any]:
    source_id = record.parent_ids[0] if record.parent_ids else (record.evidence_ids[0] if record.evidence_ids else None)
    entry: dict[str, Any] = {
        "claim_id": record.claim_id,
        "claim_text": record.statement,
        "claim_status": _translate_status(record.status),
        "scientific_limitations": list(record.scientific_limitations),
    }
    if source_id is not None:
        entry["source_id"] = source_id
    translated = _EVIDENCE_CLASS_TRANSLATION.get(record.evidence_class.value)
    if translated is not None:
        entry["evidence_class"] = translated
    return entry


def manifest_from_ledger(ledger: ResearchCycleLedger, cycle_id: str) -> dict[str, Any]:
    """Read every record in ``cycle_id`` and project sources/claims into
    the manifest-dict shape ``research_graph.loader.load_from_dict``
    consumes. Read-only: never writes to the ledger. Silently ignores
    record types this adapter doesn't yet translate (e.g. Hypothesis,
    ExperimentSpec) rather than guessing a shape for them."""
    sources: list[dict[str, Any]] = []
    claims: list[dict[str, Any]] = []
    for record in ledger.records(cycle_id):
        if isinstance(record, SourceSnapshot):
            sources.append(_source_snapshot_to_dict(record))
        elif isinstance(record, Claim):
            claims.append(_claim_to_dict(record))
    return {"sources": sources, "claims": claims}
