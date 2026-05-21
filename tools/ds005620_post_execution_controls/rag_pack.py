from __future__ import annotations
import argparse
from pathlib import Path
from . import write_json

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--root',default='outputs/btc_icft/ds005620_post_execution_controls/rag_pack');a=ap.parse_args();root=Path(a.root)
 write_json(root/'rag_safe_documents.json',{'documents':['post_execution_control_runbook.md','publication_readiness_report.md']})
 write_json(root/'rag_chunking_plan.json',{'chunk_strategy':'section_based_markdown'})
 write_json(root/'rag_query_examples.json',{'queries':['What controls are required after DS005620 real execution?','Are empirical claims allowed yet?','What null controls are required?','What ablations are required?','What blocks publication readiness?','Does a mock run count as empirical evidence?','Can Q/Qabs/fdress prove consciousness?']})
 write_json(root/'rag_forbidden_answer_patterns.json',{'forbidden':['mock run counts as empirical evidence','empirical claims allowed without controls','Q/Qabs/fdress prove consciousness']})
 (root/'rag_public_answer_guidelines.md').write_text('- Mock runs do not count as empirical evidence.\n- Empirical claims remain blocked until real run, controls, and human review are complete.\n- Q/Qabs/fdress are candidate telemetry only.\n',encoding='utf-8')
 (root/'rag_pack_report.md').write_text('# RAG Pack Report\nGenerated safe-answer artifacts for DS005620 post-execution controls.\n',encoding='utf-8')
if __name__=='__main__': main()
