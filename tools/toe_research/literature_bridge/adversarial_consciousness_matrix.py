import argparse,json
from pathlib import Path
T=['Global Workspace Theory','Integrated Information Theory','Recurrent Processing Theory','Active Inference','Higher-Order Theories','Orch-OR','Predictive Processing']
def main():
 p=argparse.ArgumentParser();p.add_argument('--out',required=True);a=p.parse_args();rows=[{'theory':t,'core_claim':'x','what_it_explains':'x','what_BTC_ICFT_adds':'x','what_BTC_ICFT_does_not_explain':'x','shared_predictions':['x'],'divergent_predictions':['x'],'falsifier':'x','required_experiment':'x','claim_scope':'evidence_mapping'} for t in T];Path(a.out).write_text(json.dumps(rows,indent=2))
if __name__=='__main__':main()