import argparse
from .common import read_json, write_json
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--scorecard',required=True);p.add_argument('--out',required=True);a=p.parse_args();rows=read_json(a.scorecard)['external_systems_scorecard']
 rows=sorted(rows,key=lambda x:x['score'],reverse=True)
 write_json(a.out,{"integration_priority_queue":[{"item_id":f"prio_{i:03d}","subsystem":r['source_domain'],"reason":f"High reusable pattern value from {r['repo_full_name']}","score":r['score'],"next_steps":["confirm license record","implement adapter fixture","validate outputs"]} for i,r in enumerate(rows,1)]})
