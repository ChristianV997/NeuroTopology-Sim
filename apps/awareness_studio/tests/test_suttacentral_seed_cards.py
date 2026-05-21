import json
from pathlib import Path

from awareness_studio.io_markdown import infer_source_kind, load_documents


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

CORE_UIDS = {
    "sn12.23",
    "an2.30",
    "an5.26",
    "sn22.59",
    "sn22.14",
    "ud8.3",
    "mn118",
    "mn106",
}

FORBIDDEN_OVERCLAIMS = (
    "prove consciousness topology",
    "suttas prove",
    "nibbāna equals q",
    "nibbana equals q",
    "q/qabs/fdress are canonical",
    "canonical buddhist entities",
)


def _seed_rows():
    root = Path(__file__).resolve().parents[1]
    path = root / "inputs" / "suttacentral_seed_cards.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_suttacentral_seed_cards_schema():
    rows = _seed_rows()

    assert len(rows) >= len(CORE_UIDS)
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
        assert row["text_role"]
        assert row["tol_function"]
        assert row["ontology_guardrail"]
        summary = row["summary"].lower()
        assert "prove" not in summary
        assert all(forbidden not in summary for forbidden in FORBIDDEN_OVERCLAIMS)


def test_seed_cards_include_core_texts():
    rows = _seed_rows()
    uids = {row["uid"] for row in rows}

    assert CORE_UIDS.issubset(uids)


def test_theravada_suttacentral_markdown_infers_source_kind():
    assert infer_source_kind(Path("run41_theravada_suttacentral_integration.md")) == "theravada_sutta"
    assert infer_source_kind(Path("notion_export/SuttaCentral/sn22_59.md")) == "theravada_sutta"


def test_run41_export_is_indexed_as_theravada_sutta():
    root = Path(__file__).resolve().parents[1]
    inputs_dir = root / "inputs" / "notion_export"
    docs = load_documents(inputs_dir)
    run41_docs = [doc for doc in docs if doc.source_path.endswith("run41_theravada_suttacentral_integration.md")]

    assert run41_docs
    assert {doc.source_kind for doc in run41_docs} == {"theravada_sutta"}
