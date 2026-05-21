import argparse,json
from pathlib import Path
def main():
 p=argparse.ArgumentParser();p.add_argument('--root',required=True);p.add_argument('--out',required=True);a=p.parse_args();o=Path(a.out);o.mkdir(parents=True,exist_ok=True)
 (o/'rag_safe_documents.json').write_text(json.dumps({'safe':['bridge']},indent=2))
 (o/'rag_chunking_plan.json').write_text(json.dumps({'chunks':[]},indent=2))
 (o/'rag_query_examples.json').write_text(json.dumps({'examples':['Does this validate the TOE? No.','Can Qabs prove consciousness? No.']},indent=2))
 (o/'rag_forbidden_answer_patterns.json').write_text(json.dumps(['TOE validated','final theory','consciousness solved','Q proves','Qabs proves','clinical treatment','diagnosis','soul proof','afterlife proof','ontology promotion'],indent=2))
 (o/'rag_public_answer_guidelines.md').write_text('Do not claim validation.')
 (o/'rag_pack_report.md').write_text('RAG pack report')
if __name__=='__main__':main()