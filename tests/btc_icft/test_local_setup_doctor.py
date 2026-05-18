import json
from pathlib import Path
from tools.local_setup import env_probe, setup_plan


def test_env_probe_writes_json_markdown(tmp_path: Path):
    report = env_probe.probe_environment(cwd=Path.cwd())
    out = tmp_path / 'environment_report.json'
    md = tmp_path / 'environment_report.md'
    from tools.local_setup.reporting import write_json, write_markdown
    write_json(str(out), report)
    write_markdown(str(md), env_probe.to_markdown(report))
    assert out.exists() and md.exists()


def test_env_probe_no_secret_values(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'secret-value')
    report = env_probe.probe_environment(cwd=Path.cwd())
    s = json.dumps(report)
    assert 'secret-value' not in s
    assert report['env_vars_present']['OPENAI_API_KEY'] is True


def test_windows_fixture_warns(monkeypatch):
    monkeypatch.setattr(env_probe.platform, 'system', lambda: 'Windows')
    monkeypatch.setattr(env_probe.platform, 'release', lambda: '10')
    report = env_probe.probe_environment(cwd=Path.cwd())
    assert report['platform']['is_windows_native'] is True
    assert report['detected_environment'] in {'warning', 'error'}


def test_setup_plan_contains_required_steps(monkeypatch):
    monkeypatch.setattr(setup_plan.platform, 'system', lambda: 'Windows')
    plan = setup_plan.build_plan()
    joined = '\n'.join(plan['steps'])
    assert 'WSL2' in joined
    assert 'pip install -r requirements.txt' in joined
    assert 'python main.py --mode synthetic' in joined
    assert 'code .' in joined
