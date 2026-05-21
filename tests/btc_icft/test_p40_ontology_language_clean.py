import json
import subprocess
import sys
from pathlib import Path


def test_repo_ontology_language_scan_clean():
    out_json = Path('outputs/btc_icft/ontology_claim_language_validation.json')
    out_md = Path('outputs/btc_icft/ontology_claim_language_validation.md')
    cmd = [
        sys.executable,
        'tools/validate_ontology_claim_language.py',
        '--root', '.',
        '--scan-mode', 'repo',
        '--baseline', 'contracts/btc_icft/ontology_claims/claim_language_baseline.json',
        '--json-out', str(out_json),
        '--markdown-out', str(out_md),
    ]
    result = subprocess.run(cmd)
    assert result.returncode == 0
    payload = json.loads(out_json.read_text(encoding='utf-8'))
    assert payload['ok'] is True
    assert payload['unbaselined_violation_count'] == 0
