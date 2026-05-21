import argparse,json
from pathlib import Path
D=['ΛCDM','BAO','DESI','CMB','SNe','Euclid lensing','Hubble tension']
def main():
 p=argparse.ArgumentParser();p.add_argument('--out',required=True);a=p.parse_args();rows=[{'constraint_id':f'C{i+1}','observable':x,'standard_model_expectation':'baseline','allowed_toe_deviation':'bounded','falsifier':'data reject','required_dataset':x,'claim_scope':'evidence_mapping','evidence_state':'conceptual_mapping'} for i,x in enumerate(D)]
 rows.append({'constraint_id':'C8','observable':'dark energy equation of state','standard_model_expectation':'w=-1','allowed_toe_deviation':'w0,wa bounded','falsifier':'inconsistency','required_dataset':'joint','claim_scope':'research_hypothesis','evidence_state':'requires_validation','equations':['H²(z)=...','w(z)=w₀ + w_a z/(1+z)','H²_TOE(z)=H²_ΛCDM(z)+ΔH²_TOE(z; θ)']})
 Path(a.out).write_text(json.dumps(rows,indent=2))
if __name__=='__main__':main()