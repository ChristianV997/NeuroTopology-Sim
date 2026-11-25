import json
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from awareness_studio.literature_bridge.mapping import bridge_claim, bridge_source
from awareness_studio.literature_bridge.reporting import NonFiniteValueError, to_finite_json
from awareness_studio.research_cycle.models import EvidenceClass
from tools.literature_evidence.models import ClaimRecord, LiteratureRecord, SourceSnapshot as LitSnapshot

REPO_ROOT = Path(__file__).resolve().parents[4]


# -- valid peer-reviewed metadata --------------------------------------------------------

def test_valid_peer_reviewed_record_bridges(valid_peer_reviewed_record):
    outcome = bridge_source(valid_peer_reviewed_record, cycle_id="cycle-1")
    assert outcome.status == "bridged"
    assert outcome.record["snapshot_id"] == "lit-source-fixture-src-0001"
    assert outcome.record["source_format"] == "peer_reviewed_journal_article"
    assert outcome.record["data_mode"] == "literature_metadata"
    assert outcome.record["evidence_class"] == EvidenceClass.HYPOTHESIS.value
    assert outcome.preserved_state["identifier_validation_state"] == "valid"
    assert outcome.preserved_state["review_status"] == "reviewed_accepted"


def test_proxy_evidence_class_maps_to_proxy_inference(valid_peer_reviewed_record):
    data = valid_peer_reviewed_record.to_dict()
    data.pop("schema")
    data["evidence_class"] = "proxy"
    data["source_id"] = "fixture-src-proxy"
    record = LiteratureRecord.from_dict(data)
    outcome = bridge_source(record, cycle_id="cycle-1")
    assert outcome.status == "bridged"
    assert outcome.record["evidence_class"] == EvidenceClass.PROXY_INFERENCE.value


# -- preprint -----------------------------------------------------------------------------

def test_preprint_bridges_with_preprint_limitation(preprint_record):
    outcome = bridge_source(preprint_record, cycle_id="cycle-1")
    assert outcome.status == "bridged"
    assert outcome.record["source_format"] == "preprint"
    assert any("peer review" in l for l in outcome.record["scientific_limitations"])
    assert any("Not yet independently reviewed" in l for l in outcome.record["scientific_limitations"])


# -- theory paper ---------------------------------------------------------------------------

def test_theory_paper_bridges_with_theory_limitation(theory_paper_record):
    outcome = bridge_source(theory_paper_record, cycle_id="cycle-1")
    assert outcome.status == "bridged"
    assert outcome.record["source_format"] == "theory_paper"
    assert any("theoretical framework" in l for l in outcome.record["scientific_limitations"])
    # No source_url on this fixture -- falls back to a urn built from the identifier.
    assert outcome.record["source_uri"].startswith("urn:literature-evidence:isbn:")


# -- unresolved identifier --------------------------------------------------------------------

def test_unresolved_fabricated_identifier_is_not_bridged(valid_peer_reviewed_record):
    data = valid_peer_reviewed_record.to_dict()
    data.pop("schema")
    data["source_id"] = "fixture-src-unresolved"
    data["identifier"] = "not-a-real-doi"
    record = LiteratureRecord.from_dict(data)
    outcome = bridge_source(record, cycle_id="cycle-1")
    assert outcome.status == "not_bridged"
    assert "rejected_fabricated_identifier" in outcome.reason
    assert outcome.record is None
    assert outcome.preserved_state["identifier_validation_state"] == "rejected_fabricated_identifier"


def test_missing_identifier_is_not_bridged(valid_peer_reviewed_record):
    data = valid_peer_reviewed_record.to_dict()
    data.pop("schema")
    data["source_id"] = "fixture-src-missing-id"
    data["identifier"] = None
    record = LiteratureRecord.from_dict(data)
    outcome = bridge_source(record, cycle_id="cycle-1")
    assert outcome.status == "not_bridged"
    assert "rejected_missing_identity" in outcome.reason


# -- missing source content (metadata-only, no checksum) --------------------------------------

def test_missing_source_content_is_not_bridged(valid_peer_reviewed_record):
    data = valid_peer_reviewed_record.to_dict()
    data.pop("schema")
    data["source_id"] = "fixture-src-no-content"
    data["content_checksum"] = None
    data["excerpt_hash"] = None
    record = LiteratureRecord.from_dict(data)
    outcome = bridge_source(record, cycle_id="cycle-1")
    assert outcome.status == "not_bridged"
    assert outcome.reason.startswith("missing_snapshot")
    assert outcome.preserved_state["has_content_checksum"] is False
    assert outcome.preserved_state["has_excerpt_hash"] is False


# -- checksum mismatch -------------------------------------------------------------------------

