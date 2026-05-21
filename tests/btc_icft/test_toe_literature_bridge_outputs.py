from tools.toe_research.literature_bridge import equation_registry
import json, tempfile, os, subprocess, sys

def test_eq_registry_contains_all(tmp_path):
    p=tmp_path/'eq.json'
    subprocess.run([sys.executable,'-m','tools.toe_research.literature_bridge.equation_registry','--out',str(p)],check=True)
    data=json.loads(p.read_text())
    ids={d['equation_id'] for d in data}
    assert all(f'EQ-{i:03d}' in ids for i in range(1,11))
