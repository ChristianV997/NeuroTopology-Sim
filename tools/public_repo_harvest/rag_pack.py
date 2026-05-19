import argparse, os
from .common import read_json, write_json
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--root',required=True);p.add_argument('--out',required=True);a=p.parse_args();os.makedirs(a.out,exist_ok=True)
 pats=read_json(os.path.join(a.root,'reusable_pattern_registry.json')).get('reusable_patterns',[])
 docs=[{"doc_id":p['pattern_id'],"title":p['description'],"source":"public_repo_harvest","summary":p['description'],"guardrails":["license-safe","pattern-only-when-blocked"]} for p in pats]
 write_json(os.path.join(a.out,'rag_safe_documents.json'),{"documents":docs})
 write_json(os.path.join(a.out,'rag_chunking_plan.json'),{"chunking_strategy":"pattern_record_per_chunk","max_chunk_chars":1200})
 write_json(os.path.join(a.out,'rag_query_examples.json'),{"examples":["Which patterns improve local_ops retry + lockfile behavior?","List pattern-only repos blocked for direct copy."]})
 write_json(os.path.join(a.out,'rag_forbidden_answer_patterns.json'),{"forbidden":["claims of clinical efficacy","claims TOE validated","live API assumptions"]})
 with open(os.path.join(a.out,'rag_public_answer_guidelines.md'),'w',encoding='utf-8') as f:f.write('# Public Repo Harvest RAG Guidelines\n- Use evidence from generated artifacts only.\n- Never claim copied code when not attributed.\n')
 with open(os.path.join(a.out,'rag_pack_report.md'),'w',encoding='utf-8') as f:f.write('# RAG Pack Report\nGenerated offline-safe documents for public repo harvest subsystem.\n')
