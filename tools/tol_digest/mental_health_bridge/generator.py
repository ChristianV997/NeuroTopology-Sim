from __future__ import annotations
import argparse, json
from datetime import datetime, timezone
from pathlib import Path
from .schema import DisorderDynamicsMapping, MLFeatureGroup, ObservableMatrixRow, to_dict

REQUIRED_OUTPUTS = [
    "mental_flexibility_master_model.md", "disorder_to_dynamics_matrix.json", "ml_feature_schema.json",
    "intervention_safety_ladder.md", "clinical_translation_map.md", "body_brain_mind_observable_matrix.json",
    "funding_and_product_opportunity_map.md", "validation_protocols.md", "mental_health_bridge_report.md",
]
INPUTS = [
    "book_spine.md", "research_roadmap.md", "tol_to_ds005620_observable_bridge.md",
    "public_language_rewrite_guide.md", "quarantine_report.md", "doctrine_to_construct_map.json",
    "observables_map.json", "claim_tier_matrix.json", "tol_synthesis_validation.json",
    "source_specific/uploaded_source_claim_risk_matrix.json",
]
CENTRAL_THESIS = "Mental health improves when a living system becomes more viable, flexible, embodied, socially connected, and less trapped by rigid self-models."
MODEL = "Suffering can be modeled as high exit-cost rigidity in an embodied meaning-making system. Wellbeing can be modeled as increased adaptive flexibility, lower recovery latency, wider perceived affordances, better body-brain regulation, and reduced compulsive self-binding."
SAFE = "This is a research and wellness architecture only: no diagnosis, no intervention efficacy claim, no cure claim, no clinician replacement, and no emergency-care bypass."

def _read_inputs(root: Path, strict: bool) -> dict:
    used, missing = [], []
    for name in INPUTS:
        p = root / name
        if p.exists():
            used.append({"path": name, "status": "available"})
        else:
            missing.append(name); used.append({"path": name, "status": "not_available"})
    if strict and missing:
        raise FileNotFoundError("missing inputs: " + ", ".join(missing))
    return {"inputs": used, "missing": missing}

def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True); path.write_text(text.strip()+"\n", encoding="utf-8")

def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True); path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")

def master_model() -> str:
    return f"""
# Mental Flexibility Master Model

## 1. Purpose
P34 creates a claim-governed mental-flexibility and systems-medicine bridge that maps ToL constructs to mental-health dynamics, ML features, body-brain-mind observables, safety tiers, clinical translation boundaries, and validation protocols without making diagnostic or intervention efficacy claims.

## 2. Research posture
Current repo outputs are research artifacts. They support research, education, and non-diagnostic wellness exploration only.

## 3. Central applied thesis
{CENTRAL_THESIS}

## 4. Mental flexibility definition
Mental flexibility is the measurable capacity of an embodied person-in-context to notice state constraints, lower exit cost from rigid loops, widen perceived options, recover after perturbation, and choose values-consistent actions.

Required model: {MODEL}

## 5. ToL construct mapping
ToL constructs are represented as candidate mappings: self-model binding, grasping loops, perceived exits, affordance fields, topology telemetry as candidate signals only, and compassion/social connectedness as context-sensitive stabilizers.

## 6. Body-brain-mind framing
Body signals, brain telemetry, mind reports, behavior traces, and environment constraints are treated as partial observables. No single layer is sufficient for diagnosis or clinical action.

## 7. Systems-medicine framing
The bridge frames distress as candidate dynamical rigidity, allostatic load, recovery latency, and context-constrained affordances. It separates research mode, wellness mode, clinician-support candidate mode, and regulated medical-device candidate mode.

## 8. Machine-learning role
ML may organize consented features, test hypotheses, identify drift, and support dashboards after validation. It must not infer labels, fabricate targets, infer protected traits, run hidden surveillance, or operate clinically without locked-model evaluation and human oversight.

## 9. Mental-health relevance
The bridge treats mental flexibility as a transdiagnostic research target: rumination, avoidance, compulsive loops, threat overprecision, low exploration, and slow recovery latency may be studied as candidate dynamics across domains.

## 10. What this model does not claim
It does not diagnose, treat, cure, prove clinical efficacy, replace clinicians, detect enlightenment, prove consciousness, prove suffering, or prove liberation. Q, Qabs, and fdress are candidate telemetry only.

## 11. Guardrails
{SAFE} If self-harm, psychosis, mania, severe dissociation, medical emergency, abuse, or acute crisis markers appear, the system must recommend human/professional/emergency support and must not continue deep intervention.

## 12. Next research milestones
Define consent protocols; collect longitudinal non-clinical data; validate construct measures; test falsifiers; evaluate bias and privacy risk; design clinician-reviewed escalation rules; and keep claims blocked until proper validation and review.
"""

