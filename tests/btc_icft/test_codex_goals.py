import subprocess,sys

def test_goal_builder_validator(tmp_path):
    out=tmp_path/'g'
    subprocess.run([sys.executable,'-m','tools.codex_goals.goal_builder','--preset','toe_research','--out',str(out)],check=True)
    r=subprocess.run([sys.executable,'-m','tools.codex_goals.goal_validator','--root',str(out),'--json-out',str(out/'v.json')])
    assert r.returncode==0
    subprocess.run([sys.executable,'-m','tools.codex_goals.prompt_renderer','--root',str(out),'--out',str(out/'generated_codex_prompt.md')],check=True)
