import pytest

from tools.awareness_studio_research.checksum import content_checksum, stable_source_id
from tools.awareness_studio_research.models import ExtractedClaim, LiteratureSource
from tools.awareness_studio_research.store import ImmutabilityError


def _make_source(source_id="s1", title="A Paper", **overrides) -> LiteratureSource:
    base = dict(
        source_id=source_id,
        title=title,
        doi="10.1/x",
        source_checksum=content_checksum(title),
        evidence_tier="T3_unverified_claimed",
    )
    base.update(overrides)
    return LiteratureSource(**base)


def test_add_and_get_source(registry):
    source = _make_source()
    registry.add_source(source)
    fetched = registry.get_source("s1")
    assert fetched is not None
    assert fetched.title == "A Paper"
    assert fetched.version == 1


def test_source_ingestion_persists_across_reopen(tmp_path, registry):
    registry.add_source(_make_source())
    from tools.awareness_studio_research.store import EvidenceRegistry

    reopened = EvidenceRegistry(registry.log_path)
    assert reopened.get_source("s1") is not None


def test_duplicate_source_id_raises_immutability_error(registry):
    registry.add_source(_make_source())
    with pytest.raises(ImmutabilityError):
        registry.add_source(_make_source())


def test_supersede_source_creates_new_version_never_deletes_old_event(registry):
    registry.add_source(_make_source())
    registry.supersede_source("s1", superseded_by="s2", reason="a newer version was found")
    current = registry.get_source("s1")
    assert current.status == "superseded"
    assert current.superseded_by == "s2"
    assert current.version == 2

    # The original "created" event is still in the log, untouched.
    events = registry.audit_history(entity_type="source", entity_id="s1")
    assert len(events) == 2
    assert events[0]["record"]["version"] == 1
    assert events[0]["record"]["status"] == "active"
    assert events[1]["record"]["version"] == 2
    assert events[1]["record"]["status"] == "superseded"


def test_dispute_source_accumulates_disagreements(registry):
    registry.add_source(_make_source())
    registry.dispute_source("s1", reason="title mismatch found", disagreements=("title does not match",))
    disputed = registry.get_source("s1")
    assert disputed.status == "disputed"
    assert disputed.verification_status == "disputed"
    assert disputed.evidence_tier == "T4_disputed"
    assert "title does not match" in disputed.disagreements


def test_downgrade_source_changes_tier_only(registry):
    registry.add_source(_make_source(evidence_tier="T1_verified_primary"))
    registry.downgrade_source("s1", new_evidence_tier="T3_unverified_claimed", reason="re-review found gaps")
    downgraded = registry.get_source("s1")
    assert downgraded.evidence_tier == "T3_unverified_claimed"
    assert downgraded.status == "active"


def test_mutating_unknown_source_raises_keyerror(registry):
    with pytest.raises(KeyError):
        registry.supersede_source("does-not-exist", superseded_by="x", reason="n/a")


def test_claim_extraction_fixture_and_dispute(registry):
    registry.add_source(_make_source())
    claim = ExtractedClaim(
        claim_id="c1",
        source_id="s1",
        claim_text="Prolonged exhalation increases risky choices via parasympathetic upregulation.",
        claim_class="causal",
        supporting_excerpt="Prolonged exhalation increased risky choices...",
        confidence=0.6,
        bio_vs_methodological="biological",
        claim_status="empirical",
        tags=("respiration", "autonomic"),
    )
    registry.add_claim(claim)
    assert registry.get_claim("c1").claim_status == "empirical"

    registry.dispute_claim("c1", reason="independent replication failed", new_claim_status="unsupported")
    disputed = registry.get_claim("c1")
    assert disputed.status == "disputed"
    assert disputed.claim_status == "unsupported"
    assert disputed.version == 2


def test_unsupported_claim_recorded_as_such(registry):
    registry.add_source(_make_source())
    claim = ExtractedClaim(
        claim_id="c2", source_id="s1", claim_text="Speculative extrapolation with no data.",
        claim_status="unsupported", confidence=0.05,
    )
    registry.add_claim(claim)
    assert registry.get_claim("c2").claim_status == "unsupported"


def test_theoretical_paper_claim_status(registry):
    registry.add_source(_make_source(source_id="s2", title="A Theoretical Paper", source_type="journal_article"))
    claim = ExtractedClaim(
        claim_id="c3", source_id="s2", claim_text="A purely theoretical framework proposal.",
        claim_class="theoretical", claim_status="theoretical",
    )
    registry.add_claim(claim)
    assert registry.get_claim("c3").claim_class == "theoretical"


def test_preprint_source_has_expected_peer_review_status(registry):
    source = _make_source(
        source_id="s3", title="A Preprint", arxiv_id="1234.5678", doi=None,
        source_type="preprint", peer_review_status="preprint_not_peer_reviewed",
    )
    registry.add_source(source)
    assert registry.get_source("s3").peer_review_status == "preprint_not_peer_reviewed"


def test_missing_metadata_defaults_conservatively_not_fabricated():
    source = LiteratureSource(source_id=stable_source_id(doi=None, arxiv_id=None, title="Minimal"), title="Minimal")
    assert source.doi is None
    assert source.arxiv_id is None
    assert source.peer_review_status == "unknown"
    assert source.evidence_tier == "T3_unverified_claimed"
    assert source.limitations == ()


def test_deterministic_repeat_projection(registry):
    import json

    registry.add_source(_make_source())
    registry.supersede_source("s1", superseded_by="s2", reason="newer version")
    snapshots = {
        json.dumps(registry.get_source("s1").to_dict(), sort_keys=True) for _ in range(10)
    }
    assert len(snapshots) == 1


def test_real_five_sources_ingested_with_correct_dispositions(registry, five_sources_fixture):
    """Ingests the 5 real scientific sources named in the task prompt,
    using the verification fixture, and asserts the registry ends up
    with exactly the right active/disputed split -- never silently
    reporting a disputed source as verified."""
    from tools.awareness_studio_research import importers
    from tools.awareness_studio_research.verification import verify_source_claim

    for entry in five_sources_fixture["sources"]:
        claimed = entry["claimed"]
        confirmed = entry["confirmed"]
        operator_metadata = {**claimed, **{k: v for k, v in confirmed.items() if k != "exists"}}
        source = importers.import_doi_metadata(operator_metadata) if claimed.get("doi") else importers.import_arxiv_metadata(operator_metadata)
        # The prompt gave only a topic descriptor per source, never an
        # exact title claim -- identity is verified by doi/arxiv_id
        # existence, not by comparing the descriptor to the real title.
        result = verify_source_claim(
            claimed_title=confirmed.get("title") or claimed["title"],
            claimed_doi=claimed.get("doi"),
            claimed_arxiv_id=claimed.get("arxiv_id"),
            confirmed=confirmed,
        )
        data = source.to_dict()
        data["verification_status"] = result.verification_status
        data["evidence_tier"] = result.evidence_tier
        data["disagreements"] = result.disagreements
        if result.verification_status == "disputed":
            data["status"] = "disputed"
        registry.add_source(LiteratureSource(**data))

    sources = {s.doi or s.arxiv_id: s for s in registry.list_sources()}
    verified = [s for s in sources.values() if s.verification_status == "verified"]
    disputed = [s for s in sources.values() if s.verification_status == "disputed"]
    assert len(verified) == 3
    assert len(disputed) == 2
    for s in disputed:
        assert s.disagreements
