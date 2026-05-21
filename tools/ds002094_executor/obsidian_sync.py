from __future__ import annotations
import argparse
from pathlib import Path
from . import DEFAULT_OUT, read_json
MAP=[('DS002094_Dataset_Registry.md','dataset_registry.json'),('Local_Data_Preflight.md','local_data_preflight.json'),('Contract_Requirements.md','contract_requirements.json'),('Reader_Preflight.md','reader_preflight.json'),('MNE_Adapter_Plan.md','mne_adapter_plan.json'),('Level_M_Adapter_Plan.md','level_m_adapter_plan.json'),('Level_T_Adapter_Plan.md','level_t_adapter_plan.json'),('Artifact_Plan.md','artifact_plan.json'),('Real_Execution_Gate.md','real_execution_gate.json'),('Post_Execution_Controls_Interface.md','post_execution_controls_interface.json'),('Readiness_Report.md','readiness_report.json')]
def main():
 ap=argparse.ArgumentParser(); ap.add_argument('--root',default=str(DEFAULT_OUT)); ap.add_argument('--vault',default='obsidian'); args=ap.parse_args()
 root=Path(args.root); dst=Path(args.vault)/'16_DS002094_Executor'; dst.mkdir(parents=True,exist_ok=True)
 for md,j in MAP:
  data=read_json(root/j); (dst/md).write_text(f"# {md[:-3]}\n\n```json\n{data}\n```\n",encoding='utf-8')
if __name__=='__main__': main()
