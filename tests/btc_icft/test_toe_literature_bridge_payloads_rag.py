import subprocess, sys, json

def test_payload_flags(tmp_path):
    out=tmp_path/'p'
    subprocess.run([sys.executable,'-m','tools.toe_research.literature_bridge.command_center_payloads','--root',str(tmp_path),'--out',str(out)],check=True)
    d=json.loads((out/'toe_literature_bridge_status.json').read_text())
    assert d['live_api_calls_allowed'] is False

def test_rag_pack(tmp_path):
    out=tmp_path/'r'
    subprocess.run([sys.executable,'-m','tools.toe_research.literature_bridge.rag_pack','--root',str(tmp_path),'--out',str(out)],check=True)
    assert (out/'rag_pack_report.md').exists()
