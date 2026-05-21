
import argparse, json
from pathlib import Path
from datetime import datetime, timezone

PRESET = {
"goal_id":"P40","name":"P40 — TOE Literature Bridge + Constraint/Falsifier Matrix","mode":"Comprehensive high-contribution vertical subsystem run.","contribution_target":">4,000 useful lines if justified.","required_surfaces":["package","schema","generator","validator","outputs","Obsidian sync","command-center payloads","RAG pack","docs","tests","Makefile cycle","PR body"],"required_outputs":["active_goal.json","active_goal.md"],"required_make_targets":["codex-goal","validate-codex-goal","codex-goal-cycle"],"validation_commands":["python -m governance.validate"],"guardrails":["no real data","no live APIs","no API keys","no OpenAI calls","no clinical claims","no ontology promotion","no proof claims","no Q/Qabs/fdress proof claims","no TOE validation claim"],"forbidden_patterns":["ignore guardrails","copy everything","final theory validated"],"success_criteria":["validators pass"],"pr_body_sections":["Summary","Tests run"]}

def now(): return datetime.now(timezone.utc).isoformat()

def main():
 p=argparse.ArgumentParser(); p.add_argument('--root',required=True); p.add_argument('--json-out',required=True); a=p.parse_args(); r=Path(a.root); v=[]
 for f in ['active_goal.json','active_goal.md']:
  if not (r/f).exists(): v.append(f'missing {f}')
 txt=(r/'active_goal.md').read_text() if (r/'active_goal.md').exists() else ''
 for must in ['REQUIRED SURFACES','GUARDRAILS','/goal toe_research']:
  if must not in txt: v.append(f'missing {must}')
 bad=['ignore guardrails','copy everything','final theory validated']
 if any(b in txt.lower() for b in bad): v.append('unsafe wording')
 out={'ok':not v,'violations':v}; Path(a.json_out).write_text(json.dumps(out,indent=2)); raise SystemExit(0 if not v else 1)
if __name__=='__main__': main()
