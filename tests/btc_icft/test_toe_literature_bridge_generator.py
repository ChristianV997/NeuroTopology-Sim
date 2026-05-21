import subprocess, sys
from pathlib import Path

def test_generator_writes(tmp_path):
    out=tmp_path/'o'
    subprocess.run([sys.executable,'-m','tools.toe_research.literature_bridge.generator','--roots','missing_a','missing_b','--out',str(out)],check=True)
    assert (out/'toe_literature_priority_matrix.json').exists()
    assert 'not_available' in (out/'toe_literature_priority_matrix.json').read_text()
