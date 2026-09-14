from __future__ import annotations

import pytest

from awareness_studio.literature_bridge.repo_paths import ensure_repo_root_importable

ensure_repo_root_importable()

from tools.literature_evidence.checksum import content_checksum  # noqa: E402
from tools.literature_evidence.models import LiteratureRecord  # noqa: E402


def make_record(**overrides) -> LiteratureRecord:
    base = dict(
        source_id="fixture-src-0001",
        identifier="10.1016/j.neuron.2026.04.044",
        identifier_type="doi",
        title="A Fixture Paper About Slow Breathing",
        authors=("A. One", "B. Two"),
        venue="Neuron",
        publication_type="peer_reviewed_journal_article",
        publication_date="2026-05",
        source_url="https://example.org/fixture-paper",
        content_checksum=content_checksum("a bounded fixture excerpt"),
        review_status="reviewed_accepted",
        evidence_class="hypothesis",
    )
    base.update(overrides)
    return LiteratureRecord(**base)


@pytest.fixture
def valid_peer_reviewed_record() -> LiteratureRecord:
    return make_record()


@pytest.fixture
def preprint_record() -> LiteratureRecord:
    return make_record(
        source_id="fixture-src-preprint",
        identifier="2609.03987",
        identifier_type="arxiv",
        title="A Fixture Preprint",
        publication_type="preprint",
        review_status="unreviewed",
        source_url="https://arxiv.org/abs/2609.03987",
    )


@pytest.fixture
def theory_paper_record() -> LiteratureRecord:
    return make_record(
        source_id="fixture-src-theory",
        identifier="978-3-16-148410-0",
        identifier_type="isbn",
        title="A Fixture Theoretical Framework",
        publication_type="theory_paper",
        source_url=None,
    )
