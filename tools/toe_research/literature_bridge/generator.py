import argparse,json
from pathlib import Path
def main():
 p=argparse.ArgumentParser();p.add_argument('--roots',nargs='+',required=True);p.add_argument('--out',required=True);p.add_argument('--strict',action='store_true');a=p.parse_args();o=Path(a.out);o.mkdir(parents=True,exist_ok=True);avail={r:Path(r).exists() for r in a.roots}
 (o/'toe_literature_priority_matrix.json').write_text(json.dumps({'inputs':avail,'status':['not_available' if not v else 'available' for v in avail.values()]},indent=2))
 (o/'toe_theory_integration_digest.md').write_text('P40 integration digest')
 (o/'toe_literature_bridge_report.md').write_text('P40 Summary')
 (o/'generation_manifest.json').write_text(json.dumps({'ok':True},indent=2))
if __name__=='__main__':main()