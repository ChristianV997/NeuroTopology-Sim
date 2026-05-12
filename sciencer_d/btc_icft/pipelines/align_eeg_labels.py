from __future__ import annotations
import argparse
import csv
import json
import sys
from pathlib import Path
from sciencer_d.btc_icft.labels.eeg_label_contracts import (
    EEGLabelContract,
    _REQUIRED_SIGNAL_COLS,
    align_eeg_labels, get_label_contract, load_metadata_rows, load_signal_rows, write_label_alignment_outputs
)

def _write_mock_signal(path: Path, dataset_id: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    cols=["dataset_id","row_id","source_file","window_id","window_start_s","window_end_s","sample_start","sample_end"]
    with path.open("w", newline="", encoding="utf-8") as f:
        w=csv.DictWriter(f, fieldnames=cols); w.writeheader()
        for i in range(2):
            w.writerow({"dataset_id":dataset_id,"row_id":f"r{i}","source_file":"f.edf","window_id":f"w{i}","window_start_s":str(i),"window_end_s":str(i+1),"sample_start":str(i*10),"sample_end":str((i+1)*10)})



def _load_external_contract(path: str, dataset_id: str) -> EEGLabelContract:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if str(payload.get("dataset_id", "")) != dataset_id:
        raise ValueError("external contract dataset_id must match --dataset-id")
    if payload.get("status") != "active_reviewed_external_contract":
        raise ValueError("external contract status must be active_reviewed_external_contract")
    explicit_label_column = str(payload.get("explicit_label_column", "")).strip()
    if not explicit_label_column:
        raise ValueError("external contract explicit_label_column must be non-empty")
    positive_values = [str(x) for x in payload.get("positive_values", []) if str(x)]
    negative_values = [str(x) for x in payload.get("negative_values", []) if str(x)]
    if not positive_values or not negative_values:
        raise ValueError("external contract positive_values and negative_values must be non-empty")
    if set(positive_values).intersection(negative_values):
        raise ValueError("external contract positive_values and negative_values must not overlap")
    join_keys = payload.get("join_keys", [])
    if join_keys != _REQUIRED_SIGNAL_COLS:
        raise ValueError("external contract join_keys must match strict required join keys")

    return EEGLabelContract(
        dataset_id=dataset_id,
        title=str(payload.get("title") or f"Reviewed external EEG label contract for {dataset_id}"),
        source_hint=str(payload.get("source_hint") or "reviewed_external_contract"),
        status="active",
        label_scope=str(payload.get("label_scope") or "window"),
        explicit_label_column=explicit_label_column,
        positive_values=positive_values,
        negative_values=negative_values,
        join_keys=list(join_keys),
        allowed_metadata_extensions=[str(x) for x in payload.get("allowed_metadata_extensions", [".csv", ".tsv", ".json"])],
        caveats=[str(x) for x in payload.get("caveats", [])],
        guardrails=[str(x) for x in payload.get("guardrails", [])],
    )

def _write_mock_meta(path: Path, active: bool) -> None:
    rows=[{"dataset_id":"DS005620","row_id":"r0","source_file":"f.edf","window_id":"w0","window_start_s":"0","window_end_s":"1","sample_start":"0","sample_end":"10","explicit_state_label":"target"},{"dataset_id":"DS005620","row_id":"r1","source_file":"f.edf","window_id":"w1","window_start_s":"1","window_end_s":"2","sample_start":"10","sample_end":"20","explicit_state_label":"control"}]
    path.write_text("\n".join([",".join(rows[0].keys())]+[",".join(r.values()) for r in rows]), encoding="utf-8")

def run(dataset_id:str, signal_features:str, metadata:str|None, out_dir:str, activate_mock_contract:bool=False, mock_fixture:bool=False, external_contract:str|None=None)->int:
    if mock_fixture:
        base=Path(out_dir)/".mock_fixture"; s=base/"features_m_signal.csv"; m=base/"metadata.csv"; _write_mock_signal(s,dataset_id); _write_mock_meta(m,activate_mock_contract); signal_features=str(s); metadata=str(m)
    if not metadata:
        print("Explicit local metadata is required. Provide --metadata or use --mock-fixture.")
        return 1
    contract=_load_external_contract(external_contract, dataset_id) if external_contract else get_label_contract(dataset_id)
    if activate_mock_contract:
        contract.status="active"; contract.explicit_label_column="explicit_state_label"; contract.positive_values=["target"]; contract.negative_values=["control"]
    signals=load_signal_rows(signal_features); metas=load_metadata_rows(metadata)
    result=align_eeg_labels(dataset_id, signals, metas, contract)
    write_label_alignment_outputs(result, out_dir)
    return 0

def main()->int:
    p=argparse.ArgumentParser()
    p.add_argument("--dataset-id", default="DS005620")
    p.add_argument("--signal-features", default="outputs/btc_icft/eeg_level_m/DS005620/features_m_signal.csv")
    p.add_argument("--metadata")
    p.add_argument("--out", default="outputs/btc_icft/eeg_labels/DS005620")
    p.add_argument("--activate-mock-contract", action="store_true")
    p.add_argument("--mock-fixture", action="store_true")
    p.add_argument("--external-contract")
    a=p.parse_args()
    return run(a.dataset_id,a.signal_features,a.metadata,a.out,a.activate_mock_contract,a.mock_fixture,a.external_contract)

if __name__=="__main__":
    sys.exit(main())
