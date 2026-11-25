"""End-to-end proof that the full chain actually works together:

tools.literature_evidence (source identity + claim)
  -> awareness_studio.literature_bridge (mapping into research_cycle's schema)
  -> awareness_studio.research_cycle.ledger.ResearchCycleLedger (append + persist)
  -> awareness_studio.research_graph.research_cycle_adapter (project into a manifest)
  -> awareness_studio.research_graph.load_from_dict (evidence graph)

Before this test (and the research_cycle_adapter module it exercises),
nothing in the repository proved this pipe worked end to end -- each
link was tested against the next one's *schema* in isolation, never
against a live instance of the next real component. This test uses
real objects at every step (a real SQLite-backed ledger in a temp
directory, real dataclass instances, a real evidence graph) -- no
mocks.

The central assertion: a literature source that is only ever
hypothesis-tier in tools.literature_evidence (evidence_class="hypothesis",
never "empirical") must never become an EMPIRICAL node in the final
evidence graph, anywhere along this chain. This is the same guarantee
apps/awareness_studio/tests/research_graph/test_evidence_classes_and_safety.py
checks in isolation for research_graph alone; this test checks it holds
when the graph's input actually comes from a real research_cycle ledger
populated via the real bridge, not a hand-written manifest dict.
"""
from __future__ import annotations

from pathlib import Path

from awareness_studio.literature_bridge.mapping import bridge_claim, bridge_source
from awareness_studio.research_cycle.ledger import ResearchCycleLedger
from awareness_studio.research_cycle.models import record_from_dict
from awareness_studio.research_graph import EvidenceClass, NodeType, load_from_dict, manifest_from_ledger
from tools.literature_evidence.checksum import content_checksum
from tools.literature_evidence.models import ClaimRecord, LiteratureRecord


def _build_ledger(tmp_path: Path) -> ResearchCycleLedger:
    return ResearchCycleLedger(tmp_path / "research_cycle.sqlite3")


def test_hypothesis_tier_literature_source_never_becomes_empirical_end_to_end(tmp_path):
    ledger = _build_ledger(tmp_path)
    cycle_id = ledger.create_cycle("cycle-e2e-001")

    literature_record = LiteratureRecord(
        source_id="e2e-src-0001",
        identifier="2609.03987",
        identifier_type="arxiv",
        title="High-Order Triadic Functional Connectivity in the Brain and Beyond",
        authors=("Qiang Li",),
        venue=None,
        publication_type="preprint",
        source_url="https://arxiv.org/abs/2609.03987",
        content_checksum=content_checksum("a bounded fixture excerpt of the abstract"),
        review_status="unreviewed",
        evidence_class="hypothesis",
    )
    source_outcome = bridge_source(literature_record, cycle_id=cycle_id)
    assert source_outcome.status == "bridged"

    source_record = record_from_dict(source_outcome.record)
    ledger.append_record(cycle_id, source_record)

    literature_claim = ClaimRecord(
        claim_id="e2e-claim-0001",
        source_id=literature_record.source_id,
        claim_text="Triadic functional connectivity reveals community structure absent from pairwise analysis.",
    )
    claim_outcome = bridge_claim(literature_claim, cycle_id=cycle_id, source_snapshot_id=source_outcome.record["snapshot_id"])
    assert claim_outcome.status == "bridged"

    claim_record = record_from_dict(claim_outcome.record)
    ledger.append_record(cycle_id, claim_record)

    # Real ledger integrity check -- not just "it didn't raise."
    assert ledger.recover(cycle_id) is True

    manifest = manifest_from_ledger(ledger, cycle_id)
    assert len(manifest["sources"]) == 1
    assert len(manifest["claims"]) == 1

    graph = load_from_dict(manifest)

    source_node = graph.get_node(source_outcome.record["snapshot_id"])
    assert source_node is not None
    assert source_node.node_type == NodeType.SOURCE_SNAPSHOT.value
    assert source_node.evidence_class == EvidenceClass.UNKNOWN.value
    assert source_node.evidence_class != EvidenceClass.EMPIRICAL.value

    claim_node = graph.get_node(claim_outcome.record["claim_id"])
    assert claim_node is not None
    assert claim_node.node_type == NodeType.CLAIM.value
    assert claim_node.evidence_class == EvidenceClass.UNKNOWN.value
    assert claim_node.evidence_class != EvidenceClass.EMPIRICAL.value

    # No EMPIRICAL_CLAIM_WITHOUT_VERIFICATION false positive either --
    # the node correctly never claimed empirical/formal in the first place.
    empirical_violations = [d for d in graph.diagnostics if "empirical" in d.code]
    assert empirical_violations == []


def test_proxy_tier_literature_source_ends_up_proxy_not_empirical(tmp_path):
    ledger = _build_ledger(tmp_path)
    cycle_id = ledger.create_cycle("cycle-e2e-002")

    literature_record = LiteratureRecord(
        source_id="e2e-src-proxy-0001",
        identifier="10.1016/j.neuron.2026.04.044",
        identifier_type="doi",
        title="Slow breathing impacts inter-organ dynamics",
        publication_type="peer_reviewed_journal_article",
        source_url="https://example.org/paper",
        content_checksum=content_checksum("a bounded fixture excerpt"),
        review_status="reviewed_accepted",
        evidence_class="proxy",
    )
    source_outcome = bridge_source(literature_record, cycle_id=cycle_id)
    assert source_outcome.status == "bridged"

    source_record = record_from_dict(source_outcome.record)
    ledger.append_record(cycle_id, source_record)

    manifest = manifest_from_ledger(ledger, cycle_id)
    graph = load_from_dict(manifest)
    source_node = graph.get_node(source_outcome.record["snapshot_id"])
    assert source_node is not None
    assert source_node.evidence_class == EvidenceClass.PROXY.value
    assert source_node.evidence_class != EvidenceClass.EMPIRICAL.value


def test_ledger_round_trip_preserves_real_checksum(tmp_path):
    """The checksum carried through the whole chain is the literature
    record's own real sha256, verified end to end -- never fabricated,
    never dropped -- via record_from_dict's own checksum verification
    plus a direct equality check against the original."""
    ledger = _build_ledger(tmp_path)
    cycle_id = ledger.create_cycle("cycle-e2e-003")

    real_excerpt = "a bounded fixture excerpt used to compute a real checksum"
    expected_checksum = content_checksum(real_excerpt)

    literature_record = LiteratureRecord(
        source_id="e2e-src-checksum-0001",
        identifier="10.1016/j.neuron.2026.04.044",
        identifier_type="doi",
        title="A Fixture Paper",
        publication_type="peer_reviewed_journal_article",
        content_checksum=expected_checksum,
        review_status="reviewed_accepted",
    )
    source_outcome = bridge_source(literature_record, cycle_id=cycle_id)
    assert source_outcome.record["source_sha256"] == expected_checksum

    source_record = record_from_dict(source_outcome.record)  # raises if checksum is tampered
    ledger.append_record(cycle_id, source_record)

    reloaded = ledger.records(cycle_id)
    assert len(reloaded) == 1
    assert reloaded[0].source_sha256 == expected_checksum