def test_checksum_mismatch_against_real_local_snapshot_is_not_bridged(tmp_path, valid_peer_reviewed_record):
    real_file = tmp_path / "content.txt"
    real_file.write_text("the real captured content")
    data = valid_peer_reviewed_record.to_dict()
    data.pop("schema")
    data["source_id"] = "fixture-src-checksum-mismatch"
    record = LiteratureRecord.from_dict(data)
    snapshot = LitSnapshot(
        snapshot_id="snap-mismatch", source_id=record.source_id, kind="full_local_snapshot",
        local_path=str(real_file), content_checksum="0" * 64,  # deliberately wrong
    )
    outcome = bridge_source(record, cycle_id="cycle-1", snapshot=snapshot)
    assert outcome.status == "not_bridged"
    assert "rejected_invalid_checksum" in outcome.reason


def test_checksum_matching_real_local_snapshot_bridges(tmp_path, valid_peer_reviewed_record):
    from tools.literature_evidence.checksum import file_checksum

    real_file = tmp_path / "content.txt"
    real_file.write_text("the real captured content")
    data = valid_peer_reviewed_record.to_dict()
    data.pop("schema")
    data["source_id"] = "fixture-src-checksum-match"
    data["content_checksum"] = None
    record = LiteratureRecord.from_dict(data)
    snapshot = LitSnapshot(
        snapshot_id="snap-match", source_id=record.source_id, kind="full_local_snapshot",
        local_path=str(real_file), content_checksum=file_checksum(real_file),
    )
    outcome = bridge_source(record, cycle_id="cycle-1", snapshot=snapshot)
    assert outcome.status == "bridged"
    assert outcome.record["source_sha256"] == file_checksum(real_file)


def test_snapshot_from_another_source_is_not_bridged(valid_peer_reviewed_record):
    snapshot = LitSnapshot(
        snapshot_id="snap-other-source", source_id="different-source",
        kind="full_local_snapshot", local_path=None, content_checksum="a" * 64,
    )
    outcome = bridge_source(valid_peer_reviewed_record, cycle_id="cycle-1", snapshot=snapshot)
    assert outcome.status == "not_bridged"
    assert outcome.reason.startswith("snapshot_source_mismatch")


# -- disputed / superseded / retracted source status preserved --------------------------------

@pytest.mark.parametrize("status", ["disputed", "superseded", "retracted"])
def test_non_active_source_status_is_not_bridged(valid_peer_reviewed_record, status):
    data = valid_peer_reviewed_record.to_dict()
    data.pop("schema")
    data["source_id"] = f"fixture-src-{status}"
    data["status"] = status
    record = LiteratureRecord.from_dict(data)
    outcome = bridge_source(record, cycle_id="cycle-1")
    assert outcome.status == "not_bridged"
    assert outcome.reason == f"source_status={status}"


# -- claim downgrade ------------------------------------------------------------------------

def test_claim_bridges_as_pending_by_default():
    claim = ClaimRecord(claim_id="claim-1", source_id="fixture-src-0001", claim_text="X correlates with Y.")
    outcome = bridge_claim(claim, cycle_id="cycle-1", source_snapshot_id="lit-source-fixture-src-0001")
    assert outcome.status == "bridged"
    assert outcome.record["status"] == "PENDING"
    assert outcome.record["evidence_class"] == EvidenceClass.HYPOTHESIS.value
    assert outcome.record["evidence_ids"] == ["lit-source-fixture-src-0001"]


def test_claim_cannot_attach_to_an_unrelated_snapshot():
    claim = ClaimRecord(claim_id="claim-wrong-source", source_id="fixture-src-0001", claim_text="X correlates with Y.")
    outcome = bridge_claim(claim, cycle_id="cycle-1", source_snapshot_id="lit-source-different-source")
    assert outcome.status == "not_bridged"
    assert outcome.reason.startswith("source_snapshot_mismatch")


def test_claim_downgraded_to_review_required_is_preserved():
    """Requirement: a claim downgrade (hypothesis -> review_required, the
    literature-evidence store's own mark_claim_review_required) must be
    reflected in the bridged status, not silently dropped."""
    claim = ClaimRecord(
        claim_id="claim-2", source_id="fixture-src-0001", claim_text="X correlates with Y.",
        claim_kind="review_required", version=2,
    )
    outcome = bridge_claim(claim, cycle_id="cycle-1", source_snapshot_id="lit-source-fixture-src-0001")
    assert outcome.status == "bridged"
    assert outcome.record["status"] == "REVIEW_REQUIRED"
    assert outcome.preserved_state["claim_kind"] == "review_required"
    assert outcome.preserved_state["claim_version"] == 2


def test_disputed_claim_status_is_not_bridged():
    claim = ClaimRecord(
        claim_id="claim-3", source_id="fixture-src-0001", claim_text="X correlates with Y.",
        status="disputed",
    )
    outcome = bridge_claim(claim, cycle_id="cycle-1", source_snapshot_id="lit-source-fixture-src-0001")
    assert outcome.status == "not_bridged"
    assert outcome.reason == "claim_status=disputed"