def disorder_matrix() -> dict:
    base = {
        "depression": ["negative attractor dwell", "reduced affordance field", "low exploration", "slow recovery latency", "rumination loop"],
        "anxiety": ["threat precision inflation", "uncertainty intolerance", "autonomic coupling", "future-state overcontrol"],
        "trauma/PTSD": ["reactivation attractor", "interoceptive threat lock", "high recovery latency", "avoidance loop", "safety cue failure"],
        "addiction": ["reward-policy lock", "cue-triggered re-entry", "craving loop", "compulsive state-grasping"],
        "OCD": ["uncertainty-control loop", "ritualized precision", "intolerance of incompletion", "compulsive checking/neutralization"],
        "rumination": ["self-model recurrence", "low novelty loop", "high dwell time", "affective replay"],
        "burnout": ["allostatic overload", "reward collapse", "low regulatory reserve", "reduced recovery capacity"],
        "dissociation": ["boundary instability", "interoceptive disconnection", "defensive decoupling", "safety required"],
        "psychosis-risk": ["salience dysregulation", "meaning overbinding", "boundary instability", "clinician escalation required"],
    }
    out = {}
    for k, vals in base.items():
        out[k] = to_dict(DisorderDynamicsMapping(
            clinical_domain=k,
            dynamics_hypothesis=["candidate mapping: "+v for v in vals],
            ToL_constructs=["self-model binding", "exit-cost rigidity", "affordance field", "state dwell", "recovery latency"],
            candidate_observables=["self report", "sleep", "HRV", "language rigidity", "behavioral narrowing"],
            candidate_ML_features=["perceived exits", "recovery latency", "dwell time", "routine narrowing", "autonomic variability"],
            safe_interventions_category=["research journaling", "wellness stabilization", "clinician support after validation"],
            contraindications=["acute crisis", "unsupervised exposure", "intensive contemplative escalation during instability"],
            safety_escalation_triggers=["self-harm markers", "psychosis markers", "mania markers", "severe dissociation", "medical emergency", "abuse or acute crisis"],
        ))
    return out

def ml_schema() -> list[dict]:
    groups = {
        "self_report_features": ["mood", "anxiety", "perceived exits", "rumination intensity", "craving intensity", "sleep quality", "energy", "safety rating", "social connection"],
        "physiology_features": ["HRV", "heart_rate", "GSR/EDA", "respiration_rate", "breath_variability", "sleep_duration", "sleep_regularities", "activity_level"],
        "neuro_features": ["EEG bandpower", "phase synchrony", "LZC", "entropy", "Q", "Qabs", "fdress", "phase_singularity_count", "PCI/PCIst if available"],
        "behavior_features": ["task switching", "routine narrowing", "avoidance markers", "exploration diversity", "app interaction regularity", "typing/cursor/touch rhythm if ethically collected"],
        "language_features": ["self-referential density", "hopelessness markers", "rigidity terms", "perceived-exit language", "craving language", "threat language", "social isolation language"],
        "context_features": ["stressor load", "social support", "environment safety", "work/financial load", "sleep schedule disruption"],
    }
    rows=[]
    for g, names in groups.items():
        for n in names:
            rows.append(to_dict(MLFeatureGroup(n,g,f"Candidate {n} feature for validated research modeling.","consented self-report/device/task/log only","medium" if g not in {"language_features","behavior_features"} else "high","high","research_or_wellness_non_diagnostic","hidden surveillance, protected-trait inference, diagnosis, clinical use without validation","mark missing and model missingness explicitly","dataset and access bias",True)))
    return rows

