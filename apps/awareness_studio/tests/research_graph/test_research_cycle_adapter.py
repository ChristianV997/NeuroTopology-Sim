"""Direct tests of research_cycle_adapter.manifest_from_ledger, independent
of the literature_bridge (which never emits FORMAL_STATISTICAL_EVIDENCE) --
these exercise research_cycle record shapes the bridge doesn't produce,
since the adapter itself is meant to be general-purpose.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from awareness_studio.research_cycle.ledger import ResearchCycleLedger
from awareness_studio.research_cycle.models import Claim, EvidenceClass, SourceSnapshot
from awareness_studio.research_graph import EvidenceClass as GraphEvidenceClass
from awareness_studio.research_graph import load_from_dict, manifest_from_ledger


@pytest.fixture
def ledger(tmp_path: Path) -> ResearchCycleLedger:
    return ResearchCycleLedger(tmp_path / "ledger.sqlite3")


def test_formal_source_with_preregistration_flags_reaches_formal(ledger):
    cycle_id = ledger.create_cycle("cycle-formal-ok")
    source = SourceSnapshot(
        snapshot_id="src-formal-ok",
        cycle_id=cycle_id,
        source_uri="urn:test:formal-ok",
        source_sha256="a" * 64,
        data_mode="empirical",
        evidence_class=EvidenceClass.FORMAL_STATISTICAL_EVIDENCE,
        claim_scope="test",
        scientific_limitations=("none stated",),
        metadata={"preregistered": True, "held_out_split_locked": True},
    )
    ledger.append_record(cycle_id, source)

    manifest = manifest_from_ledger(ledger, cycle_id)
    graph = load_from_dict(manifest)
    node = graph.get_node("src-formal-ok")
    assert node is not None
    assert node.evidence_class == GraphEvidenceClass.FORMAL.value


def test_formal_source_without_preregistration_flags_downgrades_to_empirical_and_is_flagged(ledger):
    """Without preregistered+held_out_split_locked, research_graph's own
    _classify_evidence downgrades a bare "formal" claim to EMPIRICAL -- and
    the EMPIRICAL_CLAIM_WITHOUT_VERIFICATION guardrail must catch it,
    since nothing here corroborates the claim either."""
    cycle_id = ledger.create_cycle("cycle-formal-unverified")
    source = SourceSnapshot(
        snapshot_id="src-formal-unverified",
        cycle_id=cycle_id,
        source_uri="urn:test:formal-unverified",
        source_sha256="b" * 64,
        data_mode="empirical",
        evidence_class=EvidenceClass.FORMAL_STATISTICAL_EVIDENCE,
        claim_scope="test",
        scientific_limitations=("none stated",),
    )
    ledger.append_record(cycle_id, source)

    manifest = manifest_from_ledger(ledger, cycle_id)
    graph = load_from_dict(manifest)
    node = graph.get_node("src-formal-unverified")
    assert node is not None
    assert node.evidence_class == GraphEvidenceClass.EMPIRICAL.value

    from awareness_studio.research_graph import DiagnosticCode

    violations = [
        d for d in graph.diagnostics if d.code == DiagnosticCode.EMPIRICAL_CLAIM_WITHOUT_VERIFICATION.value
    ]
    assert len(violations) == 1
    assert violations[0].affected_ids == ("src-formal-unverified",)


def test_claim_declaring_formal_statistical_evidence_downgrades_and_is_flagged(ledger):
    """A research_cycle Claim has no metadata field to source
    preregistered/held_out_split_locked from, so a Claim translated as
    "formal" always downgrades to EMPIRICAL in research_graph's own
    _classify_evidence -- this is expected, not a bug in the adapter.
    What matters is that the downgrade is never silent: the
    EMPIRICAL_CLAIM_WITHOUT_VERIFICATION guardrail checks CLAIM nodes as
    well as SOURCE_SNAPSHOT ones precisely so this case is always flagged,
    exactly like an unverified empirical/formal source is."""
    cycle_id = ledger.create_cycle("cycle-claim-formal")
    source = SourceSnapshot(
        snapshot_id="src-for-claim",
        cycle_id=cycle_id,
        source_uri="urn:test:src-for-claim",
        source_sha256="c" * 64,
        # Deliberately NOT "empirical"/"synthetic_demo": this source only
        # exists so the claim below has a parent to link to; its own
        # classification isn't the point of this test (that's covered by
        # the FORMAL-source tests above).
        data_mode="literature_metadata",
        evidence_class=EvidenceClass.HYPOTHESIS,
        claim_scope="test",
        scientific_limitations=("none stated",),
    )
    ledger.append_record(cycle_id, source)
    claim = Claim(
        claim_id="claim-formal-attempt",
        cycle_id=cycle_id,
        statement="A claim that declares itself formal statistical evidence.",
        evidence_ids=("src-for-claim",),
        evidence_class=EvidenceClass.FORMAL_STATISTICAL_EVIDENCE,
        claim_scope="test",
        scientific_limitations=("none stated",),
        parent_ids=("src-for-claim",),
    )
    ledger.append_record(cycle_id, claim)

    manifest = manifest_from_ledger(ledger, cycle_id)
    assert manifest["claims"][0]["evidence_class"] == "formal"

    graph = load_from_dict(manifest)
    node = graph.get_node("claim-formal-attempt")
    assert node is not None
    assert node.evidence_class == GraphEvidenceClass.EMPIRICAL.value

    from awareness_studio.research_graph import DiagnosticCode

    violations = [
        d for d in graph.diagnostics if d.code == DiagnosticCode.EMPIRICAL_CLAIM_WITHOUT_VERIFICATION.value
    ]
    assert len(violations) == 1
    assert violations[0].affected_ids == ("claim-formal-attempt",)


def test_claim_declaring_descriptive_empirical_without_verification_is_flagged(ledger):
    """Regression test for a real /code-review finding: a Claim with
    evidence_class=DESCRIPTIVE_EMPIRICAL translates straight to "empirical"
    (no FORMAL-style gate applies to a bare "empirical" string), and before
    the diagnostics fix in this same change, CLAIM nodes were never checked
    for verification at all -- an unverified empirical claim would have
    passed through completely unflagged."""
    cycle_id = ledger.create_cycle("cycle-claim-empirical")
    source = SourceSnapshot(
        snapshot_id="external-evidence-ref",
        cycle_id=cycle_id,
        source_uri="urn:test:external-evidence-ref",
        source_sha256="d" * 64,
        data_mode="literature_metadata",
        evidence_class=EvidenceClass.HYPOTHESIS,
        claim_scope="test",
        scientific_limitations=("none stated",),
    )
    ledger.append_record(cycle_id, source)
    claim = Claim(
        claim_id="claim-empirical-unverified",
        cycle_id=cycle_id,
        statement="A claim declaring itself descriptive empirical evidence with no corroboration.",
        evidence_ids=("external-evidence-ref",),
        evidence_class=EvidenceClass.DESCRIPTIVE_EMPIRICAL,
        claim_scope="test",
        scientific_limitations=("none stated",),
        parent_ids=("external-evidence-ref",),
    )
    ledger.append_record(cycle_id, claim)

    manifest = manifest_from_ledger(ledger, cycle_id)
    assert manifest["claims"][0]["evidence_class"] == "empirical"

    graph = load_from_dict(manifest)
    node = graph.get_node("claim-empirical-unverified")
    assert node is not None
    assert node.evidence_class == GraphEvidenceClass.EMPIRICAL.value

    from awareness_studio.research_graph import DiagnosticCode

    violations = [
        d for d in graph.diagnostics if d.code == DiagnosticCode.EMPIRICAL_CLAIM_WITHOUT_VERIFICATION.value
    ]
    assert len(violations) == 1
    assert violations[0].affected_ids == ("claim-empirical-unverified",)
