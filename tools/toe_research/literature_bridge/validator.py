import argparse,json
from pathlib import Path
REQ=['toe_literature_priority_matrix.json','topology_telemetry_upgrade_digest.md','active_inference_allostasis_digest.md','computational_psychiatry_digest.md','bioelectric_basal_cognition_digest.md','cosmology_constraint_matrix.json','gravitational_wave_constraint_matrix.json','consciousness_theory_adversarial_matrix.json','equation_candidate_registry.json','toe_falsifier_watchlist.json','toe_theory_integration_digest.md','toe_literature_bridge_report.md','generation_manifest.json']
BAD=['proves consciousness','proves soul','validates toe','final theory','consciousness solved','q proves','qabs proves','fdress proves','diagnoses','treats','cures','clinical efficacy']
def main():
    p=argparse.ArgumentParser();p.add_argument('--root',required=True);p.add_argument('--json-out',required=True);a=p.parse_args();r=Path(a.root);v=[]
    for f in REQ:
        if not (r/f).exists(): v.append(f'missing {f}')
    texts=[]
    for f in r.iterdir():
        if f.is_file(): texts.append(f.read_text(errors='ignore'))
    txt='\n'.join(texts).lower()
    for b in BAD:
        if b in txt: v.append('forbidden:'+b)
    out={'ok':not v,'violations':v};Path(a.json_out).write_text(json.dumps(out,indent=2));raise SystemExit(0 if not v else 1)
if __name__=='__main__':main()
