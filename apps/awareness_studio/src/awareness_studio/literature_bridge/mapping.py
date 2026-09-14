"""Maps validated `tools.literature_evidence` records into
`awareness_studio.research_cycle` typed input records.

Every public function here is a pure, side-effect-free mapping: it
reads a literature-evidence record (and, for sources, calls that
package's own `validate_record` -- never re-implementing or loosening
its checks), and either returns a `BridgeOutcome` wrapping a research-cycle
record ready for a caller to append to a cycle's ledger, or returns a
`BridgeOutcome` explaining exactly why bridging was refused. Nothing here
appends to the ledger itself, resolves an identifier over the network,
or invents a checksum/limitation that the source record doesn't already
carry.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from .repo_paths import ensure_repo_root_importable

ensure_repo_root_importable()

from tools.literature_evidence.models import (  # noqa: E402
    ClaimRecord,
    LiteratureRecord,
    SourceSnapshot as LiteratureSourceSnapshot,
)
from tools.literature_evidence.validation import validate_record  # noqa: E402

from awareness_studio.research_cycle.models import (
    Claim,
    EvidenceClass,
    ResearchCycleError,
    SourceSnapshot,
)

BRIDGE_SCHEMA_VERSION = "awareness-studio-literature-bridge.v1"

BRIDGE_STATUSES = frozenset({"bridged", "not_bridged"})

# Literature-evidence data is never itself experimental data collected by
# this repository's own pipelines -- this fixed value never triggers
# research_cycle.models's "synthetic_demo"/"empirical" promotion checks.
_LITERATURE_DATA_MODE = "literature_metadata"

# Every literature_evidence evidence_class describes something that is,
# at best, hypothesis-generating input -- never confirmed evidence about
# this repository's own experiments. "proxy" is the one value with a
# direct research_cycle analogue; everything else maps to HYPOTHESIS.
_EVIDENCE_CLASS_MAP: dict[str, EvidenceClass] = {
    "hypothesis": EvidenceClass.HYPOTHESIS,
    "theoretical": EvidenceClass.HYPOTHESIS,
    "review_required": EvidenceClass.HYPOTHESIS,
    "proxy": EvidenceClass.PROXY_INFERENCE,
}

_CLAIM_KIND_TO_STATUS: dict[str, str] = {
    "hypothesis": "PENDING",
    "review_required": "REVIEW_REQUIRED",
}


@dataclass(frozen=True)
class BridgeOutcome:
    """The result of attempting to bridge one literature-evidence record.
    ``record`` is populated only when ``status == "bridged"``."""

    status: str
    reason: str
    record: Optional[dict[str, Any]]
    preserved_state: dict[str, Any]

    def __post_init__(self) -> None:
        if self.status not in BRIDGE_STATUSES:
            raise ValueError(f"unrecognized bridge status: {self.status!r}")
        if self.status == "bridged" and self.record is None:
            raise ValueError("a 'bridged' outcome must carry a record")
        if self.status == "not_bridged" and self.record is not None:
            raise ValueError("a 'not_bridged' outcome must not carry a record")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": BRIDGE_SCHEMA_VERSION,
            "status": self.status,
            "reason": self.reason,
            "record": self.record,
            "preserved_state": self.preserved_state,
        }


def _not_bridged(reason: str, preserved_state: dict[str, Any]) -> BridgeOutcome:
    return BridgeOutcome(status="not_bridged", reason=reason, record=None, preserved_state=preserved_state)


def _bridged(record: dict[str, Any], preserved_state: dict[str, Any]) -> BridgeOutcome:
    return BridgeOutcome(status="bridged", reason="ok", record=record, preserved_state=preserved_state)


def _source_limitations(record: LiteratureRecord) -> tuple[str, ...]:
    """Synthesize scientific_limitations text from fields the source
    record already carries -- never a new fact, only a restatement of
    what publication_type/review_status/evidence_class already say."""
    limitations = [
        "Literature source snapshot only; not experimental evidence produced by NeuroTopology-Sim.",
        f"publication_type={record.publication_type!r}.",
        f"review_status={record.review_status!r}.",
    ]
    if record.publication_type == "preprint":
        limitations.append("Preprint: has not undergone peer review.")
    if record.publication_type == "theory_paper":
        limitations.append("Theory paper: presents a theoretical framework, not an empirical result.")
    if record.review_status in ("unreviewed", "review_required"):
        limitations.append("Not yet independently reviewed by this repository's own process.")
    if record.review_status == "disputed":
        limitations.append("Marked disputed in the source literature-evidence record.")
    if record.evidence_class == "proxy":
        limitations.append("Source is itself flagged as proxy evidence, not a direct/formal measurement.")
    return tuple(limitations)


def _preserved_source_state(record: LiteratureRecord, validation_state: str) -> dict[str, Any]:
    return {
        "identifier_validation_state": validation_state,
        "source_status": record.status,
        "review_status": record.review_status,
        "evidence_class": record.evidence_class,
        "publication_type": record.publication_type,
        "has_content_checksum": record.content_checksum is not None,
        "has_excerpt_hash": record.excerpt_hash is not None,
        "superseded_by": record.superseded_by,
    }


def bridge_source(
    record: LiteratureRecord,
    *,
    cycle_id: str,
    snapshot: Optional[LiteratureSourceSnapshot] = None,
) -> BridgeOutcome:
    """Attempt to map one `LiteratureRecord` (identity only, never a
    claim) into a research_cycle `SourceSnapshot`.

    Always calls `tools.literature_evidence.validation.validate_record`
    itself -- this bridge never re-validates more loosely than the
    canonical producer does. Refuses (returns `not_bridged`, never
    fabricates a value) when: identifier validation did not pass;
    the source's own lifecycle status is not "active" (preserves
    disputed/superseded/retracted as an explicit, visible reason); or
    no checksum is available at all (preserves the missing-snapshot
    state instead of inventing one).
    """
    if snapshot is not None and snapshot.source_id != record.source_id:
        return _not_bridged(
            f"snapshot_source_mismatch: snapshot.source_id={snapshot.source_id!r} "
            f"record.source_id={record.source_id!r}",
            _preserved_source_state(record, "source_snapshot_mismatch"),
        )
    validation = validate_record(record, snapshot)
    preserved = _preserved_source_state(record, validation.state)

    if validation.state != "valid":
        return _not_bridged(f"identifier_validation_state={validation.state}", preserved)

    if record.status != "active":
        return _not_bridged(f"source_status={record.status}", preserved)

    checksum = None
    if snapshot is not None and snapshot.kind == "full_local_snapshot" and snapshot.content_checksum:
        checksum = snapshot.content_checksum
    elif record.content_checksum:
        checksum = record.content_checksum
    elif record.excerpt_hash:
        checksum = record.excerpt_hash

    if not checksum:
        return _not_bridged("missing_snapshot: no content checksum or excerpt hash is available", preserved)

    source_uri = record.source_url or f"urn:literature-evidence:{record.identifier_type}:{record.identifier}"
    evidence_class = _EVIDENCE_CLASS_MAP.get(record.evidence_class, EvidenceClass.HYPOTHESIS)

    try:
        bridged = SourceSnapshot(
            snapshot_id=f"lit-source-{record.source_id}",
            cycle_id=cycle_id,
            source_uri=source_uri,
            source_sha256=checksum,
            data_mode=_LITERATURE_DATA_MODE,
            evidence_class=evidence_class,
            claim_scope=(
                f"Literature source identity snapshot for {record.title!r} "
                f"({record.identifier_type}:{record.identifier}); input for hypothesis "
                "generation and research planning only."
            ),
            scientific_limitations=_source_limitations(record),
            source_format=record.publication_type,
            captured_at=record.retrieval_timestamp,
            metadata={
                "literature_source_id": record.source_id,
                "identifier": record.identifier,
                "identifier_type": record.identifier_type,
                "authors": list(record.authors),
                "venue": record.venue,
                "publication_date": record.publication_date,
                "citation_relations": [r.to_dict() for r in record.citation_relations],
            },
        )
    except ResearchCycleError as exc:
        return _not_bridged(f"research_cycle_rejected: {exc}", preserved)

    return _bridged(bridged.to_dict(), preserved)


def bridge_claim(
    claim: ClaimRecord,
    *,
    cycle_id: str,
    source_snapshot_id: str,
) -> BridgeOutcome:
    """Map one literature `ClaimRecord` into a research_cycle `Claim`
    that is hypothesis-generating input, never confirmed evidence: its
    ``evidence_class`` is always ``EvidenceClass.HYPOTHESIS`` (literature
    ingestion never emits ``PROXY_INFERENCE``, ``FORMAL_STATISTICAL_EVIDENCE``,
    or any confirmed-empirical class), and its sole ``evidence_ids`` entry
    is the literature source's own `SourceSnapshot` id -- i.e. "the
    evidence that this claim was made in the literature is the citation
    itself," never evidence that the claim is *true*.

    A claim whose lifecycle ``status`` is not "active" (e.g. disputed) is
    refused, preserving that state explicitly rather than bridging it
    silently. A claim downgraded from ``hypothesis`` to
    ``review_required`` (via the literature-evidence store's own
    ``mark_claim_review_required``) maps to ``Claim.status =
    "REVIEW_REQUIRED"`` instead of "PENDING" -- the downgrade is
    preserved, not lost.
    """
    preserved = {
        "claim_status": claim.status,
        "claim_kind": claim.claim_kind,
        "claim_version": claim.version,
    }

    expected_snapshot_id = f"lit-source-{claim.source_id}"
    if source_snapshot_id != expected_snapshot_id:
        return _not_bridged(
            f"source_snapshot_mismatch: expected {expected_snapshot_id}",
            preserved,
        )

    if claim.status != "active":
        return _not_bridged(f"claim_status={claim.status}", preserved)

    mapped_status = _CLAIM_KIND_TO_STATUS.get(claim.claim_kind)
    if mapped_status is None:
        # Unreachable given ClaimRecord's own construction-time invariant,
        # but never silently coerced if literature_evidence's vocabulary
        # ever grows without this map being updated.
        return _not_bridged(f"unmapped_claim_kind={claim.claim_kind}", preserved)

    limitations = [
        "A claim derived from literature ingestion is not evidence until independently tested.",
        f"Derived from a literature claim (claim_kind={claim.claim_kind!r}); "
        "not itself an empirical, causal, or biologically confirmed finding.",
    ]
    if claim.confidence is not None:
        limitations.append(f"Source claim carried an informal confidence value of {claim.confidence!r}.")
    if claim.notes:
        limitations.append(f"Source claim notes: {claim.notes}")

    try:
        bridged = Claim(
            claim_id=f"lit-claim-{claim.claim_id}",
            cycle_id=cycle_id,
            statement=claim.claim_text,
            evidence_ids=(source_snapshot_id,),
            evidence_class=EvidenceClass.HYPOTHESIS,
            claim_scope=(
                "Claim proposed by literature ingestion; input for hypothesis generation "
                "and research planning only -- not empirical evidence, not a causal "
                "mechanism, not a confirmed biological finding."
            ),
            scientific_limitations=tuple(limitations),
            status=mapped_status,
            parent_ids=(source_snapshot_id,),
        )
    except ResearchCycleError as exc:
        return _not_bridged(f"research_cycle_rejected: {exc}", preserved)

    return _bridged(bridged.to_dict(), preserved)