def ladder() -> str:
    return """
# Intervention Safety Ladder

## Level 0 — Research / journaling
No clinical claims; self-reflection only.

## Level 1 — Wellness support
Sleep, breathing, grounding, journaling, and habit support; non-diagnostic.

## Level 2 — Coaching support
Values, routines, mindfulness, and social support; no trauma processing and no diagnosis.

## Level 3 — Clinician-facing decision support candidate
Requires validation; clinician remains responsible; audit trails required.

## Level 4 — Digital therapeutic candidate
Requires clinical trials and regulated claims only after evidence.

## Level 5 — Medical device / SaMD candidate
Requires regulatory pathway, quality system, risk management, and post-market monitoring.

## Emergency boundary
If self-harm, psychosis, mania, severe dissociation, medical emergency, abuse, or acute crisis markers appear, the system must recommend human/professional/emergency support and must not continue deep intervention.

## Forbidden intervention patterns
Trauma deletion; instant awakening; mechanical enlightenment; unsupervised exposure; intense meditation escalation during instability; replacing therapy; replacing psychiatry; medication advice.
"""

def clinical_map() -> str:
    sections=["Research mode","Wellness mode","Coaching-support mode","Clinician-support candidate mode","Digital therapeutic candidate mode","Medical device / SaMD candidate mode","Data requirements","Validation requirements","Risk controls","Human oversight","Privacy/security","Equity/bias","Regulatory boundary","What remains manual"]
    body="# Clinical Translation Map\n\nCurrent repo outputs are research artifacts. No product should claim diagnosis or intervention efficacy without trials/regulatory review. ML models must be locked/evaluated before clinical use. Adaptive model updates require change-control strategy. Clinical deployment requires human oversight and adverse-event reporting.\n"
    for s in sections:
        body += f"\n## {s}\nMaintain explicit research/wellness/clinical/regulatory separation, documented consent, validation evidence, review gates, and blocked medical claims.\n"
    return body

def observable_matrix() -> list[dict]:
    layers={
      "body":["HRV","heart rate","GSR/EDA","respiration","sleep","activity","inflammation/metabolic proxies if available","pain/fatigue self-report"],
      "brain":["EEG bandpower","phase fields","Q/Qabs/fdress","LZC","entropy","PCI/PCIst if available","phase singularities","DMN/salience/executive proxies if available"],
      "mind":["self-report","perceived exits","rumination","craving","emotional reactivity","identity rigidity","meaning collapse","mindfulness/meta-awareness"],
      "behavior":["avoidance","exploration","task switching","social engagement","routine narrowing","relapse/re-entry patterns"],
      "environment":["social support","stressor load","safety","affordance field","economic/logistical constraints"],
    }
    rows=[]
    for layer, obs in layers.items():
        for o in obs:
            rows.append(to_dict(ObservableMatrixRow(layer,o,["mental flexibility","recovery latency","exit-cost rigidity"],"consented measurement or self-report","low to medium","medium","candidate observable; reliability requires study","missingness may be meaningful and must be modeled","requires_validation","research_hypothesis")))
    return rows

def funding_map() -> str:
    sections=["Strategic opportunity","Why mental flexibility is fundable","Research grants","Digital mental health","Wearables and biomarkers","Clinician-support tools","Retreat / contemplative science","Neurofeedback and biofeedback","Preventive health","AI/RAG research assistant","Medical-device path, long term","Business risks","Regulatory risks","Ethical risks","MVP sequence"]
    body="# Funding and Product Opportunity Map\n"
    for s in sections:
        body += f"\n## {s}\nResearch-first opportunity with claim governance, consent, privacy, bias controls, and no medical claims without validation.\n"
    body += "\n1. Research artifact dashboard\n2. Wellness/non-diagnostic mental-flexibility journal\n3. Multimodal personal dashboard\n4. Clinician-support report prototype\n5. Validated research study\n6. Digital therapeutic candidate\n7. Medical-device candidate\n"
    return body

