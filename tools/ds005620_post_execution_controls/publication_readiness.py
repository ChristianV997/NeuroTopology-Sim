from __future__ import annotations
import argparse
from pathlib import Path
from . import read_json

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--root',default='outputs/btc_icft/ds005620_post_execution_controls');a=ap.parse_args();root=Path(a.root)
 audit=read_json(root/'execution_artifact_audit.json'); gate=read_json(root/'empirical_claim_gate.json')
 md='''# DS005620 Publication Readiness Report\n\n## 1. Summary\n- publication_ready: false\n- reason: real execution and controls not yet completed\n\n## 2. Execution artifact audit\n- real_execution_observed: {real}\n\n## 3. Null controls status\n- planned_only\n\n## 4. Ablations status\n- planned_only\n\n## 5. Leakage checks status\n- not_run_real_data_pending\n\n## 6. Artifact checks status\n- not_run_real_data_pending\n\n## 7. Statistical checks status\n- not_run_real_data_pending\n\n## 8. Empirical claim gate\n- empirical_claims_permitted: {claims}\n\n## 9. Human review requirements\n- Human peer review confirmation required.\n\n## 10. Allowed language\n- Engineering/runtime readiness language only.\n\n## 11. Blocked language\n- Proof, ontology promotion, clinical efficacy language.\n\n## 12. What remains manual\n- Real execution, controls, peer review.\n\n## 13. Next commands\n- make ds005620-post-execution-controls-cycle\n\n## 14. Publication lane recommendation\n- Hold publication-grade empirical claims pending controls.\n'''.format(real=audit.get('real_execution_observed',False),claims=gate.get('empirical_claims_permitted',False))
 (root/'publication_readiness_report.md').write_text(md,encoding='utf-8')
if __name__=='__main__': main()
