from __future__ import annotations
import argparse
from pathlib import Path
from . import DATASET_ID, DEFAULT_OUT, GUARDRAIL_FLAGS, write_json

CANDS=["data/DS002094","data/ds002094","inputs/DS002094","inputs/ds002094"]

def main() -> None:
    ap=argparse.ArgumentParser(); ap.add_argument('--out', default=str(DEFAULT_OUT)); args=ap.parse_args()
    out=Path(args.out)
    roots=[Path(p) for p in CANDS]
    existing=[str(p) for p in roots if p.exists()]
    missing=[str(p) for p in roots if not p.exists()]
    meta=[]; eeg=[]
    for r in roots:
        if not r.exists(): continue
        for name in ["participants.tsv","dataset_description.json","README","CHANGES"]:
            if (r/name).exists(): meta.append(str(r/name))
        meta += [str(x) for x in r.glob("**/*events.tsv")]
        eeg += [str(x) for x in r.glob("**/*.edf")] + [str(x) for x in r.glob("**/*.vhdr")] + [str(x) for x in r.glob("**/*.set")]
    data={"dataset_id":DATASET_ID,"candidate_roots":CANDS,"existing_roots":existing,"missing_roots":missing,
          "candidate_metadata_files":sorted(set(meta)),"candidate_raw_eeg_files":sorted(set(eeg)),
          "bids_like_structure_detected":bool(meta or eeg),"local_data_available":bool(existing),
          "blocked_by":[] if existing else ["local_dataset_root_missing"],
          "next_action":"review_local_DS002094_root" if existing else "provide_local_DS002094_root",**GUARDRAIL_FLAGS}
    write_json(out/'local_data_preflight.json',data)
    write_json(out/'missing_local_files.json',{"dataset_id":DATASET_ID,"missing_roots":missing})

if __name__=='__main__': main()
