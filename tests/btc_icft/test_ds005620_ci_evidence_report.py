from __future__ import annotations

import json
from pathlib import Path

import importlib.util

mod_path = Path('tools/build_ds005620_ci_evidence_report.py')
spec = importlib.util.spec_from_file_location('ci_report_tool', mod_path)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(module)
BANNED_PHRASES = module.BANNED_PHRASES
build_report = module.build_report
build_markdown = module.build_markdown


def _seed(root: Path):
    root.mkdir(parents=True, exist_ok=True)
    (root / 'ds005620_real_benchmark_execution.json').write_text(json.dumps({
        'dataset_id': 'DS005620', 'benchmark_completed': True,
        'p12_executed': True, 'p13_executed': True, 'p11_executed': True,
        'p12_succeeded': True, 'p13_succeeded': True, 'p11_succeeded': True,
    }), encoding='utf-8')
    (root / 'stage_results.json').write_text(json.dumps({'stages':[{'stage_id':'P13','actual_outputs':['x.csv']}]}), encoding='utf-8')
    (root / 'omega_event.json').write_text(json.dumps({'labels_inferred':False,'targets_fabricated':False,'source_contracts_modified':False,'legacy_mt_real_modified':False,'contracts_activated_by_executor':False,'p11_promotion_gate_modified':False,'consciousness_claims_made':False}), encoding='utf-8')


def test_report_writes_json_and_markdown(tmp_path: Path):
    _seed(tmp_path)
    vs = tmp_path / 'validation_summary.json'; vs.write_text(json.dumps({'ok': True, 'checked_artifacts': [], 'checked_stages': [], 'failures': []}))
    cs = tmp_path / 'contract_validation_summary.json'; cs.write_text(json.dumps({'ok': True, 'validated_artifacts': [], 'failures': []}))
    rep = build_report(tmp_path, vs, cs)
    (tmp_path / 'ci_evidence_report.json').write_text(json.dumps(rep), encoding='utf-8')
    (tmp_path / 'ci_evidence_report.md').write_text(build_markdown(rep), encoding='utf-8')
    assert (tmp_path / 'ci_evidence_report.json').is_file()
    assert (tmp_path / 'ci_evidence_report.md').is_file()


def test_report_json_required_keys(tmp_path: Path):
    _seed(tmp_path)
    rep = build_report(tmp_path, tmp_path/'missing_v.json', tmp_path/'missing_c.json')
    required = {'report_version','dataset_id','pipeline_id','artifact_root','benchmark_completed','validation_ok','contract_validation_ok','p12_executed','p13_executed','p11_executed','p12_succeeded','p13_succeeded','p11_succeeded','explicit_targets_available','predictive_metrics_available','auc_m','auc_mt','omega_invariants','checked_artifacts','checked_stages','contract_validated_artifacts','failures','warnings','safe_claim','ci_claim_scope'}
    assert required.issubset(set(rep.keys()))


def test_reads_summary_flags(tmp_path: Path):
    _seed(tmp_path)
    vs = tmp_path / 'validation_summary.json'; vs.write_text(json.dumps({'ok': True, 'checked_artifacts': [], 'checked_stages': [], 'failures': []}))
    cs = tmp_path / 'contract_validation_summary.json'; cs.write_text(json.dumps({'ok': False, 'validated_artifacts': [], 'failures': ['x']}))
    rep = build_report(tmp_path, vs, cs)
    assert rep['benchmark_completed'] is True
    assert rep['validation_ok'] is True
    assert rep['contract_validation_ok'] is False


def test_reads_p11_metrics_when_present(tmp_path: Path):
    _seed(tmp_path)
    m = tmp_path / 'stage_outputs/p11_signal_mt/metrics_signal_mt.json'
    m.parent.mkdir(parents=True, exist_ok=True)
    m.write_text(json.dumps({'auc_m': 0.7, 'auc_mt': 0.8}), encoding='utf-8')
    rep = build_report(tmp_path, tmp_path/'missing_v.json', tmp_path/'missing_c.json')
    assert rep['predictive_metrics_available'] is True
    assert rep['auc_m'] == 0.7
    assert rep['auc_mt'] == 0.8


