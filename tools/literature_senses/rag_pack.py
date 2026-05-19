import argparse, json
from pathlib import Path
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--root',required=True);p.add_argument('--out',required=True);a=p.parse_args();o=Path(a.out);o.mkdir(parents=True,exist_ok=True)
 json.dump([{"id":"doc1","safe":True}],open(o/'rag_safe_documents.json','w'),indent=2)
 json.dump({"chunks":[{"source":"theory_integration_digest.md"}]},open(o/'rag_chunking_plan.json','w'),indent=2)
 json.dump({"queries":["Does this literature validate the TOE?","Can Qabs prove consciousness?"],"answers":["No, this fixture pipeline does not validate TOE.","No, Qabs cannot be used as proof claims."]},open(o/'rag_query_examples.json','w'),indent=2)
 json.dump({"forbidden":["proves consciousness","clinical treatment","Q proves"]},open(o/'rag_forbidden_answer_patterns.json','w'),indent=2)
 (o/'rag_public_answer_guidelines.md').write_text('No proof, diagnosis, treatment, or ontology promotion claims.\n',encoding='utf-8')
 (o/'rag_pack_report.md').write_text('RAG pack generated from fixture-only artifacts.\n',encoding='utf-8')