def test_bridged_claim_never_uses_causal_language_guard_incorrectly():
    """A hypothesis proposing causation is ordinary pre-evidence science
    (this bridge never emits PROXY_INFERENCE, so research_cycle's
    causal-language guard for proxy claims never fires here)."""
    claim = ClaimRecord(
        claim_id="claim-4", source_id="fixture-src-0001",
        claim_text="We hypothesize that slow breathing causes reduced risk aversion.",
    )
    outcome = bridge_claim(claim, cycle_id="cycle-1", source_snapshot_id="lit-source-fixture-src-0001")
    assert outcome.status == "bridged"
    assert outcome.record["evidence_class"] == EvidenceClass.HYPOTHESIS.value


# -- never promotes to empirical/causal/confirmed -----------------------------------------------

def test_bridge_never_emits_empirical_or_formal_evidence_class(valid_peer_reviewed_record):
    outcome = bridge_source(valid_peer_reviewed_record, cycle_id="cycle-1")
    assert outcome.record["evidence_class"] not in (
        EvidenceClass.FORMAL_STATISTICAL_EVIDENCE.value, EvidenceClass.DESCRIPTIVE_EMPIRICAL.value,
    )
    assert outcome.record["data_mode"] not in ("empirical", "synthetic_demo")


def test_bridge_source_all_evidence_classes_map_to_non_confirmed_values(valid_peer_reviewed_record):
    forbidden = {EvidenceClass.FORMAL_STATISTICAL_EVIDENCE.value, EvidenceClass.DESCRIPTIVE_EMPIRICAL.value}
    for lit_class in ("hypothesis", "theoretical", "review_required", "proxy"):
        data = valid_peer_reviewed_record.to_dict()
        data.pop("schema")
        data["source_id"] = f"fixture-src-{lit_class}"
        data["evidence_class"] = lit_class
        record = LiteratureRecord.from_dict(data)
        outcome = bridge_source(record, cycle_id="cycle-1")
        assert outcome.status == "bridged"
        assert outcome.record["evidence_class"] not in forbidden


# -- no-network ---------------------------------------------------------------------------------

def test_no_network_during_full_bridge_cycle(valid_peer_reviewed_record, monkeypatch):
    def _no_network(*args, **kwargs):
        raise AssertionError("network access attempted during literature bridging")

    monkeypatch.setattr(socket, "socket", _no_network)
    source_outcome = bridge_source(valid_peer_reviewed_record, cycle_id="cycle-1")
    assert source_outcome.status == "bridged"
    claim = ClaimRecord(claim_id="claim-5", source_id=valid_peer_reviewed_record.source_id, claim_text="x")
    claim_outcome = bridge_claim(claim, cycle_id="cycle-1", source_snapshot_id=source_outcome.record["snapshot_id"])
    assert claim_outcome.status == "bridged"


def test_module_import_touches_no_network(monkeypatch):
    def _no_network(*args, **kwargs):
        raise AssertionError("network access attempted merely by importing the bridge")

    monkeypatch.setattr(socket, "socket", _no_network)
    import importlib

    import awareness_studio.literature_bridge.mapping as mapping_module

    importlib.reload(mapping_module)


# -- finite JSON -----------------------------------------------------------------------------

def test_to_finite_json_round_trips(valid_peer_reviewed_record):
    outcome = bridge_source(valid_peer_reviewed_record, cycle_id="cycle-1")
    parsed = json.loads(to_finite_json(outcome))
    assert parsed["status"] == "bridged"
    assert parsed["record"]["snapshot_id"] == "lit-source-fixture-src-0001"


def test_to_finite_json_rejects_nan_and_infinity():
    from awareness_studio.literature_bridge.mapping import BridgeOutcome

    outcome = BridgeOutcome(
        status="not_bridged", reason="test", record=None,
        preserved_state={"confidence": float("nan")},
    )
    with pytest.raises(NonFiniteValueError):
        to_finite_json(outcome)

    outcome_inf = BridgeOutcome(
        status="not_bridged", reason="test", record=None,
        preserved_state={"confidence": float("inf")},
    )
    with pytest.raises(NonFiniteValueError):
        to_finite_json(outcome_inf)


def test_deterministic_repeat(valid_peer_reviewed_record):
    outputs = {to_finite_json(bridge_source(valid_peer_reviewed_record, cycle_id="cycle-1")) for _ in range(15)}
    assert len(outputs) == 1


# -- isolated subprocess / no-heavy-import --------------------------------------------------

def test_no_heavy_import():
    script = (
        "import sys; "
        "import awareness_studio.literature_bridge as pkg; "
        "import awareness_studio.literature_bridge.mapping; "
        "import awareness_studio.literature_bridge.reporting; "
        "import awareness_studio.literature_bridge.repo_paths; "
        "heavy = {'numpy', 'scipy', 'sklearn', 'mne', 'torch', 'pandas', 'requests'}; "
        "print('LOADED_HEAVY=' + ','.join(sorted(heavy & set(sys.modules))))"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=REPO_ROOT / "apps" / "awareness_studio",
        env={**__import__("os").environ, "PYTHONPATH": "src"},
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    loaded = next(line for line in result.stdout.splitlines() if line.startswith("LOADED_HEAVY=")).split("=", 1)[1]
    assert loaded == ""
