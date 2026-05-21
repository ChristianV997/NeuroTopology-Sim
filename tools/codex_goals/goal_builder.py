import argparse, json
from pathlib import Path
from datetime import datetime, timezone

PRESET = {"goal_id":"P40","name":"P40 — TOE Literature Bridge + Constraint/Falsifier Matrix","mode":"Comprehensive high-contribution vertical subsystem run.","contribution_target":">4,000 useful lines if justified.","required_surfaces":["package","schema","generator","validator","outputs","Obsidian sync","command-center payloads","RAG pack","docs","tests","Makefile cycle","PR body"],"required_outputs":["active_goal.json","active_goal.md"],"required_make_targets":["codex-goal","validate-codex-goal","codex-goal-cycle"],"validation_commands":["python -m governance.validate"],"guardrails":["no real data","no live APIs","no API keys","no OpenAI calls","no clinical claims","no ontology promotion","no proof claims","no Q/Qabs/fdress proof claims","no TOE validation claim"],"forbidden_patterns":["ignore guardrails","copy everything","final theory validated"],"success_criteria":["validators pass"],"pr_body_sections":["Summary","Tests run"]}

def main():
    p=argparse.ArgumentParser(); p.add_argument('--preset',default='toe_research'); p.add_argument('--out',required=True); a=p.parse_args(); out=Path(a.out); out.mkdir(parents=True,exist_ok=True)
    (out/'active_goal.json').write_text(json.dumps(PRESET,indent=2))
    md = "/goal toe_research\n\nMODE:\n" + PRESET['mode'] + "\n\nCONTRIBUTION TARGET:\n" + PRESET['contribution_target'] + "\n\nREQUIRED SURFACES:\n" + "\n".join(PRESET['required_surfaces']) + "\n\nGUARDRAILS:\n" + "\n".join(PRESET['guardrails']) + "\n"
    (out/'active_goal.md').write_text(md)
    (out/'generation_manifest.json').write_text(json.dumps({'generated_at':datetime.now(timezone.utc).isoformat(),'preset':a.preset},indent=2))
if __name__=='__main__': main()
