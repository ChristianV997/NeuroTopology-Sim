from __future__ import annotations
import argparse
import csv
import json
import sys
from pathlib import Path
from sciencer_d.btc_icft.labels.eeg_label_contracts import (
    align_eeg_labels,
    get_label_contract,
    load_external_eeg_label_contract,
    load_metadata_rows,
    load_signal_rows,
    write_label_alignment_outputs,
)

def _write_mock_signal(path: Path, dataset_id: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    cols=["dataset_id","row_id","source_file","window_id","window_start_s","window_end_s","sample_start","sample_end"]
    with path.open("w", newline="", encoding="utf-8") as f:
        w=csv.DictWriter(f, fieldnames=cols); w.writeheader()
        for i in range(2):
            w.writerow({"dataset_id":dataset_id,"row_id":f"r{i}","source_file":"f.edf","window_id":f"w{i}","window_start_s":str(i),"window_end_s":str(i+1),"sample_start":str(i*10),"sample_end":str((i+1)*10)})


def _write_mock_meta(path: Path, active: bool) -> None:
    rows=[{"dataset_id":"DS005620","row_id":"r0","source_file":"f.edf","window_id":"w0","window_start_s":"0","window_end_s":"1","sample_start":"0","sample_end":"10","explicit_state_label":"target"},{"dataset_id":"DS005620","row_id":"r1","source_file":"f.edf","window_id":"w1","window_start_s":"1","window_end_s":"2","sample_start":"10","sample_end":"20","explicit_state_label":"control"}]
    path.write_text("\n".join([",".join(rows[0].keys())]+[",".join(r.values()) for r in rows]), encoding="utf-8")

def run(dataset_id:str, signal_features:str, metadata:str|None, out_dir:str, activate_mock_contract:bool=False, mock_fixture:bool=False, external_contract:str|None=None)->int:
    if external_contract and activate_mock_contract:
        print("Invalid flags: --external-contract cannot be combined with --activate-mock-contract.")
        return 2
    if mock_fixture:
        base=Path(out_dir)/".mock_fixture"; s=base/"features_m_signal.csv"; m=base/"metadata.csv"; _write_mock_signal(s,dataset_id); _write_mock_meta(m,activate_mock_contract); signal_features=str(s); metadata=str(m)
    if not metadata:
        print("Explicit local metadata is required. Provide --metadata or use --mock-fixture.")
        return 1
    if external_contract is not None:
        try:
            contract = load_external_eeg_label_contract(external_contract, dataset_id)
        except (FileNotFoundError, ValueError) as exc:
            print(f"External reviewed contract rejected: {exc}", file=sys.stderr)
            return 2
    else:
        contract=get_label_contract(dataset_id)
        if activate_mock_contract:
            contract.status="active"; contract.explicit_label_column="explicit_state_label"; contract.positive_values=["target"]; contract.negative_values=["control"]
    signals=load_signal_rows(signal_features); metas=load_metadata_rows(metadata)
    try:
        result=align_eeg_labels(dataset_id, signals, metas, contract)
        write_label_alignment_outputs(result, out_dir)
        return 0
    except Exception as exc:
        print(f"P12 alignment failed: {exc}")
        return 1

def main()->int:
    p=argparse.ArgumentParser()
    p.add_argument("--dataset-id", default="DS005620")
    p.add_argument("--signal-features", default="outputs/btc_icft/eeg_level_m/DS005620/features_m_signal.csv")
    p.add_argument("--metadata")
    p.add_argument("--out", default="outputs/btc_icft/eeg_labels/DS005620")
    p.add_argument("--activate-mock-contract", action="store_true")
    p.add_argument("--mock-fixture", action="store_true")
    p.add_argument(
        "--external-contract",
        dest="external_contract",
        default=None,
        help=(
            "Path to a P17.1 reviewed external contract JSON "
            "(p12_external_contract.json). When supplied, replaces the seed "
            "contract with the strictly validated reviewed contract."
        ),
    )
    a=p.parse_args()
    return run(
        a.dataset_id,
        a.signal_features,
        a.metadata,
        a.out,
        a.activate_mock_contract,
        a.mock_fixture,
        a.external_contract,
    )

if __name__=="__main__":
    sys.exit(main())
