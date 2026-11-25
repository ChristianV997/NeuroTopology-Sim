import json
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from tests.literature_evidence.conftest import load_fixture, load_record
from tools.literature_evidence.checksum import file_checksum, is_well_formed_sha256, stable_source_id
from tools.literature_evidence.identifiers import is_valid_isbn, validate_identifier
from tools.literature_evidence.models import (
    CLAIM_KINDS,
    ClaimRecord,
    EVIDENCE_CLASSES,
    LiteratureRecord,
    SourceSnapshot,
)
from tools.literature_evidence.network import NetworkDisabledError, fetch_arxiv_metadata, fetch_doi_metadata
from tools.literature_evidence.reporting import NonFiniteValueError, to_finite_json
from tools.literature_evidence.store import ImmutabilityError, LiteratureEvidenceStore
from tools.literature_evidence.validation import validate_record

REPO_ROOT = Path(__file__).resolve().parents[2]


# -- fixtures: peer-reviewed / preprint / theory paper --------------------------------

def test_peer_reviewed_paper_is_valid():
    record = load_record("peer_reviewed_paper.json")
    result = validate_record(record)
    assert result.state == "valid"
    assert record.publication_type == "peer_reviewed_journal_article"


def test_preprint_is_valid_and_defaults_to_hypothesis_evidence_class():
    record = load_record("preprint.json")
    result = validate_record(record)
    assert result.state == "valid"
    assert record.evidence_class == "hypothesis"
    assert record.publication_type == "preprint"


def test_theory_paper_is_valid_with_isbn_identifier():
    record = load_record("theory_paper.json")
    result = validate_record(record)
    assert result.state == "valid"
    assert record.publication_type == "theory_paper"


# -- unresolved / fabricated identifiers -----------------------------------------------

def test_unresolved_fabricated_doi_is_rejected():
    record = load_record("unresolved_identifier.json")
    result = validate_record(record)
    assert result.state == "rejected_fabricated_identifier"
    assert not result.is_valid()


def test_missing_identifier_is_rejected_as_missing_identity():
    data = load_fixture("preprint.json")
    data["identifier"] = None
    record = LiteratureRecord.from_dict(data)
    result = validate_record(record)
    assert result.state == "rejected_missing_identity"


def test_fabricated_isbn_fails_checksum():
    assert is_valid_isbn("978-3-16-148410-1") is False  # last digit tampered
    assert is_valid_isbn("978-3-16-148410-0") is True


def test_valid_and_invalid_arxiv_ids():
    assert validate_identifier("2609.03987", "arxiv")[0] is True
    assert validate_identifier("arXiv:2609.03987", "arxiv")[0] is True
    assert validate_identifier("not-an-arxiv-id", "arxiv")[0] is False


def test_valid_and_invalid_doi():
    assert validate_identifier("10.1016/j.neuron.2026.04.044", "doi")[0] is True
    assert validate_identifier("just some text", "doi")[0] is False


# -- missing source content (metadata-only) --------------------------------------------

def test_missing_source_content_is_valid_as_metadata_only(store):
    record = load_record("missing_source_content.json")
    result = validate_record(record)
    assert result.state == "valid"  # metadata-only is explicitly supported, not rejected

    snapshot = SourceSnapshot(
        snapshot_id="snap-missing-0001", source_id=record.source_id, kind="metadata_only",
    )
    store.add_source(record)
    store.add_snapshot(snapshot)
    assert store.get_snapshot("snap-missing-0001").kind == "metadata_only"
    assert store.get_snapshot("snap-missing-0001").local_path is None


def test_snapshot_pointing_at_missing_file_is_rejected():
    record = load_record("preprint.json")
    snapshot = SourceSnapshot(
        snapshot_id="snap-x", source_id=record.source_id, kind="full_local_snapshot",
        local_path="/no/such/file/anywhere.txt", content_checksum="a" * 64,
    )
    result = validate_record(record, snapshot)
    assert result.state == "rejected_invalid_checksum"


def test_snapshot_with_checksum_mismatch_is_rejected(tmp_path):
    real_file = tmp_path / "content.txt"
    real_file.write_text("the real captured content")
    record = load_record("preprint.json")
    snapshot = SourceSnapshot(
        snapshot_id="snap-y", source_id=record.source_id, kind="full_local_snapshot",
        local_path=str(real_file), content_checksum="0" * 64,  # deliberately wrong
    )
    result = validate_record(record, snapshot)
    assert result.state == "rejected_invalid_checksum"


def test_snapshot_cannot_substitute_another_source(tmp_path):
    record = load_record("preprint.json")
    path = tmp_path / "source.txt"
    path.write_text("synthetic test source", encoding="utf-8")
    snapshot = SourceSnapshot("snapshot", "different-source", "full_local_snapshot",
                              str(path), file_checksum(path))
    assert validate_record(record, snapshot).state == "rejected_invalid_checksum"


