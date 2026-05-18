import json
from pathlib import Path


REQUIRED_FIELDS = {
    "uid",
    "title",
    "collection",
    "source_url",
    "source_kind",
    "translation_lang",
    "text_role",
    "tol_function",
    "claim_type",
    "ontology_guardrail",
    "summary",
}


def test_suttacentral_seed_cards_schema():
    root = Path(__file__).resolve().parents[1]
    path = root / "inputs" / "suttacentral_seed_cards.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

    assert len(rows) >= 8
    for row in rows:
        assert REQUIRED_FIELDS.issubset(row)
        assert row["uid"]
        assert row["source_kind"] == "suttacentral"
        assert row["source_url"].startswith("https://suttacentral.net/")
        assert row["claim_type"] in {
            "doctrine_scaffold",
            "interpretive_bridge",
            "practice_protocol",
            "empirical_hypothesis",
            "quarantined_speculation",
        }
        assert "prove" not in row["summary"].lower()


def test_seed_cards_include_core_vimutti_and_anatta_texts():
    root = Path(__file__).resolve().parents[1]
    path = root / "inputs" / "suttacentral_seed_cards.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    uids = {row["uid"] for row in rows}

    assert "sn12.23" in uids
    assert "an2.30" in uids
    assert "an5.26" in uids
    assert "sn22.59" in uids
    assert "sn22.14" in uids
    assert "ud8.3" in uids
