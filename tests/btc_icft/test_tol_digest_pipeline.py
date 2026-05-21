from pathlib import Path
import json, tempfile
from tools.tol_digest.source_registry import build_registry
from tools.tol_digest.claim_extractor import extract_claims_from_text
from tools.tol_digest.tier_classifier import classify_claim
from tools.tol_digest.mapping_builder import DOCTRINE_MAP, OBS_MAP
from tools.tol_digest.report_writer import main as report_main
from tools.tol_digest.validator import main as validate_main
from tools.tol_digest.obsidian_sync import main as sync_main

def test_missing_inputs_writes_empty_registry_and_warning():
    reg=build_registry('no_such_tol_input')
    assert reg['sources']==[] and reg['warnings']

def test_registry_scans_and_pdf_unsupported():
    with tempfile.TemporaryDirectory() as d:
        p=Path(d)
        for n in ['a.txt','b.md','c.tex','d.json','e.pdf']:
            (p/n).write_text('dukkha Qabs',encoding='utf-8')
        reg=build_registry(d)
        exts={s['extension'] for s in reg['sources']}
        assert {'.txt','.md','.tex','.json','.pdf'}.issubset(exts)
        assert any('unsupported' in s['parse_status'] for s in reg['sources'] if s['extension']=='.pdf')

def test_extractor_and_classifier_rules():
    claims=extract_claims_from_text('dukkha as high exit cost\nQ Qabs fdress in anesthesia\nsoul is real\ntheory validated\nkarmic deletion', 's1')
    assert any('dukkha' in c['normalized_text'] for c in claims)
    assert any('qabs' in c['normalized_text'] for c in claims)
    assert classify_claim('dukkha is high exit-cost model')[0]=='book_safe_core'
    assert classify_claim('anesthesia Q Qabs fdress candidate telemetry')[0]=='research_hypothesis'
    assert classify_claim('soul is real')[0] in {'speculative_quarantined','unsafe_or_requires_rewrite'}
    assert classify_claim('theory validated')[0]=='unsafe_or_requires_rewrite'
    assert classify_claim('karmic deletion')[0] in {'speculative_quarantined','unsafe_or_requires_rewrite'}
    assert classify_claim('kl1 topological afterlife quantum-vacuum interface')[0]=='speculative_quarantined'
    assert classify_claim('instant arhat state')[0]=='unsafe_or_requires_rewrite'

def test_maps_required_keys():
    assert 'dukkha' in DOCTRINE_MAP and 'exit_cost_proxy' in OBS_MAP

def test_report_validator_sync_and_files_and_makefile_docs():
    with tempfile.TemporaryDirectory() as d:
        root=Path(d); inp=root/'inputs'/'tol'; inp.mkdir(parents=True)
        (inp/'x.md').write_text('dukkha high exit-cost\nQ Qabs fdress anesthesia\nsoul is real\n',encoding='utf-8')
        (inp/'Book seed 2 ToL science .txt').write_text('dukkha and samadhi with no trauma deletion guarantee',encoding='utf-8')
        (inp/'Consciousness systems science .txt').write_text('KL1 and topological afterlife and quantum-vacuum are speculative',encoding='utf-8')
        out=root/'outputs'/'tol_digest'
        assert report_main(['--input',str(inp),'--out',str(out)])==0
        req=['source_registry.json','claim_inventory.json','claim_tier_matrix.json','doctrine_to_construct_map.json','observables_map.json','book_insights.md','research_hypotheses.md','quarantine_report.md','next_actions.json','tol_digest_report.md','source_specific/uploaded_source_claim_risk_matrix.json','source_specific/uploaded_source_integration_plan.md']
        for f in req: assert (out/f).exists()
        assert 'Stability vs freedom' in (out/'book_insights.md').read_text(encoding='utf-8')
        assert 'Falsifiers' in (out/'research_hypotheses.md').read_text(encoding='utf-8')
        assert 'soul is real' in (out/'quarantine_report.md').read_text(encoding='utf-8')
        assert validate_main(['--root',str(out),'--json-out',str(out/'tol_digest_validation.json')])==0
        vault=root/'obsidian'; assert sync_main(['--root',str(out),'--vault',str(vault),'--out',str(out/'tol_obsidian_sync_result.json')])==0
        assert (vault/'07_ToL'/'ToL_Index.md').exists()
        assert (vault/'07_ToL'/'Uploaded_Source_Index.md').exists()
        assert (out/'source_specific'/'book_seed_2_tol_science_digest.md').exists()
        assert (out/'source_specific'/'consciousness_systems_science_digest.md').exists()
    mf=Path('Makefile').read_text(encoding='utf-8')
    assert 'tol-digest:' in mf and 'validate-tol-digest:' in mf and 'tol-sync-obsidian:' in mf
    assert Path('docs/tol_knowledge_digest_pipeline.md').exists()