def protocols() -> str:
    hyps=["Exit-cost proxies predict subjective distress and reduced perceived options.","Recovery latency predicts worse wellbeing more robustly than single mood snapshots.","Multimodal flexibility features predict relapse/re-entry risk.","Topology telemetry adds residual value only if it improves prediction beyond M-only and standard physiology/language features.","Mindfulness/stabilization practice improves recovery latency and reduces state dwell time in safe non-clinical contexts."]
    fals=["features do not predict longitudinal distress/wellbeing","recovery latency adds no value over baseline mood/sleep","topology metrics add no residual predictive value","model performance fails under distribution shift","safety/escalation classifier misses critical events","intervention suggestions worsen outcomes or dependency"]
    sections=["Validation posture","Construct validity","Predictive validity","Safety validity","Longitudinal validity","Bias/fairness evaluation","Privacy evaluation","Clinical escalation evaluation","Human factors testing","Model drift monitoring","Locked model vs adaptive model","External validation","Failure modes","Falsifiers"]
    body="# Validation Protocols\n"
    for s in sections:
        body += f"\n## {s}\nPre-register metrics, compare against baselines, monitor harms, and block clinical claims until evidence and review exist.\n"
    body += "\n## Research hypotheses\n" + "\n".join(f"- {h}" for h in hyps)
    body += "\n\n## Falsifiers\n" + "\n".join(f"- {f}" for f in fals)
    return body

def report(meta: dict, out: Path) -> str:
    return f"""
# P34 Mental Flexibility & Systems Medicine Bridge

## Inputs used
{json.dumps(meta['inputs'], indent=2)}

## Outputs written
{json.dumps(REQUIRED_OUTPUTS, indent=2)}

## Current claim scope
Research hypothesis, education, and wellness_non_diagnostic only. Guardrails block diagnosis, clinical efficacy, cure, clinician replacement, and ontology-promotion claims.

## Main theory
{CENTRAL_THESIS} {MODEL}

## ML bridge
Consented multimodal features are schemas for validation, not deployed clinical inference.

## Clinical translation
Research, wellness, coaching, clinician-support candidate, digital-therapeutic candidate, and SaMD candidate modes are separated.

## Product opportunity
The safe MVP starts with research dashboards and non-diagnostic journals before any validated study or regulated pathway.

## Safety boundary
Guardrails require professional/emergency support for crisis markers and prohibit deep intervention in acute-risk states.

## Next recommended PR
Build a static dashboard over these artifacts and add richer claim-tier provenance.
"""

def generate(root: Path, out: Path, strict: bool=False) -> dict:
    meta=_read_inputs(root, strict); out.mkdir(parents=True, exist_ok=True)
    _write(out/"mental_flexibility_master_model.md", master_model())
    _write_json(out/"disorder_to_dynamics_matrix.json", disorder_matrix())
    _write_json(out/"ml_feature_schema.json", ml_schema())
    _write(out/"intervention_safety_ladder.md", ladder())
    _write(out/"clinical_translation_map.md", clinical_map())
    _write_json(out/"body_brain_mind_observable_matrix.json", observable_matrix())
    _write(out/"funding_and_product_opportunity_map.md", funding_map())
    _write(out/"validation_protocols.md", protocols())
    _write(out/"mental_health_bridge_report.md", report(meta,out))
    manifest={"ok": True, "generated_at": datetime.now(timezone.utc).isoformat(), "input_status": meta, "outputs": REQUIRED_OUTPUTS, "not_available_inputs": meta["missing"]}
    _write_json(out/"generation_manifest.json", manifest)
    return manifest

def main(argv=None):
    p=argparse.ArgumentParser(); p.add_argument("--root", required=True); p.add_argument("--out", required=True); p.add_argument("--strict", action="store_true"); a=p.parse_args(argv)
    try:
        res=generate(Path(a.root), Path(a.out), a.strict); print(json.dumps(res, indent=2)); return 0
    except FileNotFoundError as e:
        print(json.dumps({"ok": False, "error": str(e)}, indent=2)); return 1
if __name__ == "__main__": raise SystemExit(main())
