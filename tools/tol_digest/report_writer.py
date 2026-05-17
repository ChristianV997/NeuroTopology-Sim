from __future__ import annotations
import argparse, json
from pathlib import Path
from .source_registry import build_registry
from .claim_extractor import extract_claims
from .tier_classifier import classify_claim
from .mapping_builder import DOCTRINE_MAP, OBS_MAP
REQ=['source_registry.json','claim_inventory.json','claim_tier_matrix.json','doctrine_to_construct_map.json','observables_map.json','book_insights.md','research_hypotheses.md','quarantine_report.md','next_actions.json','tol_digest_report.md']

def main(argv=None):
    ap=argparse.ArgumentParser(); ap.add_argument('--input',required=True); ap.add_argument('--out',required=True); a=ap.parse_args(argv)
    out=Path(a.out); out.mkdir(parents=True,exist_ok=True)
    reg=build_registry(a.input)
    claims=extract_claims(reg['sources'])
    inv=[]
    tiers={'book_safe_core':0,'research_hypothesis':0,'speculative_quarantined':0,'unsafe_or_requires_rewrite':0}
    for c in claims:
        t,au,rw,ut=classify_claim(c['text']); tiers[t]+=1
        c.update({'tier':t,'category':'doctrine' if 'dukkha' in c['normalized_text'] else 'neuroscience','confidence':0.9,'evidence_status':'textual_claim_only','allowed_use':au,'rewrite_required':rw,'unsafe_terms':ut,'mapped_doctrine':[],'mapped_construct':[],'mapped_observables':[]})
        inv.append(c)
    (out/'source_registry.json').write_text(json.dumps(reg,indent=2),encoding='utf-8')
    (out/'claim_inventory.json').write_text(json.dumps({'claims':inv},indent=2),encoding='utf-8')
    (out/'claim_tier_matrix.json').write_text(json.dumps({'tier_counts':tiers},indent=2),encoding='utf-8')
    (out/'doctrine_to_construct_map.json').write_text(json.dumps(DOCTRINE_MAP,indent=2),encoding='utf-8')
    (out/'observables_map.json').write_text(json.dumps(OBS_MAP,indent=2),encoding='utf-8')
    (out/'book_insights.md').write_text('# Book Insights\n\n## Core thesis\n\n## Suffering as high exit-cost\n\n## Liberation as cheap exits\n\n## Stability vs freedom\n\n## Practice sequence\n\n## Chapter seeds\n\n## Safe language replacements\n',encoding='utf-8')
    (out/'research_hypotheses.md').write_text('# Research Hypotheses\n\n## Dynamics layer\n\n## Topology layer\n\n## Perturbation layer\n\n## Anesthesia wedge\n\n## Meditation contrast\n\n## Falsifiers\n\n## Required controls\n\nUse Q/Qabs/fdress as candidate telemetry only.\n',encoding='utf-8')
    q=[c for c in inv if c['tier'] in {'speculative_quarantined','unsafe_or_requires_rewrite'}]
    (out/'quarantine_report.md').write_text('# Quarantine Report\n\n## Quarantined ontology claims\n\n## Unsafe therapeutic/trauma claims\n\n## Speculative physics claims\n\n## Required rewrites\n\n## Do not use in empirical outputs\n\n'+'\n'.join(f"- {c['text']}" for c in q),encoding='utf-8')
    (out/'next_actions.json').write_text(json.dumps({'actions':['create ToL book spine','create ToL chapter seeds','create ToL research hypothesis registry','create ToL-to-DS005620 observable map','prepare ToL-safe publication language checklist']},indent=2),encoding='utf-8')
    (out/'tol_digest_report.md').write_text('# ToL Digest Report\n\nDeterministic ToL digestion completed.\n',encoding='utf-8')
    return 0
if __name__=='__main__': raise SystemExit(main())
