import subprocess, json, tempfile, pathlib

def test_pipeline():
 d=pathlib.Path(tempfile.mkdtemp())
 q=d/'q.json'; subprocess.check_call(['python','-m','tools.literature_senses.query_packs','--out',str(q)])
 fr=d/'fr.json';n=d/'n.json';dd=d/'dd.json';sc=d/'sc.json';cl=d/'cl.json';ev=d/'ev.json';mp=d/'mp.json';fa=d/'fa.json';
 subprocess.check_call(['python','-m','tools.literature_senses.retrieval','--mode','fixture','--query-packs',str(q),'--out',str(fr)])
 assert all(p['fixture_generated'] and p['not_real_paper'] for p in json.loads(fr.read_text())['papers'])
 for cmd in [(['python','-m','tools.literature_senses.normalize','--input',str(fr),'--out',str(n)]),(['python','-m','tools.literature_senses.dedupe','--input',str(n),'--out',str(dd)]),(['python','-m','tools.literature_senses.scoring','--input',str(dd),'--query-packs',str(q),'--out',str(sc)]),(['python','-m','tools.literature_senses.claim_extractor','--input',str(sc),'--out',str(cl)]),(['python','-m','tools.literature_senses.evidence_tiering','--input',str(cl),'--out',str(ev)]),(['python','-m','tools.literature_senses.theory_mapper','--claims',str(cl),'--tiers',str(ev),'--out',str(mp)]),(['python','-m','tools.literature_senses.falsifier_detector','--claims',str(cl),'--mapping',str(mp),'--out',str(fa)])]: subprocess.check_call(cmd)
 assert 'limitations' in json.loads(cl.read_text())['claims'][0]
