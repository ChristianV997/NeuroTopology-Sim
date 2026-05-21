import argparse,json
from pathlib import Path
D=['Kerr ringdown','quasi-normal modes','black-hole spectroscopy','area theorem','GR reduction limit']
def main():
 p=argparse.ArgumentParser();p.add_argument('--out',required=True);a=p.parse_args();rows=[{'constraint_id':f'G{i+1}','observable':x,'standard_GR_expectation':'baseline','allowed_toe_deviation':'bounded','falsifier':'deviation absent','required_dataset':x,'claim_scope':'evidence_mapping','evidence_state':'conceptual_mapping'} for i,x in enumerate(D)]
 rows.append({'equations':['h(t)=Σ_n A_n e^{-t/τ_n} cos(ω_n t + φ_n)','ω_n = ω_n^Kerr(M,a)(1 + δ_n)','τ_n = τ_n^Kerr(M,a)(1 + γ_n)','A_final ≥ A_1 + A_2']})
 Path(a.out).write_text(json.dumps(rows,indent=2))
if __name__=='__main__':main()