def test_source_checksum_must_match_snapshot_even_when_snapshot_hash_matches(tmp_path):
    record = load_record("preprint.json")
    path = tmp_path / "source.txt"
    path.write_text("synthetic test source", encoding="utf-8")
    record.content_checksum = "0" * 64
    snapshot = SourceSnapshot("snapshot", record.source_id, "full_local_snapshot",
                              str(path), file_checksum(path))
    assert validate_record(record, snapshot).state == "rejected_invalid_checksum"


def test_snapshot_with_correct_checksum_is_valid(tmp_path):
    real_file = tmp_path / "content.txt"
    real_file.write_text("the real captured content")
    actual_checksum = file_checksum(real_file)
    record = load_record("preprint.json")
    snapshot = SourceSnapshot(
        snapshot_id="snap-z", source_id=record.source_id, kind="full_local_snapshot",
        local_path=str(real_file), content_checksum=actual_checksum,
    )
    result = validate_record(record, snapshot)
    assert result.state == "valid"


# -- invalid checksum format -------------------------------------------------------------

def test_malformed_content_checksum_is_rejected():
    data = load_fixture("peer_reviewed_paper.json")
    data["content_checksum"] = "not-a-real-hash"
    record = LiteratureRecord.from_dict(data)
    result = validate_record(record)
    assert result.state == "rejected_invalid_checksum"


def test_is_well_formed_sha256():
    assert is_well_formed_sha256("a" * 64) is True
    assert is_well_formed_sha256("a" * 63) is False
    assert is_well_formed_sha256(None) is False


# -- unsupported publication status -------------------------------------------------------

def test_unsupported_publication_type_is_rejected():
    data = load_fixture("peer_reviewed_paper.json")
    data["publication_type"] = "definitely_not_a_real_type"
    record = LiteratureRecord.from_dict(data)
    result = validate_record(record)
    assert result.state == "rejected_unsupported_publication_status"


def test_unsupported_review_status_is_rejected():
    data = load_fixture("peer_reviewed_paper.json")
    data["review_status"] = "definitely_not_a_real_status"
    record = LiteratureRecord.from_dict(data)
    result = validate_record(record)
    assert result.state == "rejected_unsupported_publication_status"


# -- source identity kept separate from claims (requirement 2) ---------------------------

def test_claim_references_source_but_is_not_embedded(store):
    record = load_record("peer_reviewed_paper.json")
    store.add_source(record)
    claim = ClaimRecord(
        claim_id="claim-0001", source_id=record.source_id,
        claim_text="Slow breathing modulates risk-taking via parasympathetic upregulation.",
    )
    store.add_claim(claim)
    fetched_source = store.get_source(record.source_id)
    assert not hasattr(fetched_source, "claim_text")
    fetched_claim = store.get_claim("claim-0001")
    assert fetched_claim.source_id == record.source_id


# -- never promote a claim to empirical (requirement 7) ------------------------------------

def test_claim_kind_can_never_be_empirical():
    with pytest.raises(ValueError):
        ClaimRecord(claim_id="c1", source_id="s1", claim_text="x", claim_kind="empirical")


def test_claim_kinds_and_evidence_classes_never_include_empirical():
    assert "empirical" not in CLAIM_KINDS
    assert "confirmed" not in CLAIM_KINDS
    assert "empirical" not in EVIDENCE_CLASSES
    assert "confirmed" not in EVIDENCE_CLASSES


def test_claim_defaults_to_hypothesis():
    claim = ClaimRecord(claim_id="c2", source_id="s1", claim_text="A default claim.")
    assert claim.claim_kind == "hypothesis"


def test_mark_claim_review_required_appends_new_version(store):
    record = load_record("preprint.json")
    store.add_source(record)
    claim = ClaimRecord(claim_id="c3", source_id=record.source_id, claim_text="x", claim_kind="hypothesis")
    store.add_claim(claim)
    updated = store.mark_claim_review_required("c3")
    assert updated.claim_kind == "review_required"
    assert updated.version == 2
    history = store.audit_history(entity_type="claim", entity_id="c3")
    assert len(history) == 2


# -- immutability / never silently rewrite -------------------------------------------------

def test_duplicate_source_id_raises_immutability_error(store):
    record = load_record("peer_reviewed_paper.json")
    store.add_source(record)
    with pytest.raises(ImmutabilityError):
        store.add_source(record)


def test_supersede_preserves_original_event(store):
    record = load_record("peer_reviewed_paper.json")
    store.add_source(record)
    store.supersede_source(record.source_id, superseded_by="fixture-newer-0002", reason="newer version found")
    current = store.get_source(record.source_id)
    assert current.status == "superseded"
    assert current.version == 2
    history = store.audit_history(entity_type="source", entity_id=record.source_id)
    assert len(history) == 2
    assert history[0]["record"]["status"] == "active"
    assert history[1]["record"]["status"] == "superseded"
    assert history[1]["reason"] == "newer version found"


def test_dispute_source_never_deletes_history(store):
    record = load_record("preprint.json")
    store.add_source(record)
    store.dispute_source(record.source_id, reason="contradicting evidence found")
    disputed = store.get_source(record.source_id)
    assert disputed.status == "disputed"
    assert disputed.evidence_class == "review_required"
    history = store.audit_history(entity_type="source", entity_id=record.source_id)
    assert len(history) == 2


