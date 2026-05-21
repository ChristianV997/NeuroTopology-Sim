from __future__ import annotations
import argparse
from pathlib import Path

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--root',default='outputs/btc_icft/ds005620_post_execution_controls');a=ap.parse_args();root=Path(a.root)
 txt='''# DS005620 Post-Execution Control Runbook\n\n- Run only after manual DS005620 real execution is completed.\n- Verify expected benchmark artifacts before controls.\n- Execute null controls and ablations manually with human oversight.\n- Complete leakage, artifact, and statistical checklists.\n- Human review gate must confirm claim language boundaries.\n- Do not claim proof, ontology validation, or clinical efficacy.\n- If any check fails, keep empirical claims blocked and remediate evidence gaps.\n'''
 (root/'post_execution_control_runbook.md').write_text(txt,encoding='utf-8')
if __name__=='__main__': main()
