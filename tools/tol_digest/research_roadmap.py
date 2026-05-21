from __future__ import annotations
import argparse
from pathlib import Path

REQ=["book_insights.md","research_hypotheses.md","quarantine_report.md","doctrine_to_construct_map.json","observables_map.json","claim_tier_matrix.json","claim_inventory.json","tol_digest_validation.json"]

def main(argv=None):
    ap=argparse.ArgumentParser(); ap.add_argument('--root',required=True); ap.add_argument('--out',required=True); a=ap.parse_args(argv)
    root,out=Path(a.root),Path(a.out); out.mkdir(parents=True,exist_ok=True)
    missing=[x for x in REQ if not (root/x).exists()]
    roadmap='''# ToL Research Roadmap

## 1. ToL Research Roadmap
## 2. Research posture
Hypothesis-generating only.
## 3. Test state transitions, not metaphysical endpoints
## 4. Dynamics layer
## 5. Topology layer
## 6. Perturbation layer
## 7. Anesthesia wedge
## 8. Meditation contrast
## 9. DS005620 bridge
## 10. Multi-dataset bridge
## 11. Null controls
## 12. Ablations
## 13. Leakage/artifact reports
## 14. Falsifiers
## 15. Claim-promotion boundary
Q, Qabs, fdress are candidate topology telemetry.
They are not proof of consciousness, soul, liberation, or nibbāna.
Real empirical claims require real execution, controls, ablations, leakage reports, artifact reports, and human-reviewed label contracts.
## 16. Next empirical milestones
Pre-registered control plans and audited artifacts.
'''
    (out/'research_roadmap.md').write_text(roadmap,encoding='utf-8')
    bridge='''# ToL to DS005620 Observable Bridge

- high exit cost → recovery latency, dwell time, transition resistance
- rigidity → hysteresis, attractor depth, delayed recovery
- fragmentation → Qabs, fdress, phase singularity burden (candidate telemetry only)
- stability → lower volatility, lower entropy/complexity under controlled contexts
- perturbational flexibility → PCI/PCIst-style response where available
- ownership/clinging proxy → not directly measured; requires cautious behavioral/task proxy
- liberation → not directly measured; only indirect candidate proxies
'''
    (out/'tol_to_ds005620_observable_bridge.md').write_text(bridge,encoding='utf-8')
    return 1 if missing else 0
if __name__=='__main__': raise SystemExit(main())