# -- stable id derivation -----------------------------------------------------------------

def test_stable_source_id_deterministic():
    a = stable_source_id(identifier="10.1/x", identifier_type="doi", title="A")
    b = stable_source_id(identifier="10.1/x", identifier_type="doi", title="B")
    assert a == b


# -- network opt-in only --------------------------------------------------------------------

def test_network_fetch_disabled_by_default():
    with pytest.raises(NetworkDisabledError):
        fetch_doi_metadata("10.1016/j.neuron.2026.04.044")
    with pytest.raises(NetworkDisabledError):
        fetch_arxiv_metadata("2609.03987")


def test_no_network_during_full_ingest_cycle(store, monkeypatch):
    def _no_network(*args, **kwargs):
        raise AssertionError("network access attempted during offline ingest")

    monkeypatch.setattr(socket, "socket", _no_network)
    for name in ("peer_reviewed_paper.json", "preprint.json", "theory_paper.json"):
        record = load_record(name)
        assert validate_record(record).state == "valid"
        store.add_source(record)
    assert len(store.list_sources()) == 3


def test_module_import_touches_no_network(monkeypatch):
    def _no_network(*args, **kwargs):
        raise AssertionError("network access attempted merely by importing the package")

    monkeypatch.setattr(socket, "socket", _no_network)
    import importlib

    import tools.literature_evidence.store as store_module

    importlib.reload(store_module)


# -- finite JSON --------------------------------------------------------------------------

def test_to_finite_json_round_trips():
    record = load_record("peer_reviewed_paper.json")
    result = validate_record(record)
    text = to_finite_json({"record": record.to_dict(), "validation": result.to_dict()})
    parsed = json.loads(text)
    assert parsed["validation"]["state"] == "valid"


def test_to_finite_json_rejects_nan_and_infinity():
    with pytest.raises(NonFiniteValueError):
        to_finite_json({"score": float("nan")})
    with pytest.raises(NonFiniteValueError):
        to_finite_json({"score": float("inf")})


# -- repeatability / deterministic ----------------------------------------------------------

def test_deterministic_repeat_validation():
    record = load_record("peer_reviewed_paper.json")
    outputs = {to_finite_json(validate_record(record).to_dict()) for _ in range(15)}
    assert len(outputs) == 1


def test_deterministic_event_log(store):
    record = load_record("peer_reviewed_paper.json")
    store.add_source(record)
    snapshots = set()
    for _ in range(10):
        events = store.audit_history(entity_type="source", entity_id=record.source_id)
        snapshots.add(json.dumps(events, sort_keys=True))
    assert len(snapshots) == 1


# -- isolated subprocess CLI ------------------------------------------------------------------

def test_isolated_subprocess_cli_validate(tmp_path):
    record_path = tmp_path / "record.json"
    record_path.write_text((Path(__file__).parent / "fixtures" / "peer_reviewed_paper.json").read_text())
    result = subprocess.run(
        [sys.executable, "scripts/validate_literature_evidence.py", "validate", "--record", str(record_path)],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["state"] == "valid"


def test_isolated_subprocess_cli_validate_rejects_fabricated(tmp_path):
    record_path = tmp_path / "record.json"
    record_path.write_text((Path(__file__).parent / "fixtures" / "unresolved_identifier.json").read_text())
    result = subprocess.run(
        [sys.executable, "scripts/validate_literature_evidence.py", "validate", "--record", str(record_path)],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["state"] == "rejected_fabricated_identifier"


def test_isolated_subprocess_cli_ingest(tmp_path):
    record_path = tmp_path / "record.json"
    record_path.write_text((Path(__file__).parent / "fixtures" / "preprint.json").read_text())
    store_path = tmp_path / "events.jsonl"
    result = subprocess.run(
        [
            sys.executable, "scripts/validate_literature_evidence.py", "--store", str(store_path),
            "ingest", "--record", str(record_path),
        ],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert store_path.exists()


def test_no_heavy_import():
    script = (
        "import sys; "
        "import tools.literature_evidence as pkg; "
        "import tools.literature_evidence.models; "
        "import tools.literature_evidence.checksum; "
        "import tools.literature_evidence.identifiers; "
        "import tools.literature_evidence.validation; "
        "import tools.literature_evidence.store; "
        "import tools.literature_evidence.network; "
        "import tools.literature_evidence.reporting; "
        "heavy = {'numpy', 'scipy', 'sklearn', 'mne', 'torch', 'pandas', 'requests'}; "
        "print('LOADED_HEAVY=' + ','.join(sorted(heavy & set(sys.modules))))"
    )
    result = subprocess.run([sys.executable, "-c", script], cwd=REPO_ROOT, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    loaded = next(line for line in result.stdout.splitlines() if line.startswith("LOADED_HEAVY=")).split("=", 1)[1]
    assert loaded == ""
