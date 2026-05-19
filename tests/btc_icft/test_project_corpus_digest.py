from __future__ import annotations
import json, zipfile, subprocess, sys
from pathlib import Path


def run(*args):
    subprocess.run([sys.executable, '-m', *args], check=True)


def test_inventory_and_digest_cycle(tmp_path: Path):
    root = tmp_path / 'src'; root.mkdir()
    (root / 'manuscript').mkdir(); (root/'manuscript'/'paper.tex').write_text('draft hypothesis only', encoding='utf-8')
    (root/'simulator_config.yaml').write_text('mode: sim', encoding='utf-8')
    (root/'ontology_soul.md').write_text('unsafe topic', encoding='utf-8')
    z = root/'assets.zip'
    with zipfile.ZipFile(z, 'w') as zf: zf.writestr('folder/a.txt', 'hello')
    out = tmp_path / 'out'
    run('tools.project_corpus_digest.inventory','--roots',str(root),'--out',str(out))
    for f in ['local_source_registry.json','local_file_inventory.json','archive_inventory.json','generation_manifest.json']:
        assert (out/f).exists()
    run('tools.project_corpus_digest.digestor','--root',str(out),'--out',str(out))
    for f in ['manuscript_digest_matrix.json','simulator_artifact_matrix.json','speculative_quarantine_matrix.json','publication_lane_registry.json','reusable_asset_registry.json']:
        assert (out/f).exists()


def test_validator_forbidden_phrase_fails(tmp_path: Path):
    out = tmp_path/'o'; out.mkdir()
    minimal=[{"id":"1","name":"a","path":"a","artifact_type":"manuscript","category":"manuscripts","claim_scope":"publication_safe","evidence_state":"artifact_derived","allowed_use":"x","prohibited_claims":[],"safety_notes":[]}]
    for f in ['local_source_registry.json','local_file_inventory.json','archive_inventory.json','manuscript_digest_matrix.json','simulator_artifact_matrix.json','os_runtime_extraction_matrix.json','book_system_extraction_matrix.json','speculative_quarantine_matrix.json','publication_lane_registry.json','reusable_asset_registry.json']:
        (out/f).write_text(json.dumps(minimal), encoding='utf-8')
    (out/'generation_manifest.json').write_text('{}', encoding='utf-8')
    (out/'claim_risk_report.md').write_text('unsafe phrase field: proves consciousness', encoding='utf-8')
    (out/'system_integration_digest.md').write_text('proves consciousness', encoding='utf-8')
    p=subprocess.run([sys.executable,'-m','tools.project_corpus_digest.validator','--root',str(out),'--json-out',str(out/'v.json')])
    assert p.returncode != 0


def test_command_center_flags_false(tmp_path: Path):
    out=tmp_path/'o'; out.mkdir(); cc=tmp_path/'cc'
    (out/'local_source_registry.json').write_text('[]', encoding='utf-8')
    (out/'claim_risk_matrix.json').write_text('[]', encoding='utf-8')
    (out/'publication_lane_registry.json').write_text('[]', encoding='utf-8')
    (out/'reusable_asset_registry.json').write_text('[]', encoding='utf-8')
    run('tools.project_corpus_digest.command_center_payloads','--root',str(out),'--out',str(cc))
    data=json.loads((cc/'project_corpus_status.json').read_text(encoding='utf-8'))
    assert data['ontology_promotion_allowed'] is False and data['api_key_exposure_allowed'] is False
