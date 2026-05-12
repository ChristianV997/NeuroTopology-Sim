from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

_BANNED_PHRASES = (
    "proves consciousness",
    "consciousness proven",
    "soul proven",
    "afterlife proven",
    "liberation detected",
    "ontology solved",
    "ultimate reality",
    "q equals self",
    "q equals soul",
    "q_abs equals suffering",
    "f_dress equals karma",
    "sedated implies no_experience",
    "unresponsive implies unconscious",
)

_ALLOWED_SCOPES = {"window", "file", "run", "subject", "session"}
_REQUIRED_SIGNAL_COLS = ["dataset_id", "row_id", "source_file", "window_id", "window_start_s", "window_end_s", "sample_start", "sample_end"]


@dataclass
class EEGLabelMetadataRow:
    data: dict


@dataclass
class EEGLabelContract:
    dataset_id: str
    title: str
    source_hint: str
    status: str
    label_scope: str
    explicit_label_column: str | None
    positive_values: list[str]
    negative_values: list[str]
    join_keys: list[str]
    allowed_metadata_extensions: list[str]
    caveats: list[str]
    guardrails: list[str]


@dataclass
class EEGLabelAlignmentRow:
    dataset_id: str
    row_id: str | None
    source_file: str | None
    window_id: str | None
    window_start_s: float | None
    window_end_s: float | None
    sample_start: int | None
    sample_end: int | None
    label: str | None
    y: int | None
    label_scope: str
    alignment_status: str
    provenance: str
    caveats: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class EEGLabelAlignmentResult:
    dataset_id: str
    contract: dict
    n_signal_rows: int
    n_metadata_rows: int
    n_aligned: int
    n_rejected: int
    n_targets_available: int
    explicit_targets_available: bool
    alignment_rows: list[dict]
    rejected_rows: list[dict]
    label_alignment_report: dict
    omega_event: dict
    safe_claim: str
    forbidden_claims: list[str]
    warnings: list[str]


def _validate_safe_text(text: str) -> None:
    lower = text.lower()
    for phrase in _BANNED_PHRASES:
        if phrase in lower:
            raise ValueError(f"Banned phrase detected: {phrase}")


def get_seed_label_contracts() -> dict[str, EEGLabelContract]:
    ids = ["DS005620", "DS002094", "ds001787", "ds003969", "ds003816", "PhysioNet_GABA"]
    base = dict(
        source_hint="local_metadata",
        status="inactive_until_metadata_supplied",
        label_scope="window",
        explicit_label_column=None,
        positive_values=[],
        negative_values=[],
        join_keys=_REQUIRED_SIGNAL_COLS.copy(),
        allowed_metadata_extensions=[".csv", ".tsv", ".json"],
        caveats=["Seed contract stub; explicit metadata mapping required before activation."],
        guardrails=["no_label_inference", "no_target_fabrication", "no_sedated_to_no_experience", "no_unresponsive_to_unconscious", "no_ontology_claims", "no_soul_afterlife_claims", "no_liberation_claims"],
    )
    return {d: EEGLabelContract(dataset_id=d, title=f"EEG explicit label contract seed for {d}", **base) for d in ids}


def get_label_contract(dataset_id: str) -> EEGLabelContract:
    registry = get_seed_label_contracts()
    if dataset_id not in registry:
        raise ValueError(f"Unknown dataset_id: {dataset_id}")
    return registry[dataset_id]


_REQUIRED_EXTERNAL_CONTRACT_FIELDS = (
    "dataset_id",
    "explicit_label_column",
    "positive_values",
    "negative_values",
    "join_keys",
)
_EXPECTED_EXTERNAL_CONTRACT_STATUS = "active_reviewed_external_contract"


