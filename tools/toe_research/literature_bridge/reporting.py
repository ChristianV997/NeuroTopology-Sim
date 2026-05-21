import argparse
import json
from pathlib import Path


def _load_json(path: Path, fallback):
    if not path.exists():
        return fallback
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--root', required=True)
    p.add_argument('--out', required=True)
    a = p.parse_args()

    root = Path(a.root)
    priority = _load_json(root / 'toe_literature_priority_matrix.json', {})
    equations = _load_json(root / 'equation_candidate_registry.json', {})
    cosmology = _load_json(root / 'cosmology_constraint_matrix.json', {})
    gw = _load_json(root / 'gravitational_wave_constraint_matrix.json', {})
    adversarial = _load_json(root / 'consciousness_theory_adversarial_matrix.json', {})
    falsifiers = _load_json(root / 'toe_falsifier_watchlist.json', {})

    report = f"""# TOE Literature Bridge Report (P40)

## 1) P40 summary
P40 builds a constrained TOE research bridge that remains in engineering and hypothesis space. It expands traceable artifacts without advancing ontology or consciousness certainty statements.

## 2) Inputs consumed
- Priority matrix source keys: {list(priority.get('inputs', {}).keys())}
- Priority matrix availability: {priority.get('status', [])}
- Generated digest files from topology, active inference/allostasis, computational psychiatry, and bioelectric basal cognition tracks.

## 3) TOE primitive expansion
The primitive set is treated as candidate telemetry primitives for modeling only. Expansion remains documentation + registry based and is non-promotional.

## 4) Equation candidate registry
- Registry keys: {list(equations.keys()) if isinstance(equations, dict) else []}
- Candidate equations are retained as provisional mappings pending external evidence and explicit falsification pressure.

## 5) Topology telemetry upgrade
Topology telemetry is now represented as a dedicated digest and mapped to constrained observables, with no metric-to-ontology shortcuts.

## 6) Active inference/allostasis bridge
This bridge maps active inference and allostasis concepts into candidate state-update language for future simulation tasks under strict claim boundaries.

## 7) Computational psychiatry bridge
Computational psychiatry linkage is captured as hypothesis scaffolding for symptom-model interfaces only; no diagnosis or intervention statements are emitted.

## 8) Bioelectric/basal cognition bridge
Bioelectric and basal cognition notes remain at comparative literature-bridge level with guarded interpretation boundaries.

## 9) Cosmology constraints
- Constraint keys: {list(cosmology.keys()) if isinstance(cosmology, dict) else []}
- Cosmology constraints are tracked as external boundary conditions.

## 10) Gravitational-wave constraints
- Constraint keys: {list(gw.keys()) if isinstance(gw, dict) else []}
- Gravitational-wave constraints are integrated as compatibility checks for candidate equation behavior.

## 11) Consciousness adversarial matrix
- Matrix keys: {list(adversarial.keys()) if isinstance(adversarial, dict) else []}
- Adversarial cases are used to stress-test overreach and unsupported language.

## 12) Falsifier registry
- Registry keys: {list(falsifiers.keys()) if isinstance(falsifiers, dict) else []}
- Falsifiers enumerate failure modes that should block confidence escalation.

## 13) Guardrails preserved
- No real data execution
- No live API calls
- No API keys
- No clinical-claim framing
- No ontology promotion
- No proof framing for TOE/consciousness

## 14) What remains quarantined
Any claim language that implies proof, finality, solved ontology, or direct metaphysical identity mappings remains blocked and quarantined.

## 15) Next recommended PR
P40.2 should add richer cross-artifact traceability (source-to-claim maps + rationale annotations) and expand validator unit tests for newly generated report sections.
"""
    Path(a.out).write_text(report, encoding="utf-8")


if __name__ == '__main__':
    main()