def test_claim_scope_and_markdown_guardrails(tmp_path: Path):
    _seed(tmp_path)
    rep = build_report(tmp_path, tmp_path/'missing_v.json', tmp_path/'missing_c.json')
    assert rep['ci_claim_scope'] == 'mock_e2e_engineering_validation_only'
    md = build_markdown(rep).lower()
    for phrase in BANNED_PHRASES:
        assert phrase not in md


def test_missing_optional_metrics_warns(tmp_path: Path):
    _seed(tmp_path)
    rep = build_report(tmp_path, tmp_path/'missing_v.json', tmp_path/'missing_c.json')
    assert rep['predictive_metrics_available'] is False
    assert any('missing P11 metrics' in w for w in rep['warnings'])


def test_missing_validation_summary_warns_and_false(tmp_path: Path):
    _seed(tmp_path)
    rep = build_report(tmp_path, tmp_path/'missing_v.json', tmp_path/'missing_c.json')
    assert rep['validation_ok'] is False
    assert any('missing validation summary' in w for w in rep['warnings'])


def test_missing_contract_summary_warns_and_false(tmp_path: Path):
    _seed(tmp_path)
    rep = build_report(tmp_path, tmp_path/'missing_v.json', tmp_path/'missing_c.json')
    assert rep['contract_validation_ok'] is False
    assert any('missing contract summary' in w for w in rep['warnings'])


# O4 ontology integration tests

def _seed_ontology_root(tmp_path: Path) -> Path:
    ont = tmp_path / "ontology"
    ont.mkdir()
    (ont / "ontology_claim_evaluation.json").write_text(json.dumps({
        "max_claim_scope": "engineering_runtime",
        "promotion_state": "engineering_validated",
        "ontology_claim_status": "ontology_quarantined",
        "claims": [],
        "blockers": ["run_mode_is_mock_e2e"],
        "safe_claim": "Ontology evaluation constrains claim scopes.",
    }), encoding="utf-8")
    (ont / "ontology_promotion_decision.json").write_text(json.dumps({
        "ontology_promotion": False,
        "empirical_marker_promotion": False,
        "empirical_topology_promotion": False,
        "mechanism_promotion": False,
        "metaphysical_promotion": False,
    }), encoding="utf-8")
    (ont / "bridge_claim_status.json").write_text(
        json.dumps({"bridge_statuses": []}), encoding="utf-8"
    )
    return ont


def test_ci_report_includes_ontology_fields(tmp_path: Path):
    _seed(tmp_path)
    ont = _seed_ontology_root(tmp_path)
    rep = build_report(tmp_path, tmp_path / "missing_v.json", tmp_path / "missing_c.json",
                       ontology_root=str(ont))
    assert "ontology_available" in rep
    assert "ontology_max_claim_scope" in rep
    assert "ontology_promotion_state" in rep
    assert "ontology_claim_status" in rep
    assert "ontology_promotion" in rep
    assert "empirical_marker_promotion" in rep
    assert "empirical_topology_promotion" in rep
    assert "mechanism_promotion" in rep
    assert "metaphysical_promotion" in rep


def test_ci_report_markdown_includes_ontology_section(tmp_path: Path):
    _seed(tmp_path)
    ont = _seed_ontology_root(tmp_path)
    rep = build_report(tmp_path, tmp_path / "missing_v.json", tmp_path / "missing_c.json",
                       ontology_root=str(ont))
    md = build_markdown(rep)
    assert "## Ontology Evaluation Summary" in md
    assert "ontology_available" in md


def test_ci_report_does_not_promote_empirical_claims_from_mock(tmp_path: Path):
    _seed(tmp_path)
    ont = _seed_ontology_root(tmp_path)
    rep = build_report(tmp_path, tmp_path / "missing_v.json", tmp_path / "missing_c.json",
                       ontology_root=str(ont))
    assert rep["empirical_marker_promotion"] is False
    assert rep["empirical_topology_promotion"] is False
    assert rep["mechanism_promotion"] is False
    assert rep["metaphysical_promotion"] is False
    assert rep["ontology_promotion"] is False


def test_ci_report_warns_when_ontology_missing(tmp_path: Path):
    _seed(tmp_path)
    rep = build_report(tmp_path, tmp_path / "missing_v.json", tmp_path / "missing_c.json",
                       ontology_root=str(tmp_path / "nonexistent_ont"))
    assert rep["ontology_available"] is False
    assert "ontology_evaluation_missing" in rep["warnings"]
