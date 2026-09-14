"""Validate literature context and create linked canonical planning records."""
from dataclasses import replace
from typing import Any, Mapping

from awareness_studio.literature_bridge.mapping import bridge_claim, bridge_source
from awareness_studio.research_cycle.models import ExperimentSpec, Hypothesis, record_from_dict, stable_id
from tools.literature_evidence.models import ClaimRecord, LiteratureRecord, SourceSnapshot


def prepare_research_context(preflight: Mapping[str, Any], cycle_id: str, binding: Mapping[str, Any]):
    """Optional local literature context; missing or invalid declarations fail.

    A context is explicit input to research planning. This function does not
    generate a hypothesis or independently verify the truth of a citation.
    """
    context = preflight.get("literature_context")
    if context is None:
        return []
    if not isinstance(context, Mapping):
        raise ValueError("literature_context must be an object")
    if any(not isinstance(context.get(key), Mapping) for key in ("source", "snapshot", "claim")):
        raise ValueError("literature_context requires source, snapshot, and claim objects")
    if not context.get("source", {}).get("retrieval_timestamp") or not context.get("snapshot", {}).get("captured_at"):
        raise ValueError("literature retrieval and snapshot capture timestamps must be explicit")
    source = LiteratureRecord.from_dict(context["source"])
    snapshot = SourceSnapshot.from_dict(context["snapshot"])
    claim = ClaimRecord.from_dict(context["claim"])
    if snapshot.kind != "full_local_snapshot" or not snapshot.content_checksum:
        raise ValueError("execution context requires a checksummed local source snapshot")
    if claim.source_id != source.source_id:
        raise ValueError("literature claim references a different source")
    source_outcome = bridge_source(source, cycle_id=cycle_id, snapshot=snapshot)
    if source_outcome.status != "bridged":
        raise ValueError(source_outcome.reason)
    source_record = record_from_dict(source_outcome.record)
    source_record = replace(source_record, snapshot_id=stable_id("source", {"cycle": cycle_id, "source": source_outcome.record}))
    claim_outcome = bridge_claim(
        claim,
        cycle_id=cycle_id,
        source_snapshot_id=f"lit-source-{claim.source_id}",
    )
    if claim_outcome.status != "bridged":
        raise ValueError(claim_outcome.reason)
    claim_record = record_from_dict(claim_outcome.record)
    claim_record = replace(
        claim_record,
        claim_id=stable_id("claim", {"cycle": cycle_id, "claim": claim_outcome.record}),
        evidence_ids=(source_record.record_id,),
        parent_ids=(source_record.record_id,),
    )
    hypothesis = Hypothesis(stable_id("hypothesis", {"cycle": cycle_id}), cycle_id,
                            preflight["plan"]["research_question"], (claim_record.record_id,),
                            claim_scope="Declared research question; no conclusion from source ingestion.",
                            parent_ids=(claim_record.record_id,))
    experiment = ExperimentSpec(stable_id("experiment", {"cycle": cycle_id}), cycle_id,
                                (hypothesis.record_id,), binding["workload_id"], dict(binding),
                                parent_ids=(hypothesis.record_id,))
    return [source_record, claim_record, hypothesis, experiment]
