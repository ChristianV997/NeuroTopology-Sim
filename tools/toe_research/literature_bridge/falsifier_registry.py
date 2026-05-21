import argparse,json
from pathlib import Path
F=['F1','F2','F3','F4','F5','F6','F7','F8','F9','F10']
def main():
 p=argparse.ArgumentParser();p.add_argument('--out',required=True);a=p.parse_args();rows=[{'id':f,'claim_affected':'x','affected_subsystems':['x'],'observable_required':'x','failure_condition':'x','claim_demotion_action':'x','next_experiment_or_simulation':'x','priority':'high'} for f in F];Path(a.out).write_text(json.dumps(rows,indent=2))
if __name__=='__main__':main()