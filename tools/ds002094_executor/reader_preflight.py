from __future__ import annotations
import argparse, importlib.util
from pathlib import Path
from . import DATASET_ID, DEFAULT_OUT, GUARDRAIL_FLAGS, write_json

def main() -> None:
    ap=argparse.ArgumentParser(); ap.add_argument('--out', default=str(DEFAULT_OUT)); args=ap.parse_args()
    mne_avail=importlib.util.find_spec('mne') is not None
    data={"dataset_id":DATASET_ID,"bids_reader_available":True,"mne_dependency_available_or_optional":mne_avail,
          "dataset_specific_reader_available":False,"metadata_parser_available":True,"events_parser_available":True,
          "raw_eeg_discovery_available":True,"blocked_by":["dataset_specific_reader_mapping_not_implemented"],
          "next_action":"implement_or_review_reader_mapping",**GUARDRAIL_FLAGS}
    write_json(Path(args.out)/'reader_preflight.json',data)
if __name__=='__main__': main()
