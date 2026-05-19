import subprocess, json, tempfile, pathlib

def test_registries_and_plan():
 d=pathlib.Path(tempfile.mkdtemp())
 s=d/'s.json';q=d/'q.json';r=d/'r.json'
 subprocess.check_call(['python','-m','tools.literature_senses.source_registry','--out',str(s)])
 subprocess.check_call(['python','-m','tools.literature_senses.query_packs','--out',str(q)])
 subprocess.check_call(['python','-m','tools.literature_senses.retrieval_plan','--sources',str(s),'--query-packs',str(q),'--out',str(r)])
 sj=json.loads(s.read_text()); assert {x['source_id'] for x in sj['sources']}>= {'arxiv','pubmed','openalex','semantic_scholar','local_fixture','local_file'}
 assert all(x.get('live_status')!='enabled_by_default' for x in sj['sources'])
 assert len(json.loads(q.read_text())['query_packs'])>=20
 assert all(x['blocked_without_confirm_network'] for x in json.loads(r.read_text())['retrieval_plan'])
