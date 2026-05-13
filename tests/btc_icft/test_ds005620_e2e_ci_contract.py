from pathlib import Path


def test_workflow_file_exists():
    assert Path('.github/workflows/ds005620-e2e.yml').is_file()


def test_workflow_contains_required_commands():
    txt = Path('.github/workflows/ds005620-e2e.yml').read_text(encoding='utf-8')
    assert 'python -m governance.validate' in txt
    assert 'test_ds005620_real_benchmark_executor.py -q' in txt
    assert 'make ds005620-e2e-mock' in txt
    assert 'make validate-ds005620-e2e' in txt
    assert 'make validate-ds005620-e2e-json' in txt
    assert 'make validate-ds005620-contracts' in txt
    assert 'make ds005620-ci-evidence-report' in txt
    assert 'test_ds005620_e2e_ci_contract.py -q' in txt


def test_workflow_contains_evidence_upload_contract():
    txt = Path('.github/workflows/ds005620-e2e.yml').read_text(encoding='utf-8')
    assert 'actions/upload-artifact@v4' in txt
    assert 'name: ds005620-mock-e2e-evidence' in txt
    assert 'ci_evidence_report.json' in txt
    assert 'ci_evidence_report.md' in txt
    assert 'validation_summary.json' in txt
    assert 'contract_validation_summary.json' in txt
    assert 'metrics_signal_mt.json' in txt


def test_makefile_contains_ci_targets():
    txt = Path('Makefile').read_text(encoding='utf-8')
    assert 'ds005620-e2e-ci:' in txt
    assert 'validate-ds005620-e2e-json:' in txt
    assert 'validate-ds005620-contracts:' in txt
    assert 'ds005620-ci-evidence-report:' in txt
    assert 'validate-ds005620-contracts' in txt.split('ds005620-e2e-ci:')[1]
    assert 'ds005620-ci-evidence-report' in txt.split('ds005620-e2e-ci:')[1]


def test_workflow_does_not_run_dangerous_real_execute():
    txt = Path('.github/workflows/ds005620-e2e.yml').read_text(encoding='utf-8')
    assert '--execute --peer-reviewed-contract-confirmed' not in txt or '--mock-e2e' in txt


def test_workflow_does_not_require_real_data_path():
    txt = Path('.github/workflows/ds005620-e2e.yml').read_text(encoding='utf-8')
    assert 'data/DS005620' not in txt
