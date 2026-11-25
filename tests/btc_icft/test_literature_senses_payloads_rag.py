import subprocess, pathlib, json

# `make literature-senses-cycle` regenerates in-tree command-center payloads, including the
# git-tracked guardrails_status.json. Restore every tracked file it rewrites so running the
# suite never leaves the working tree dirty (a dirty tree breaks later diff-based tests).
_TRACKED_SIDE_EFFECTS = (
    pathlib.Path('outputs/command_center/mock_payloads/guardrails_status.json'),
)


def test_payloads_rag_obsidian():
    snapshot = {p: p.read_bytes() for p in _TRACKED_SIDE_EFFECTS if p.exists()}
    try:
        subprocess.check_call(['make', 'literature-senses-cycle'])
        out = pathlib.Path('outputs/command_center/mock_payloads/literature_senses_status.json')
        assert out.exists() and json.loads(out.read_text())['live_api_calls_enabled'] is False
        assert pathlib.Path('outputs/literature_senses/rag_pack/rag_forbidden_answer_patterns.json').exists()
    finally:
        for path, data in snapshot.items():
            path.write_bytes(data)
