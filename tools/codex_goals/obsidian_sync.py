import argparse,json
from pathlib import Path
def main():
 p=argparse.ArgumentParser();p.add_argument('--root',required=True);p.add_argument('--vault',required=True);p.add_argument('--out',required=True);a=p.parse_args();d=Path(a.vault)/'14_Codex_Goals';d.mkdir(parents=True,exist_ok=True)
 for n in ['Active_Goal','Goal_Policy','Contribution_Scorecard','Rendered_Codex_Prompt','Goal_Pack_Report']:(d/f'{n}.md').write_text(n)
 Path(a.out).write_text(json.dumps({'ok':True},indent=2))
if __name__=='__main__':main()