def load_external_eeg_label_contract(path: str, dataset_id: str) -> EEGLabelContract:
    """Load and strictly validate a P17.1 reviewed external contract JSON.

    Converts the reviewed external contract artifact into an EEGLabelContract
    with status='active' so existing alignment logic runs unchanged.

    Validation:
      - file exists, JSON readable
      - dataset_id matches caller's dataset_id
      - contract_status == 'active_reviewed_external_contract' (or legacy 'status' field)
      - explicit_label_column non-empty
      - positive_values, negative_values are non-empty lists with no overlap
      - join_keys contains all strict keys

    Raises FileNotFoundError or ValueError on any validation failure.
    """
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(
            f"External reviewed contract not found: {path}. "
            "Run P17.1 (materialize_ds005620_reviewed_contract) first."
        )
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"External reviewed contract is not valid JSON: {exc}")

    missing = [f for f in _REQUIRED_EXTERNAL_CONTRACT_FIELDS if f not in data]
    if missing:
        raise ValueError(
            f"External reviewed contract missing required fields: {missing}"
        )

    if str(data.get("dataset_id", "")) != dataset_id:
        raise ValueError(
            f"External reviewed contract dataset_id is {data.get('dataset_id')!r}, "
            f"expected {dataset_id!r}"
        )

    # Support legacy 'status' field as fallback for 'contract_status'
    contract_status = data.get("contract_status") or data.get("status")
    if contract_status != _EXPECTED_EXTERNAL_CONTRACT_STATUS:
        raise ValueError(
            f"External reviewed contract contract_status is "
            f"{contract_status!r}, expected "
            f"{_EXPECTED_EXTERNAL_CONTRACT_STATUS!r}"
        )

    label_column = data["explicit_label_column"]
    if not isinstance(label_column, str) or not label_column.strip():
        raise ValueError(
            "External reviewed contract explicit_label_column must be a non-empty string"
        )

    positive = data["positive_values"]
    if not isinstance(positive, list) or len(positive) == 0:
        raise ValueError(
            "External reviewed contract positive_values must be a non-empty list"
        )
    negative = data["negative_values"]
    if not isinstance(negative, list) or len(negative) == 0:
        raise ValueError(
            "External reviewed contract negative_values must be a non-empty list"
        )

    overlap = sorted(set(map(str, positive)) & set(map(str, negative)))
    if overlap:
        raise ValueError(
            f"External reviewed contract positive_values and negative_values "
            f"overlap: {overlap}"
        )

    contract_keys = data["join_keys"]
    if not isinstance(contract_keys, list):
        raise ValueError("External reviewed contract join_keys must be a list")
    missing_keys = [k for k in _REQUIRED_SIGNAL_COLS if k not in contract_keys]
    if missing_keys:
        raise ValueError(
            f"External reviewed contract join_keys missing strict keys: {missing_keys}"
        )

    label_scope = data.get("label_scope", "window")
    if label_scope not in _ALLOWED_SCOPES:
        raise ValueError(
            f"External reviewed contract label_scope {label_scope!r} not supported"
        )

    return EEGLabelContract(
        dataset_id=dataset_id,
        title=str(data.get("title") or f"EEG explicit label contract from external reviewed P17.1 artifact for {dataset_id}"),
        source_hint=str(data.get("source_hint") or "external_reviewed_contract"),
        status="active",
        label_scope=label_scope,
        explicit_label_column=label_column,
        positive_values=[str(v) for v in positive],
        negative_values=[str(v) for v in negative],
        join_keys=list(contract_keys),
        allowed_metadata_extensions=[str(x) for x in data.get("allowed_metadata_extensions") or [".csv", ".tsv", ".json"]],
        caveats=[str(x) for x in data.get("caveats") or [
            "Contract sourced from external reviewed P17.1 artifact; "
            "no labels inferred and no targets fabricated.",
        ]],
        guardrails=list(data.get("guardrails") or [
            "no_label_inference",
            "no_target_fabrication",
            "no_filename_derived_labels",
            "no_topology_derived_labels",
            "no_artifact_derived_labels",
            "no_sedated_to_no_experience",
            "no_unresponsive_to_unconscious",
            "no_ontology_claims",
            "no_soul_afterlife_claims",
            "no_liberation_claims",
        ]),
    )


