import argparse
from pathlib import Path

def main():
    p=argparse.ArgumentParser();p.add_argument('--root',required=True);p.add_argument('--out',required=True);a=p.parse_args()
    sections=['Codex Goal Pack Summary','Why this exists','Available goal presets','Active goal','Required surfaces','Contribution target','Scorecard','Guardrails','How to use','Next recommended Codex run']
    Path(a.out).write_text('\n'.join(f'{i+1}. {s}' for i,s in enumerate(sections)))
if __name__=='__main__':main()
