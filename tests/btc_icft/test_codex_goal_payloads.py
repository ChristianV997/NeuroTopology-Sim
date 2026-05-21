import subprocess,sys,json
from pathlib import Path

def test_goal_payloads(tmp_path):
    out=tmp_path/'o'
    subprocess.run([sys.executable,'-m','tools.codex_goals.command_center_payloads','--root',str(tmp_path),'--out',str(out)],check=True)
    d=json.loads((out/'codex_goal_status.json').read_text())
    assert d['api_key_exposure_allowed'] is False

def test_agents_exists():
    assert Path('AGENTS.md').exists()
