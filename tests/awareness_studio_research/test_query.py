import pytest

from tools.awareness_studio_research.models import ExtractedClaim
from tools.awareness_studio_research.query import available_query_packs, run_query_pack

CLAIMS = [
    ExtractedClaim(
        claim_id="c1", source_id="s1",
        claim_text="Triadic (three-way) functional connectivity reveals hidden community structure.",
        tags=("connectivity",),
    ),
    ExtractedClaim(
        claim_id="c2", source_id="s2",
        claim_text="The trispectrum, a higher-order spectra method, identifies modulated oscillations.",
    ),
    ExtractedClaim(
        claim_id="c3", source_id="s3",
        claim_text="Slow breathing raises parasympathetic tone and vagal activity.",
    ),
    ExtractedClaim(
        claim_id="c4", source_id="s4",
        claim_text="Discernment requires wise evaluative judgment beyond simple nonjudgment.",
    ),
    ExtractedClaim(
        claim_id="c5", source_id="s5",
        claim_text="Decentering is a form of metacognitive distancing from thought content.",
    ),
    ExtractedClaim(
        claim_id="c6", source_id="s6",
        claim_text="A null model using surrogate data controls for spurious correlations.",
    ),
]


def test_available_query_packs_includes_all_required():
    packs = available_query_packs()
    for expected in (
        "triadic_connectivity", "higher_order_spectra", "respiration_autonomic",
        "discernment", "nonattachment", "decentering", "hypergraph_forecasting",
        "null_model_methodology",
    ):
        assert expected in packs


def test_triadic_connectivity_query():
    results = run_query_pack(CLAIMS, "triadic_connectivity")
    assert [c.claim_id for c in results] == ["c1"]


def test_higher_order_spectra_query():
    results = run_query_pack(CLAIMS, "higher_order_spectra")
    assert [c.claim_id for c in results] == ["c2"]


def test_respiration_autonomic_query():
    results = run_query_pack(CLAIMS, "respiration_autonomic")
    assert [c.claim_id for c in results] == ["c3"]


def test_discernment_query():
    results = run_query_pack(CLAIMS, "discernment")
    assert [c.claim_id for c in results] == ["c4"]


def test_decentering_query():
    results = run_query_pack(CLAIMS, "decentering")
    assert [c.claim_id for c in results] == ["c5"]


def test_null_model_methodology_query():
    results = run_query_pack(CLAIMS, "null_model_methodology")
    assert [c.claim_id for c in results] == ["c6"]


def test_unknown_pack_raises():
    with pytest.raises(KeyError):
        run_query_pack(CLAIMS, "not-a-real-pack")


def test_query_is_deterministic_across_repeats():
    outputs = {tuple(c.claim_id for c in run_query_pack(CLAIMS, "decentering")) for _ in range(15)}
    assert len(outputs) == 1