def load_metadata_rows(path: str) -> list[dict]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Metadata file not found: {p}. Provide a local metadata file via --metadata.")
    ext = p.suffix.lower()
    if ext not in {".csv", ".tsv", ".json"}:
        raise ValueError(f"Unsupported metadata extension: {ext}")
    if ext in {".csv", ".tsv"}:
        with p.open("r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter="\t" if ext == ".tsv" else ",")
            return [{k: "" if v is None else str(v) for k, v in r.items()} for r in reader]
    payload = json.loads(p.read_text(encoding="utf-8"))
    rows = payload if isinstance(payload, list) else payload.get("rows", []) if isinstance(payload, dict) else []
    return [{k: "" if v is None else str(v) for k, v in r.items()} for r in rows if isinstance(r, dict)]


def load_signal_rows(path: str) -> list[dict]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Signal features file not found: {p}")
    with p.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        cols = reader.fieldnames or []
        missing = [c for c in _REQUIRED_SIGNAL_COLS if c not in cols]
        if missing:
            raise ValueError(f"Missing required signal columns: {missing}")
        return [dict(r) for r in reader]


def _candidate_key(row: dict, contract: EEGLabelContract) -> tuple:
    if contract.label_scope == "window":
        return tuple(str(row.get(k, "")) for k in contract.join_keys)
    if contract.label_scope == "file":
        return (str(row.get("source_file", "")),)
    if contract.label_scope == "subject":
        return (str(row.get("subject_id", "")),)
    if contract.label_scope == "session":
        return (str(row.get("subject_id", "")), str(row.get("session_id", "")))
    return (str(row.get("subject_id", "")), str(row.get("session_id", "")), str(row.get("run_id", "")))


def align_eeg_labels(dataset_id: str, signal_rows: list[dict], metadata_rows: list[dict], contract: EEGLabelContract) -> EEGLabelAlignmentResult:
    if contract.label_scope not in _ALLOWED_SCOPES:
        raise ValueError("Unsupported label_scope")
    aligned = []
    rejected = []
    status_counts = {}

    if contract.status != "active":
        for s in signal_rows:
            row = EEGLabelAlignmentRow(dataset_id, s.get("row_id"), s.get("source_file"), s.get("window_id"), float(s.get("window_start_s") or 0), float(s.get("window_end_s") or 0), int(float(s.get("sample_start") or 0)), int(float(s.get("sample_end") or 0)), None, None, contract.label_scope, "rejected_contract_inactive", "contract", contract.caveats[:], [])
            aligned.append(asdict(row)); status_counts[row.alignment_status]=status_counts.get(row.alignment_status,0)+1
        result = EEGLabelAlignmentResult(dataset_id, asdict(contract), len(signal_rows), len(metadata_rows), 0, len(signal_rows), 0, False, aligned, [], {}, {}, "Explicit local EEG metadata labels were aligned to signal windows under a declared label contract for future controlled predictive testing.", ["No consciousness proof.", "No self or soul claim.", "No liberation or enlightenment claim.", "No afterlife claim.", "No ontology proof.", "No label inference.", "No target fabrication.", "No sedated/no_experience shortcut.", "No unresponsive/unconscious shortcut."], [])
        result.label_alignment_report = build_label_alignment_report(result)
        result.omega_event = build_label_omega_event(result)
        return result

    meta_index = {}
    for m in metadata_rows:
        if contract.explicit_label_column is None:
            continue
        for key in contract.join_keys:
            if key not in m:
                continue
        key = _candidate_key(m, contract)
        meta_index.setdefault(key, []).append(m)

    for s in signal_rows:
        warnings = []
        caveats = contract.caveats[:]
        if contract.label_scope != "window":
            caveats.append("Label scope is broader than window; target applies by declared contract scope.")
        missing_keys = [k for k in contract.join_keys if contract.label_scope == "window" and not str(s.get(k, ""))]
        if missing_keys:
            status = "rejected_missing_join_key"
            aligned.append(asdict(EEGLabelAlignmentRow(dataset_id, s.get("row_id"), s.get("source_file"), s.get("window_id"), None, None, None, None, None, None, contract.label_scope, status, "signal_row", caveats, warnings)))
            rejected.append({"status": status, "reason": f"missing join keys: {missing_keys}", "metadata": None, "candidate_key": None})
            status_counts[status] = status_counts.get(status, 0) + 1
            continue
        key = _candidate_key(s, contract)
        matches = meta_index.get(key, [])
        if not matches:
            status = "rejected_missing_label"
            aligned.append(asdict(EEGLabelAlignmentRow(dataset_id, s.get("row_id"), s.get("source_file"), s.get("window_id"), None, None, None, None, None, None, contract.label_scope, status, "metadata", caveats, warnings)))
            rejected.append({"status": status, "reason": "no metadata match", "metadata": None, "candidate_key": list(key)})
            status_counts[status] = status_counts.get(status, 0) + 1
            continue
        labels = []
        for m in matches:
            if contract.explicit_label_column not in m:
                continue
            labels.append(str(m.get(contract.explicit_label_column, "")))
        if not labels:
            status = "rejected_missing_label"
            aligned.append(asdict(EEGLabelAlignmentRow(dataset_id, s.get("row_id"), s.get("source_file"), s.get("window_id"), None, None, None, None, None, None, contract.label_scope, status, "metadata", caveats, warnings)))
            rejected.append({"status": status, "reason": "explicit label column missing", "metadata": matches[0], "candidate_key": list(key)})
            status_counts[status] = status_counts.get(status, 0) + 1
            continue
        uniq = set(labels)
        if len(uniq) > 1:
            status = "rejected_conflicting_label"
            aligned.append(asdict(EEGLabelAlignmentRow(dataset_id, s.get("row_id"), s.get("source_file"), s.get("window_id"), None, None, None, None, None, None, contract.label_scope, status, "metadata", caveats, warnings)))
            rejected.append({"status": status, "reason": "conflicting metadata labels", "metadata": matches, "candidate_key": list(key)})
            status_counts[status] = status_counts.get(status, 0) + 1
            continue
        label = next(iter(uniq))
        in_pos, in_neg = label in contract.positive_values, label in contract.negative_values
        if in_pos and in_neg:
            status = "rejected_ambiguous_mapping"; y = None
        elif in_pos:
            status = "aligned"; y = 1
        elif in_neg:
            status = "aligned"; y = 0
        else:
            status = "rejected_unknown_label_value"; y = None
        row = EEGLabelAlignmentRow(dataset_id, s.get("row_id"), s.get("source_file"), s.get("window_id"), float(s.get("window_start_s") or 0), float(s.get("window_end_s") or 0), int(float(s.get("sample_start") or 0)), int(float(s.get("sample_end") or 0)), label, y, contract.label_scope, status, "explicit_metadata", caveats, warnings)
        aligned.append(asdict(row)); status_counts[status]=status_counts.get(status,0)+1
        if status != "aligned":
            rejected.append({"status": status, "reason": status, "metadata": matches, "candidate_key": list(key)})

    n_targets = sum(1 for r in aligned if r.get("y") in (0,1))
    result = EEGLabelAlignmentResult(dataset_id, asdict(contract), len(signal_rows), len(metadata_rows), status_counts.get("aligned",0), len(signal_rows)-status_counts.get("aligned",0), n_targets, n_targets>0, aligned, rejected, {}, {}, "Explicit local EEG metadata labels were aligned to signal windows under a declared label contract for future controlled predictive testing.", ["No consciousness proof.", "No self or soul claim.", "No liberation or enlightenment claim.", "No afterlife claim.", "No ontology proof.", "No label inference.", "No target fabrication.", "No sedated/no_experience shortcut.", "No unresponsive/unconscious shortcut."], [])
    result.label_alignment_report = build_label_alignment_report(result)
    result.omega_event = build_label_omega_event(result)
    return result


def build_label_alignment_report(result: EEGLabelAlignmentResult) -> dict:
    ys = [r.get("y") for r in result.alignment_rows if r.get("y") in (0,1)]
    return {
        "dataset_id": result.dataset_id,
        "contract_status": result.contract.get("status"),
        "label_scope": result.contract.get("label_scope"),
        "explicit_label_column": result.contract.get("explicit_label_column"),
        "n_signal_rows": result.n_signal_rows,
        "n_metadata_rows": result.n_metadata_rows,
        "n_aligned": result.n_aligned,
        "n_rejected": result.n_rejected,
        "n_targets_available": result.n_targets_available,
        "explicit_targets_available": result.explicit_targets_available,
        "status_counts": {s: sum(1 for r in result.alignment_rows if r.get("alignment_status")==s) for s in set(r.get("alignment_status") for r in result.alignment_rows)},
        "positive_values": result.contract.get("positive_values", []),
        "negative_values": result.contract.get("negative_values", []),
        "warnings": result.warnings,
        "ready_for_p11_with_targets": result.explicit_targets_available and result.n_targets_available > 0 and (0 in ys and 1 in ys),
    }


def build_label_omega_event(result: EEGLabelAlignmentResult) -> dict:
    _validate_safe_text(result.safe_claim)
    payload = f"{result.dataset_id}:{result.n_targets_available}:{result.explicit_targets_available}:{result.safe_claim}"
    return {"event_id": hashlib.sha256(payload.encode()).hexdigest()[:16], "event_type": "eeg_label_alignment", "dataset_id": result.dataset_id, "n_signal_rows": result.n_signal_rows, "n_targets_available": result.n_targets_available, "safe_claim": result.safe_claim, "forbidden_claims": result.forbidden_claims}


def write_label_alignment_outputs(result: EEGLabelAlignmentResult, out_dir: str) -> dict[str, str]:
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    outputs = {}
    p = out / "label_contract.json"; p.write_text(json.dumps(result.contract, indent=2), encoding="utf-8"); outputs[p.name]=str(p)
    cols=["dataset_id","row_id","source_file","window_id","window_start_s","window_end_s","sample_start","sample_end","label","y","label_scope","alignment_status","provenance","caveats","warnings"]
    p = out / "label_alignment.csv"
    with p.open("w", newline="", encoding="utf-8") as f:
        w=csv.DictWriter(f, fieldnames=cols); w.writeheader()
        for r in result.alignment_rows:
            row=dict(r); row["caveats"]=" | ".join(row.get("caveats",[])); row["warnings"]=" | ".join(row.get("warnings",[])); w.writerow(row)
    outputs[p.name]=str(p)
    p = out / "label_alignment_report.json"; p.write_text(json.dumps(result.label_alignment_report, indent=2), encoding="utf-8"); outputs[p.name]=str(p)
    p = out / "rejected_labels.json"; p.write_text(json.dumps({"rejected_rows": result.rejected_rows}, indent=2), encoding="utf-8"); outputs[p.name]=str(p)
    p = out / "omega_event.json"; p.write_text(json.dumps(result.omega_event, indent=2), encoding="utf-8"); outputs[p.name]=str(p)
    report = "# EEG Explicit Label Contract Alignment\n\n## Stage\nExplicit-label contract alignment layer for future controlled predictive testing.\n\n## Dataset\n- dataset_id: {}\n\n## Contract\n- status: {}\n- label_scope: {}\n- explicit_label_column: {}\n\n## Metadata input\n- n_metadata_rows: {}\n\n## Signal rows\n- n_signal_rows: {}\n\n## Alignment results\n- n_aligned: {}\n- n_rejected: {}\n\n## Rejected labels\n- rejected_rows: {}\n\n## Target availability\n- explicit_targets_available: {}\n- n_targets_available: {}\n- ready_for_p11_with_targets: {}\n\n## Safe claim\n{}\n\n## Forbidden claims\n{}\n\n## Next required step\nIf ready_for_p11_with_targets is true, merge explicit y targets into Level M signal features and rerun P11 under controlled target-aware validation.\n".format(result.dataset_id, result.contract.get("status"), result.contract.get("label_scope"), result.contract.get("explicit_label_column"), result.n_metadata_rows, result.n_signal_rows, result.n_aligned, result.n_rejected, len(result.rejected_rows), result.explicit_targets_available, result.n_targets_available, result.label_alignment_report.get("ready_for_p11_with_targets"), result.safe_claim, "\n".join(f"- {x}" for x in result.forbidden_claims))
    _validate_safe_text(report)
    p = out / "report.md"; p.write_text(report, encoding="utf-8"); outputs[p.name]=str(p)
    return outputs
