from __future__ import annotations
import argparse
from pathlib import Path
from . import DATASET_ID, DEFAULT_OUT, GUARDRAIL_FLAGS, write_json

def main() -> None:
    ap=argparse.ArgumentParser(); ap.add_argument('--out', default=str(DEFAULT_OUT)); args=ap.parse_args()
    data={"dataset_id":DATASET_ID,"contract_status_required":"human_reviewed",
    "explicit_label_column_required":True,"allowed_label_source":"human_reviewed_metadata_only",
    "forbidden_label_sources":["filename","topology","signal amplitude","model prediction","artifact path","inferred sedation shortcut","inferred unresponsiveness shortcut"],
    "strict_join_keys_required":True,"positive_values_required":"human_declared","negative_values_required":"human_declared",
    "overlap_forbidden":True,"requires_human_review":True,"auto_activation_allowed":False,
    "labels_inferred":False,"targets_fabricated":False,**GUARDRAIL_FLAGS}
    write_json(Path(args.out)/'contract_requirements.json',data)

if __name__=='__main__': main()
