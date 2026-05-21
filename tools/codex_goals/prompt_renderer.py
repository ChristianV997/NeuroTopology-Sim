import argparse, json
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument('--root',required=True); p.add_argument('--out',required=True); a=p.parse_args();
    _=json.loads((Path(a.root)/'active_goal.json').read_text())
    sections=['Mission','Context','Primary objective','Required package','Required outputs','Obsidian mirror','Command-center payloads','RAG pack','Makefile targets','Tests','Validation commands','Guardrails','PR branch/title/body','Success criteria']
    Path(a.out).write_text('\n'.join([f'# {s}' for s in sections]))
if __name__=='__main__': main()
