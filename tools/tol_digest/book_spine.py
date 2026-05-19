from __future__ import annotations
import argparse, json
from pathlib import Path

CORE_THESIS=("Suffering can be modeled as the cost of being unable to exit a state. "
"Liberation can be modeled as stable flexibility: the capacity to participate, release, and reconfigure without compulsive ownership.")
INPUTS=["book_insights.md","research_hypotheses.md","quarantine_report.md","doctrine_to_construct_map.json","observables_map.json","claim_tier_matrix.json","claim_inventory.json","tol_digest_validation.json"]
OPTIONAL=["tol_digest_strict_validation.json","tol_digest_safety_report.json","tol_digest_safety_report.md","tol_digest_strict_validation.md"]
SEEDS=[
"The Mind as a System of Exits","Dukkha as High Exit Cost","Craving as State-Grasping","Clinging as Boundary Locking",
"No-Self as No Fixed Attractor","Impermanence and Metastability","Stability Is Not Freedom","Joy and Calm Before Deconstruction",
"Jhāna as Low-Noise Stability","Awakening as Reduced Ownership","The Science of Transitions","What We Can and Cannot Claim"
]

def _read(root: Path, name: str) -> str:
    p=root/name
    return p.read_text(encoding='utf-8') if p.exists() else ''

def main(argv=None):
    ap=argparse.ArgumentParser(); ap.add_argument('--root',required=True); ap.add_argument('--out',required=True); ap.add_argument('--strict',action='store_true'); a=ap.parse_args(argv)
    root,out=Path(a.root),Path(a.out); out.mkdir(parents=True,exist_ok=True)
    missing=[x for x in INPUTS if not (root/x).exists()]
    strict_available=any((root/x).exists() for x in OPTIONAL)
    strict_status='available' if strict_available else 'not_available'
    if a.strict and not strict_available: missing.append('strict_validation_outputs')

    book=f"""# ToL Book Spine

## 1. ToL Book Spine
P28 synthesis from validated digest outputs only.

## 2. Core thesis
{CORE_THESIS}

## 3. Reader promise
A practical and scientifically cautious map for reducing compulsive rigidity.

## 4. The central metaphor: suffering as high exit cost
Dukkha is framed as high transition cost across states and narratives.

## 5. Liberation as stable flexibility
Liberation is framed as flexible participation without compulsive ownership.

## 6. Stability vs freedom
Stability can reduce noise; freedom is flexible reconfiguration.

## 7. Practice sequence
Stabilize attention, observe grasping, reduce ownership pressure, increase flexible exits.

## 8. Scientific bridge without overclaiming
Operational bridges are hypothesis-generating and require controlled testing.

## 9. What the book does not claim
No metaphysical proof, no clinical guarantee, no claim that telemetry proves liberation.

## 10. Chapter arc
From phenomenology and practice toward constrained research language.

## 11. Draft table of contents
""" + "\n".join(f"{i+1}. {t}" for i,t in enumerate(SEEDS)) + """

## 12. Claim-safety notes
Use candidate/proxy language; quarantine ontology-candidate and clinical overclaim language.
"""
    (out/'book_spine.md').write_text(book,encoding='utf-8')

    lines=['# Chapter Seed Bank','']
    for i,t in enumerate(SEEDS,1):
        lines += [f'## {i}. {t}','- thesis: transition-focused, non-metaphysical framing.','- key concepts: exits, transitions, flexibility, ownership pressure.','- practice angle: observe grasping and release cycles.','- science bridge: candidate observables and controls, no proof language.','- unsafe claims to avoid: soul claims, proof claims, trauma deletion guarantees.','- source tier dependency: book_safe_core + research_hypothesis; quarantine for unsafe examples only.','']
    (out/'chapter_seed_bank.md').write_text('\n'.join(lines),encoding='utf-8')

    report=out/'tol_synthesis_report.md'
    report.write_text(f"""# P28 ToL Synthesis Report

## Inputs used
"""+"\n".join(f"- {x}" for x in INPUTS)+f"""

## Strict validation status
{strict_status}

## Outputs written
- book_spine.md
- chapter_seed_bank.md

## Book spine summary
Built with safe thesis and claim boundaries.

## Research roadmap summary
Pending/produced by research roadmap step.

## Observable bridge summary
Pending/produced by research roadmap step.

## Public language safety summary
Pending/produced by public language guide step.

## Guardrails
No raw synthesis from speculative ToL files; no ontology promotion.

## Next recommended PR
P29: fixture expansion and synthesis linting ergonomics.
""",encoding='utf-8')

    return 1 if missing else 0

if __name__=='__main__': raise SystemExit(main())
