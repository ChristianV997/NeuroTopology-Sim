from pathlib import Path
import tempfile
from tools.tol_digest.book_spine import main as book_main
from tools.tol_digest.research_roadmap import main as road_main
from tools.tol_digest.public_language_guide import main as guide_main
from tools.tol_digest.synthesis_validator import main as syn_val
from tools.tol_digest.obsidian_sync import main as sync_main

REQ=["book_insights.md","research_hypotheses.md","quarantine_report.md","doctrine_to_construct_map.json","observables_map.json","claim_tier_matrix.json","claim_inventory.json","tol_digest_validation.json"]

def seed(root: Path):
    root.mkdir(parents=True,exist_ok=True)
    for n in REQ: (root/n).write_text('ok',encoding='utf-8')

def test_p28_flow_and_rules():
    with tempfile.TemporaryDirectory() as d:
        r=Path(d)/'outputs'/'tol_digest'; seed(r)
        assert book_main(['--root',str(r),'--out',str(r)])==0
        assert 'high exit cost' in (r/'book_spine.md').read_text(encoding='utf-8').lower()
        assert 'stable flexibility' in (r/'book_spine.md').read_text(encoding='utf-8').lower()
        assert 'stability vs freedom' in (r/'book_spine.md').read_text(encoding='utf-8').lower()
        assert 'what the book does not claim' in (r/'book_spine.md').read_text(encoding='utf-8').lower()
        assert (r/'chapter_seed_bank.md').read_text(encoding='utf-8').lower().count('unsafe claims to avoid')>=12
        assert road_main(['--root',str(r),'--out',str(r)])==0
        rr=(r/'research_roadmap.md').read_text(encoding='utf-8').lower()
        assert 'candidate topology telemetry' in rr and 'falsifiers' in rr and 'null controls' in rr and 'ablations' in rr
        ob=(r/'tol_to_ds005620_observable_bridge.md').read_text(encoding='utf-8').lower()
        assert 'liberation → not directly measured' in ob and 'recovery latency' in ob and 'dwell time' in ob and 'qabs' in ob and 'fdress' in ob
        assert guide_main(['--root',str(r),'--out',str(r/'public_language_rewrite_guide.md')])==0
        g=(r/'public_language_rewrite_guide.md').read_text(encoding='utf-8').lower()
        assert 'soul is real' in g and 'qabs proves liberation' in g and 'trauma deletion' in g
        assert syn_val(['--root',str(r),'--json-out',str(r/'tol_synthesis_validation.json')])==0
        (r/'book_spine.md').write_text('soul is real',encoding='utf-8')
        assert syn_val(['--root',str(r),'--json-out',str(r/'x.json')])==1

def test_missing_inputs_not_available_and_obsidian_makefile_docs():
    with tempfile.TemporaryDirectory() as d:
        r=Path(d)/'o'; r.mkdir()
        assert book_main(['--root',str(r),'--out',str(r)])==1
        seed(r); book_main(['--root',str(r),'--out',str(r)]); road_main(['--root',str(r),'--out',str(r)]); guide_main(['--root',str(r),'--out',str(r/'public_language_rewrite_guide.md')])
        v=Path(d)/'obs'; assert sync_main(['--root',str(r),'--vault',str(v),'--out',str(r/'sync.json')])==0
        assert (v/'07_ToL'/'Book_Spine.md').exists()
    mf=Path('Makefile').read_text(encoding='utf-8')
    assert 'tol-book-spine:' in mf and 'tol-research-roadmap:' in mf and 'tol-public-language-guide:' in mf and 'tol-synthesis-cycle:' in mf
    assert Path('docs/tol_book_spine_research_roadmap.md').exists()
