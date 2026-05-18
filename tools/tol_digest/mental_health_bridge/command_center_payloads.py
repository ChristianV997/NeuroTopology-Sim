from __future__ import annotations
import argparse, json
from datetime import datetime, timezone
from pathlib import Path
from .generator import CENTRAL_THESIS, REQUIRED_OUTPUTS

def build(root: Path) -> dict:
    available={name: (root/name).exists() for name in REQUIRED_OUTPUTS}
    return {
        "ok": all(available.values()),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "bridge_status": "available" if all(available.values()) else "partial",
        "claim_scope": ["research_hypothesis", "wellness_support", "clinical_claim_blocked", "medical_device_claim_blocked"],
        "evidence_state": "requires_validation",
        "outputs_available": available,
        "core_thesis": CENTRAL_THESIS,
        "product_stage": "research_artifact_dashboard",
        "safety_level": "non_diagnostic_research_and_wellness_only",
        "guardrails": {
            "diagnosis_claims_allowed": False,
            "treatment_claims_allowed": False,
            "emergency_support_required_for_crisis": True,
            "q_qabs_fdress_candidate_telemetry_only": True,
            "clinician_replacement_allowed": False,
            "hidden_surveillance_allowed": False,
        },
        "next_actions": ["run validation protocols", "build dashboard", "review with domain experts"],
        "source_artifacts": [str(root/name) for name in REQUIRED_OUTPUTS],
        "limitations": ["No diagnosis", "No clinical efficacy claims", "No real-data execution", "No OpenAI calls", "No replacement for human/professional/emergency support"],
    }

def main(argv=None):
    p=argparse.ArgumentParser(); p.add_argument("--root", required=True); p.add_argument("--out", required=True); a=p.parse_args(argv)
    payload=build(Path(a.root)); out=Path(a.out); out.parent.mkdir(parents=True, exist_ok=True); out.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"); print(json.dumps(payload, indent=2)); return 0
if __name__ == "__main__": raise SystemExit(main())
