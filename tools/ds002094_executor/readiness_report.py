from __future__ import annotations
import argparse
from datetime import datetime, timezone
from pathlib import Path
from . import DEFAULT_OUT, read_json, write_json

def main()->None:
 ap=argparse.ArgumentParser(); ap.add_argument('--out', default=str(DEFAULT_OUT)); args=ap.parse_args(); out=Path(args.out)
 files=["dataset_registry.json","local_data_preflight.json","contract_requirements.json","reader_preflight.json","mne_adapter_plan.json","level_m_adapter_plan.json","level_t_adapter_plan.json","artifact_plan.json","real_execution_gate.json","post_execution_controls_interface.json"]
 docs={f:read_json(out/f) for f in files}
 rr={"generated_at":datetime.now(timezone.utc).isoformat(),"summary":"DS002094 dataset-specific executor template generated in offline/manual-only mode.","sections":docs,"remaining_blockers":["local_dataset_root_missing_or_unverified","human_reviewed_contract_missing","dataset_specific_reader_mapping_pending"],"next_action":"provide_local_DS002094_root"}
 write_json(out/'readiness_report.json',rr)
 (out/'ds002094_executor_report.md').write_text('# DS002094 Executor Report\n\nManual-only template generated; real execution remains blocked.\n',encoding='utf-8')
 write_json(out/'generation_manifest.json',{"generated_files":files+["readiness_report.json","ds002094_executor_report.md"],"status":"complete"})
if __name__=='__main__': main()
