"""HtmlReportPackV1: dict/JSON roundtrip, deterministic ID, and structural
validation rules. Synthetic fixtures only.
"""
from __future__ import annotations

from workflows.html_report_pack import HtmlReportPackV1, compute_html_pack_id
from workflows.html_validation import HtmlReportPackValidationError


def _minimal_pack(**overrides) -> HtmlReportPackV1:
    kwargs = dict(
        report_pack_id="report-pack-1", dataset_id="demo_ds", input_mode="mne_bids_derived_features",
        modality="EEG", pipeline_run_id="pipeline-1", title="Demo Report",
        source_report_pack_path="outputs/report_packs/demo/ReportPack.json",
        output_root="outputs/report_packs/demo/html",
        limitations=["test"], blocked_interpretations=["This report pack does not support a clinical claim."],
    )
    kwargs.update(overrides)
    return HtmlReportPackV1.make(**kwargs)


def test_pack_dict_roundtrip():
    pack = _minimal_pack()
    d = pack.to_dict()
    pack2 = HtmlReportPackV1.from_dict(d)
    assert pack2.to_dict() == d


def test_pack_json_roundtrip():
    pack = _minimal_pack()
    text = pack.to_json()
    pack2 = HtmlReportPackV1.from_json(text)
    assert pack2.to_dict() == pack.to_dict()


def test_pack_write_json_roundtrip(tmp_path):
    pack = _minimal_pack()
    path = pack.write_json(tmp_path / "HtmlReportPack.json")
    pack2 = HtmlReportPackV1.from_json(path.read_text(encoding="utf-8"))
    assert pack2.html_pack_id == pack.html_pack_id


def test_html_pack_id_deterministic():
    pack_a = _minimal_pack()
    pack_b = _minimal_pack(title="a totally different title")
    assert pack_a.html_pack_id == pack_b.html_pack_id
    assert pack_a.html_pack_id == compute_html_pack_id(
        report_pack_id="report-pack-1", dataset_id="demo_ds", input_mode="mne_bids_derived_features",
        source_evidence_report_paths=[],
    )


def test_html_pack_id_differs_across_identity_fields():
    base = _minimal_pack()
    other_report_pack = _minimal_pack(report_pack_id="report-pack-2")
    other_reports = _minimal_pack(source_evidence_report_paths=["outputs/x/EvidenceReport.json"])
    assert base.html_pack_id != other_report_pack.html_pack_id
    assert base.html_pack_id != other_reports.html_pack_id


def test_created_at_excluded_from_html_pack_id():
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    later = now + timedelta(days=365)
    pack_now = _minimal_pack(_now=now)
    pack_later = _minimal_pack(_now=later)
    assert pack_now.created_at != pack_later.created_at
    assert pack_now.html_pack_id == pack_later.html_pack_id


def test_validate_or_raise_raises():
    pack = _minimal_pack(limitations=[])
    try:
        pack.validate_or_raise()
        assert False, "expected HtmlReportPackValidationError"
    except HtmlReportPackValidationError:
        pass


def test_validation_fails_on_empty_limitations():
    pack = _minimal_pack(limitations=[])
    assert any("rule 1" in e for e in pack.validate())


def test_validation_fails_on_empty_blocked_interpretations():
    pack = _minimal_pack(blocked_interpretations=[])
    assert any("rule 2" in e for e in pack.validate())


def test_validation_fails_on_missing_source_report_pack_path():
    pack = _minimal_pack(source_report_pack_path="")
    assert any("rule 3" in e for e in pack.validate())


def test_validation_fails_on_invalid_output_root():
    pack = _minimal_pack(output_root="/etc/evil")
    assert any("rule 5" in e for e in pack.validate())


def test_validation_fails_on_output_root_traversal():
    pack = _minimal_pack(output_root="outputs/../secrets")
    assert any("rule 5" in e for e in pack.validate())


def test_html_pack_id_mismatch_is_a_validation_error():
    pack = _minimal_pack()
    pack.html_pack_id = "not-the-real-id"
    errors = pack.validate()
    assert any("does not match deterministic id" in e for e in errors)


def test_pack_never_carries_claim_scope_or_evidence_level_field():
    pack = _minimal_pack()
    assert not hasattr(pack, "claim_scope")
    assert not hasattr(pack, "evidence_level")


def test_banned_phrase_in_free_text_fails():
    pack = _minimal_pack(title="this confirms diagnosis beyond doubt")
    errors = pack.validate()
    assert any("banned phrase" in e for e in errors)


def test_valid_pack_has_no_errors():
    assert _minimal_pack().validate() == []
