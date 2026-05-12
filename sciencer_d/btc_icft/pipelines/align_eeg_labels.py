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

_STRICT_JOIN_KEYS = _REQUIRED_SIGNAL_COLS
_EXTERNAL_CONTRACT_REQUIRED_STATUS = "active_reviewed_external_contract"
_DEFAULT_METADATA_EXTENSIONS = [".csv", ".tsv", ".json"]
_DEFAULT_CAVEATS = ["External reviewed contract; labels from explicit metadata only."]
_DEFAULT_GUARDRAILS = ["no_label_inference", "no_target_fabrication", "no_ontology_claims"]


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

def load_external_contract(path: str, dataset_id: str) -> EEGLabelContract:
    """Load and validate a reviewed external contract JSON, returning an EEGLabelContract.

    Raises ValueError with a clear message for any validation failure.
    """
    p = Path(path)
    if not p.is_file():
        raise ValueError(f"External contract file not found: {path}")

    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValueError(f"External contract is not valid JSON: {exc}") from exc

    errors: list[str] = []

    # Require dataset_id match
    contract_dataset_id = data.get("dataset_id")
    if contract_dataset_id != dataset_id:
        errors.append(
            f"External contract dataset_id {contract_dataset_id!r} does not match "
            f"--dataset-id {dataset_id!r}"
        )

    # Accept either status key for compatibility across reviewed contract generators.
    contract_status = data.get("status", data.get("contract_status"))
    if contract_status != _EXTERNAL_CONTRACT_REQUIRED_STATUS:
        errors.append(
            f"External contract status is {contract_status!r}; "
            f"expected {_EXTERNAL_CONTRACT_REQUIRED_STATUS!r}"
        )

    # Require explicit_label_column
    explicit_label_column = data.get("explicit_label_column")
    if not explicit_label_column:
        errors.append("External contract explicit_label_column is missing or empty")

    # Require positive_values non-empty
    positive_values = data.get("positive_values") or []
    if not positive_values:
        errors.append("External contract positive_values is missing or empty")

    # Require negative_values non-empty
    negative_values = data.get("negative_values") or []
    if not negative_values:
        errors.append("External contract negative_values is missing or empty")

    # Require positive_values and negative_values do not overlap
    overlap = set(positive_values) & set(negative_values)
    if overlap:
        errors.append(
            f"External contract positive_values and negative_values overlap: {sorted(overlap)}"
        )

    # Require exact strict join keys.
    join_keys = tuple(data.get("join_keys") or [])
    expected_join_keys = tuple(_STRICT_JOIN_KEYS)
    if join_keys != expected_join_keys:
        errors.append(
            "External contract join_keys must match strict required join keys exactly; "
            f"expected {list(expected_join_keys)} got {list(join_keys)}"
        )

    if errors:
        raise ValueError(
            "Invalid external contract:\n" + "\n".join(f"  - {e}" for e in errors)
        )

    return EEGLabelContract(
        dataset_id=dataset_id,
        title=data.get("title", f"External reviewed contract for {dataset_id}"),
        source_hint=data.get("source_hint", "external_reviewed_contract"),
        status="active",
        label_scope=data.get("label_scope", "window"),
        explicit_label_column=explicit_label_column,
        positive_values=list(positive_values),
        negative_values=list(negative_values),
        join_keys=list(_STRICT_JOIN_KEYS),
        allowed_metadata_extensions=list(data.get("allowed_metadata_extensions") or _DEFAULT_METADATA_EXTENSIONS),
        caveats=list(data.get("caveats") or _DEFAULT_CAVEATS),
        guardrails=list(data.get("guardrails") or _DEFAULT_GUARDRAILS),
    )


def run(dataset_id:str, signal_features:str, metadata:str|None, out_dir:str, activate_mock_contract:bool=False, mock_fixture:bool=False, external_contract:str|None=None)->int:
    if mock_fixture:
        base=Path(out_dir)/".mock_fixture"; s=base/"features_m_signal.csv"; m=base/"metadata.csv"; _write_mock_signal(s,dataset_id); _write_mock_meta(m,activate_mock_contract); signal_features=str(s); metadata=str(m)

    if external_contract:
        try:
            contract = load_external_contract(external_contract, dataset_id)
        except ValueError as exc:
            print(str(exc))
            return 1
        if not metadata:
            print("Explicit local metadata is required when using --external-contract. Provide --metadata.")
            return 1
    else:
        if not metadata:
            print("Explicit local metadata is required. Provide --metadata or use --mock-fixture.")
            return 1
        contract=get_label_contract(dataset_id)
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
    p.add_argument("--external-contract", default=None,
                   help="Path to a reviewed external contract JSON file (P17.1 output).")
    a=p.parse_args()
    return run(a.dataset_id, a.signal_features, a.metadata, a.out, a.activate_mock_contract, a.mock_fixture, a.external_contract)

if __name__=="__main__":
    sys.exit(main())
