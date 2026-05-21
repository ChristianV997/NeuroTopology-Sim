from __future__ import annotations
import argparse
from pathlib import Path
from . import DATASET_ID, DEFAULT_OUT, GUARDRAIL_FLAGS, write_json

def build() -> dict:
    return {
        "dataset_id": DATASET_ID,
        "source": "OpenNeuro",
        "dataset_family": "anesthesia_or_consciousness_benchmark",
        "role_in_project": "secondary validation dataset for PCI / consciousness-state benchmarking",
        "generic_supported": True,
        "dataset_specific_executor_template": True,
        "real_execution_available": False,
        "manual_real_execution_required": True,
        "local_roots_checked": ["data/DS002094", "data/ds002094", "inputs/DS002094", "inputs/ds002094"],
        **GUARDRAIL_FLAGS,
    }

def main() -> None:
    ap=argparse.ArgumentParser(); ap.add_argument('--out', default=str(DEFAULT_OUT)); args=ap.parse_args()
    out=Path(args.out); write_json(out/'dataset_registry.json', build())

if __name__=='__main__': main()
