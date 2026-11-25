from pathlib import Path

import pytest

from tools.awareness_studio_research import importers
from tools.awareness_studio_research.network import NetworkDisabledError, fetch_arxiv_metadata, fetch_doi_metadata

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def test_import_json_export():
    sources = importers.import_json_export(FIXTURES_DIR / "sample_export.json")
    assert len(sources) == 2
    titles = {s.title for s in sources}
    assert "A Fixture Paper About Decentering and Metacognitive Distance" in titles
    preprint = next(s for s in sources if s.arxiv_id == "9999.00001")
    assert preprint.source_type == "preprint"
    assert preprint.retrieval_metadata["method"] == "json_export"
    assert preprint.retrieval_metadata["network_used"] is False


def test_import_csv_export():
    sources = importers.import_csv_export(FIXTURES_DIR / "sample_export.csv")
    assert len(sources) == 1
    source = sources[0]
    assert source.authors == ("A. Csv", "B. Csv")
    assert source.limitations == ("single dataset", "no replication")
    assert source.retrieval_metadata["method"] == "csv_export"


def test_import_arxiv_metadata_operator_supplied():
    source = importers.import_arxiv_metadata(
        {"title": "A Fixture arXiv Paper", "arxiv_id": "1111.2222", "authors": ["X. Author"]}
    )
    assert source.source_type == "preprint"
    assert source.url == "https://arxiv.org/abs/1111.2222"
    assert source.retrieval_metadata["method"] == "operator_manual"
    assert source.retrieval_metadata["network_used"] is False


def test_import_doi_metadata_operator_supplied():
    source = importers.import_doi_metadata({"title": "A Fixture DOI Paper", "doi": "10.9999/x"})
    assert source.peer_review_status == "peer_reviewed"
    assert source.retrieval_metadata["method"] == "doi_operator_supplied"


def test_import_manual_capture_bounds_and_checksums_excerpt():
    long_text = "word " * 1000
    source = importers.import_manual_capture(
        text=long_text, metadata={"title": "A Manually Captured Page", "url": "https://example.org"}
    )
    assert source.abstract_or_excerpt.endswith("…[truncated]")
    assert len(source.abstract_or_excerpt) <= 2000 + len(" …[truncated]")
    assert source.source_checksum
    assert "manually captured excerpt" in source.limitations[0]


def test_network_fetch_disabled_by_default():
    with pytest.raises(NetworkDisabledError):
        fetch_arxiv_metadata("2609.03987")
    with pytest.raises(NetworkDisabledError):
        fetch_doi_metadata("10.1016/j.neuron.2026.04.044")


def test_network_fetch_requires_explicit_opt_in_keyword():
    """allow_network defaults to False even if called positionally with
    no other args -- confirms the gate can't be bypassed accidentally."""
    import inspect

    sig = inspect.signature(fetch_arxiv_metadata)
    assert sig.parameters["allow_network"].default is False
