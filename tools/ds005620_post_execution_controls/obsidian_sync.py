from __future__ import annotations
import argparse
from pathlib import Path
MAP={"Post_Execution_Control_Runbook.md":"post_execution_control_runbook.md","Execution_Artifact_Audit.md":"execution_artifact_audit.json","Null_Controls_Plan.md":"null_controls_plan.json","Ablation_Plan.md":"ablation_plan.json","Leakage_Report_Template.md":"leakage_report_template.json","Artifact_Report_Template.md":"artifact_report_template.json","Statistical_Report_Template.md":"statistical_report_template.json","Empirical_Claim_Gate.md":"empirical_claim_gate.json","Publication_Readiness_Report.md":"publication_readiness_report.md"}
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--root',default='outputs/btc_icft/ds005620_post_execution_controls');ap.add_argument('--obsidian-root',default='obsidian/15_DS005620_Post_Execution_Controls');a=ap.parse_args();src=Path(a.root);dst=Path(a.obsidian_root);dst.mkdir(parents=True,exist_ok=True)
 for d,s in MAP.items():
  p=src/s
  content=p.read_text(encoding='utf-8') if p.exists() else f'# Missing source\n- {s}\n'
  (dst/d).write_text(content,encoding='utf-8')
if __name__=='__main__': main()
