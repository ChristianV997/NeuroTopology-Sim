from tools.awareness_studio_research.verification import verify_source_claim


def test_no_confirmation_attempted_is_unverified():
    result = verify_source_claim(
        claimed_title="Some Paper", claimed_doi="10.1/x", claimed_arxiv_id=None, confirmed=None
    )
    assert result.verification_status == "unverified"
    assert result.evidence_tier == "T3_unverified_claimed"
    assert result.disagreements


def test_confirmed_match_is_verified():
    result = verify_source_claim(
        claimed_title="Some Paper",
        claimed_doi="10.1/x",
        claimed_arxiv_id=None,
        confirmed={"exists": True, "title": "Some Paper", "doi": "10.1/x"},
    )
    assert result.verification_status == "verified"
    assert result.disagreements == ()


def test_confirmed_title_mismatch_is_disputed():
    result = verify_source_claim(
        claimed_title="Wrong Title",
        claimed_doi="10.1/x",
        claimed_arxiv_id=None,
        confirmed={"exists": True, "title": "Actual Title", "doi": "10.1/x"},
    )
    assert result.verification_status == "disputed"
    assert result.evidence_tier == "T4_disputed"
    assert any("does not match" in d for d in result.disagreements)


def test_confirmed_does_not_exist_is_disputed():
    result = verify_source_claim(
        claimed_title="Ghost Paper", claimed_doi="10.1/ghost", claimed_arxiv_id=None,
        confirmed={"exists": False},
    )
    assert result.verification_status == "disputed"
    assert any("could not be found" in d for d in result.disagreements)


def test_five_real_sources_fixture_two_disagreements(five_sources_fixture):
    """Cross-checks the real 2026-09-07 WebSearch verification recorded in
    the fixture: 3 of 5 sources confirm cleanly, 2 do not (the exact
    claimed DOI could not be independently located for either).

    The prompt only gave a topic descriptor per source (e.g. "triadic
    functional connectivity"), never an exact title claim, so
    ``claimed_title`` is intentionally omitted from the identity check
    here (comparing a topic descriptor against a real title would
    always mismatch and produce a false disagreement) -- identity is
    verified by DOI/arXiv-id existence alone, exactly as the prompt's
    claims were actually phrased. Topic-relevance is checked separately
    below by a plain substring match against the confirmed title/abstract.
    """
    results = {}
    for entry in five_sources_fixture["sources"]:
        claimed = entry["claimed"]
        confirmed = entry["confirmed"]
        result = verify_source_claim(
            claimed_title=confirmed.get("title") or claimed["title"],
            claimed_doi=claimed.get("doi"),
            claimed_arxiv_id=claimed.get("arxiv_id"),
            confirmed=confirmed,
        )
        results[entry["label"]] = result

        if confirmed.get("exists"):
            topic_descriptor = claimed["title"].lower()
            haystack = " ".join(
                [confirmed.get("title", ""), confirmed.get("abstract", "")]
            ).lower()
            topic_words = [w for w in topic_descriptor.replace("-", " ").split() if len(w) > 3]
            assert any(word in haystack for word in topic_words), (
                f"{entry['label']}: none of the prompt's topic words {topic_words} "
                f"appear in the confirmed title/abstract"
            )

    assert results["triadic_connectivity"].verification_status == "verified"
    assert results["higher_order_spectra"].verification_status == "verified"
    assert results["slow_breathing_inter_organ"].verification_status == "verified"
    assert results["discernment_nonjudgment"].verification_status == "disputed"
    assert results["buddhist_meditation_ecology"].verification_status == "disputed"

    disputed_count = sum(1 for r in results.values() if r.verification_status == "disputed")
    verified_count = sum(1 for r in results.values() if r.verification_status == "verified")
    assert disputed_count == 2
    assert verified_count == 3
