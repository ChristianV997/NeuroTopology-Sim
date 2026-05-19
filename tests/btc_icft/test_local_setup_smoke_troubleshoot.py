from pathlib import Path
from tools.local_setup import smoke_runner, troubleshoot


def test_dry_run_plans_only():
    res = smoke_runner.run('dry-run', 1, True, 8)
    assert res['mode'] == 'dry-run'
    assert all(x['status'] == 'planned' for x in res['commands'])


def test_blocked_command_refused(monkeypatch):
    monkeypatch.setattr(smoke_runner, 'planned_commands', lambda has_make: ['python bad --execute --peer-reviewed-contract-confirmed'])
    res = smoke_runner.run('run', 1, True, 8)
    assert res['commands'][0]['status'] == 'skipped'


def test_troubleshoot_hints():
    env = {'python': {'virtualenv_active': False}, 'repo': {'root': '/mnt/c/ScienceR-Dsim'}}
    smoke = {'commands': [{'stderr_tail': 'make: command not found\nNo module named pytest'}]}
    out = troubleshoot.generate(env, smoke)
    assert 'install make' in out
    assert 'pip install -r requirements.txt' in out
    assert 'source .venv/bin/activate' in out
    assert '/mnt/c/' in out


def test_makefile_and_docs_exist():
    mk = Path('Makefile').read_text(encoding='utf-8')
    for k in ['laptop-setup-doctor', 'laptop-setup-plan', 'laptop-smoke', 'laptop-smoke-dry-run', 'laptop-safe-run']:
        assert k in mk
    assert Path('docs/laptop_local_run_guide.md').exists()
    assert Path('docs/windows_wsl_vscode_setup.md').exists()
