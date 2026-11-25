from tools.awareness_studio_research.checksum import (
    content_checksum,
    normalize_text,
    stable_claim_id,
    stable_source_id,
)
from tools.awareness_studio_research.dedupe import find_duplicates
from tools.awareness_studio_research.models import LiteratureSource


def test_normalize_text_collapses_whitespace_and_case():
    assert normalize_text("  Hello   World \n") == "hello world"


def test_content_checksum_deterministic():
    assert content_checksum("abc") == content_checksum("  ABC  ")


def test_content_checksum_sensitive_to_content():
    assert content_checksum("abc") != content_checksum("abcd")


def test_stable_source_id_prefers_doi():
    a = stable_source_id(doi="10.1/x", arxiv_id="1234.5678", title="Title A")
    b = stable_source_id(doi="10.1/x", arxiv_id="9999.9999", title="Title B")
    assert a == b


def test_stable_source_id_falls_back_to_arxiv_then_title():
    a = stable_source_id(doi=None, arxiv_id="1234.5678", title="Title A")
    b = stable_source_id(doi=None, arxiv_id="1234.5678", title="Title B")
    assert a == b
    c = stable_source_id(doi=None, arxiv_id=None, title="Same Title")
    d = stable_source_id(doi=None, arxiv_id=None, title="same title")
    assert c == d


def test_stable_claim_id_deterministic():
    a = stable_claim_id(source_id="s1", claim_text="X causes Y")
    b = stable_claim_id(source_id="s1", claim_text="  x causes y ")
    assert a == b


def _source(**overrides) -> LiteratureSource:
    base = dict(source_id="id1", title="A Paper", doi=None, arxiv_id=None, source_checksum="")
    base.update(overrides)
    return LiteratureSource(**base)


def test_find_duplicates_by_doi():
    existing = _source(source_id="id1", doi="10.1/x")
    candidate = _source(source_id="id2", doi="10.1/x")
    findings = find_duplicates(candidate, [existing])
    assert len(findings) == 1
    assert "doi_match" in findings[0][1]


def test_find_duplicates_by_normalized_title():
    existing = _source(source_id="id1", title="The Same Title")
    candidate = _source(source_id="id2", title="the same title")
    findings = find_duplicates(candidate, [existing])
    assert "normalized_title_match" in findings[0][1]


def test_find_duplicates_by_checksum():
    existing = _source(source_id="id1", source_checksum="abc123")
    candidate = _source(source_id="id2", source_checksum="abc123")
    findings = find_duplicates(candidate, [existing])
    assert "checksum_match" in findings[0][1]


def test_find_duplicates_none_when_disjoint():
    existing = _source(source_id="id1", title="Alpha", doi="10.1/alpha")
    candidate = _source(source_id="id2", title="Beta", doi="10.1/beta")
    assert find_duplicates(candidate, [existing]) == []


def test_find_duplicates_excludes_self_by_id():
    existing = _source(source_id="id1", title="Same", doi="10.1/x")
    findings = find_duplicates(existing, [existing])
    assert findings == []
