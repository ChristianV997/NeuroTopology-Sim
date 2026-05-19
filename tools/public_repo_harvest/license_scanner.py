import argparse
from .common import read_json, write_json
ALLOWED={"MIT","Apache-2.0","BSD-2-Clause","BSD-3-Clause","ISC"}
MANUAL={"MPL-2.0","LGPL","EPL","custom"}
BLOCK={"GPL","AGPL","unknown","proprietary","no-license"}

def rec(c):
 lic=c.get('likely_license','unknown')
 if lic in ALLOWED:status="safe_to_adapt";copy=True;manual=False;r="Permissive open-source license is compatible for small attributed snippets."
 elif lic in MANUAL:status="manual_review_required";copy=False;manual=True;r="License requires manual legal compatibility review."
 else:status="blocked_license";copy=False;manual=True;r="Code copy blocked; use pattern-only reimplementation."
 return {"repo":c['repo'],"detected_license":lic,"license_spdx":lic,"compatibility_status":status,"can_copy_code":copy,"can_copy_docs":False,"can_adapt_patterns":True,"attribution_required":True,"notice_required":True,"manual_review_required":manual,"decision_rationale":r}
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--candidates',required=True);p.add_argument('--out',required=True);a=p.parse_args();c=read_json(a.candidates)['candidates'];write_json(a.out,{"license_matrix":[rec(i) for i in c]})
