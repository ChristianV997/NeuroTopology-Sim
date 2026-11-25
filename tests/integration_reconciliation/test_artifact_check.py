from __future__ import annotations

from tools.integration_reconciliation import artifact_check


def test_source_files_are_not_flagged():
    files = ["tools/integration_reconciliation/reconcile.py", "docs/integration_reconciliation/README.md"]
    assert artifact_check.find_suspect_artifacts(files) == []


def test_run_record_json_is_flagged():
    files = ["artifacts/pitnn/RunRecord.json"]
    assert artifact_check.find_suspect_artifacts(files) == ["artifacts/pitnn/RunRecord.json"]


def test_pycache_is_flagged():
    files = ["__pycache__/module.cpython-311.pyc"]
    assert artifact_check.find_suspect_artifacts(files) != []


def test_docs_json_exception_is_not_flagged():
    files = ["docs/examples/monorepo-repository.json"]
    assert artifact_check.find_suspect_artifacts(files) == []


def test_test_fixture_json_exception_is_not_flagged():
    files = ["tests/integration_reconciliation/fixtures/sample_manifest.json"]
    assert artifact_check.find_suspect_artifacts(files) == []


def test_governance_spec_yaml_is_not_flagged():
    files = ["governance/specs/HYP-20260101-001.yaml"]
    assert artifact_check.find_suspect_artifacts(files) == []


def test_mixed_list_flags_only_the_suspects():
    files = ["scripts/verify_integration_reconciliation.py", "results/output.png", "docs/README.md"]
    assert artifact_check.find_suspect_artifacts(files) == ["results/output.png"]
