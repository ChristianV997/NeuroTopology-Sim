from __future__ import annotations
import argparse
from pathlib import Path
from . import DEFAULT_OUT, write_json

def main():
 ap=argparse.ArgumentParser(); ap.add_argument('--root',default=str(DEFAULT_OUT)); args=ap.parse_args(); out=Path(args.root)/'rag_pack'; out.mkdir(parents=True,exist_ok=True)
 write_json(out/'rag_safe_documents.json',{"documents":["readiness_report.json","contract_requirements.json","real_execution_gate.json"]})
 write_json(out/'rag_chunking_plan.json',{"strategy":"sectional_json_and_markdown","max_chunk_chars":1200})
 write_json(out/'rag_query_examples.json',{"queries":["What is DS002094’s role?","Is DS002094 ready for real execution?","What files are missing?","Can the system infer labels?","Can DS002094 run MNE automatically?","What controls are required after execution?","Does this validate consciousness?"]})
 write_json(out/'rag_forbidden_answer_patterns.json',{"forbidden":["claims real execution ready by default","infers labels","automatic MNE execution","consciousness proof","ontology promotion"]})
 (out/'rag_public_answer_guidelines.md').write_text('Always answer that DS002094 is manual-only by default, no label inference, no automatic MNE, and no consciousness/ontology claims.\n',encoding='utf-8')
 (out/'rag_pack_report.md').write_text('# RAG Pack Report\n\nSafe-answer pack generated for DS002094 template.\n',encoding='utf-8')
if __name__=='__main__': main()
