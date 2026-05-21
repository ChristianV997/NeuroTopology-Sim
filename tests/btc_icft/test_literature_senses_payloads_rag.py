import subprocess, pathlib, json

def test_payloads_rag_obsidian():
 subprocess.check_call(['make','literature-senses-cycle'])
 out=pathlib.Path('outputs/command_center/mock_payloads/literature_senses_status.json')
 assert out.exists() and json.loads(out.read_text())['live_api_calls_enabled'] is False
 assert pathlib.Path('outputs/literature_senses/rag_pack/rag_forbidden_answer_patterns.json').exists()
