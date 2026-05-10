from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re

from sciencer_d.btc_icft.datasets.ds005620 import (
    BANNED_TEXT_TERMS,
    DS005620DatasetConfig,
    DS005620LabelRow,
    validate_ds005620_contract,
)

BANNED_EXTRA = (
    "proves consciousness",
    "consciousness proven",
    "q equals self",
    "q equals soul",
    "q_abs equals suffering",
    "f_dress equals karma",
)
SAFE_STATE = {"awake", "sedated", "loc_candidate", "roc_candidate"}
SAFE_BEHAVIOR = {"responsive", "unresponsive", "partial"}
SAFE_REPORT = {"experience", "no_experience", "dream", "imagery", "discontinuity"}
EEG_EXTENSIONS = {".edf", ".bdf", ".set", ".vhdr", ".fif", ".eeg", ".tsv", ".json"}


@dataclass(frozen=True)
class BIDSFileRecord:
    path: str
    relative_path: str
    subject_id: str | None
    session_id: str | None
    task_label: str | None
    run_id: str | None
    suffix: str | None
    extension: str
    is_eeg_candidate: bool
    is_metadata_candidate: bool
    warnings: list[str]


@dataclass(frozen=True)
class BIDSInspectionResult:
    dataset_id: str
    bids_root: str
    n_files: int
    n_subjects: int
    eeg_candidates: list[dict]
    metadata_candidates: list[dict]
    label_candidates: list[dict]
    contract_report: dict
    warnings: list[str]
    errors: list[str]
    safe_claim: str
    forbidden_claims: list[str]


def _validate_safe_text(text: str) -> None:
    low = text.lower()
    for t in BANNED_EXTRA:
        if t in low:
            raise ValueError(f"forbidden phrase detected: {t}")


def _token(rel: str, key: str) -> str | None:
    if key == "task":
        m = re.search(r"task-([a-zA-Z0-9_]+?)(?=_(?:run|ses|sub|acq|rec|proc|space|desc|eeg)-|_eeg\.|\.|$)", rel)
        if m:
            return m.group(1)
    for part in rel.replace('/', '_').split('_'):
        if part.startswith(f"{key}-"):
            return part.split('-', 1)[1]
    return None


def _suffix(stem: str) -> str | None:
    parts = stem.split("_")
    return parts[-1] if parts else None


def discover_ds005620_bids_files(bids_root: str) -> list[BIDSFileRecord]:
    root = Path(bids_root)
    if not root.exists():
        raise FileNotFoundError(f"BIDS root does not exist: {bids_root}. Provide a local DS005620-style directory.")
    out = []
    for p in sorted(x for x in root.rglob("*") if x.is_file()):
        rel = p.relative_to(root).as_posix()
        low_rel = rel.lower()
        for term in BANNED_TEXT_TERMS:
            if term in low_rel:
                raise ValueError(f"forbidden phrase detected: {term}")
        _validate_safe_text(rel)
        name = p.name.lower()
        ext = p.suffix.lower()
        subj = _token(rel, "sub")
        ses = _token(rel, "ses")
        task = _token(rel, "task")
        run = _token(rel, "run")
        suf = _suffix(p.stem)
        meta = name in {"participants.tsv", "participants.json"} or name.endswith("_events.tsv") or name.endswith("_channels.tsv") or name.endswith("_eeg.json")
        out.append(BIDSFileRecord(str(p), rel, subj, ses, task, run, suf, ext, ext in EEG_EXTENSIONS, meta, []))
    return out


def build_label_candidates(records: list[BIDSFileRecord]) -> list[DS005620LabelRow]:
    rows = []
    for r in records:
        if not r.subject_id:
            continue
        row_id = f"{r.subject_id}:{r.session_id or 'noses'}:{r.run_id or 'norun'}:{r.relative_path}"
        task = (r.task_label or "").lower() if r.task_label else None
        state = task if task in SAFE_STATE else ("unknown" if task else None)
        behavior = task if task in SAFE_BEHAVIOR else ("unknown" if task else None)
        report = task if task in SAFE_REPORT else ("unknown" if task else None)
        notes = []
        if task and task not in SAFE_STATE | SAFE_BEHAVIOR | SAFE_REPORT:
            notes.append("task label not mapped to known DS005620 labels")
        row = DS005620LabelRow(
            row_id=row_id,
            subject_id=r.subject_id,
            session_id=r.session_id,
            run_id=r.run_id,
            state_label=state,
            behavior_label=behavior,
            report_label=report,
            task_label=r.task_label,
            source=r.relative_path,
            notes=notes,
        )
        rows.append(row)
    return rows


def inspect_ds005620_bids_root(bids_root: str) -> BIDSInspectionResult:
    records = discover_ds005620_bids_files(bids_root)
    labels = build_label_candidates(records)
    cfg = DS005620DatasetConfig(
        allowed_state_labels=["awake", "sedated", "loc_candidate", "roc_candidate", "unknown"],
        allowed_behavior_labels=["responsive", "unresponsive", "partial", "unknown"],
        allowed_report_labels=["experience", "no_experience", "dream", "imagery", "discontinuity", "unknown"],
    )
    contract = asdict(validate_ds005620_contract(labels, cfg))
    contract.update({
        "n_label_candidates": len(labels),
        "n_subjects": len({x.subject_id for x in labels}),
        "subject_split_possible": len({x.subject_id for x in labels}) >= 2,
        "artifact_report_required": cfg.artifact_report_required,
    })
    return BIDSInspectionResult(
        dataset_id="ds005620",
        bids_root=str(Path(bids_root)),
        n_files=len(records),
        n_subjects=len({r.subject_id for r in records if r.subject_id}),
        eeg_candidates=[asdict(r) for r in records if r.is_eeg_candidate],
        metadata_candidates=[asdict(r) for r in records if r.is_metadata_candidate],
        label_candidates=[asdict(r) for r in labels],
        contract_report=contract,
        warnings=[],
        errors=[],
        safe_claim="Local DS005620-style files were inspected and mapped into operational metadata candidates for future Level M and Level T residual testing.",
        forbidden_claims=[
            "No consciousness proof.", "No self/soul/afterlife claim.", "No liberation/enlightenment claim.", "No ontology proof.", "No unsafe label shortcuts.",
        ],
    )


def write_bids_inspection_outputs(result: BIDSInspectionResult, out_dir: str) -> dict[str, str]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    inv = out / "file_inventory.json"
    labels = out / "label_candidates.json"
    contract = out / "contract_report.json"
    report = out / "report.md"
    inv.write_text(json.dumps({"dataset_id": result.dataset_id, "bids_root": result.bids_root, "n_files": result.n_files, "n_subjects": result.n_subjects, "eeg_candidates": result.eeg_candidates, "metadata_candidates": result.metadata_candidates}, indent=2), encoding="utf-8")
    labels.write_text(json.dumps(result.label_candidates, indent=2), encoding="utf-8")
    contract.write_text(json.dumps(result.contract_report, indent=2), encoding="utf-8")
    txt = "\n".join([
        "# DS005620 BIDS Inspection Contract",
        "## Dataset/root",
        f"- dataset_id: {result.dataset_id}",
        f"- bids_root: {result.bids_root}",
        "## File inventory summary",
        f"- n_files: {result.n_files}",
        f"- n_subjects: {result.n_subjects}",
        "## Metadata candidates",
        f"- n_metadata_candidates: {len(result.metadata_candidates)}",
        "## Label candidates",
        f"- n_label_candidates: {len(result.label_candidates)}",
        "## Contract validation",
        f"- valid: {result.contract_report.get('valid')}",
        "## Warnings/errors",
        f"- warnings: {result.warnings}",
        f"- errors: {result.errors}",
        "## Safe claim",
        f"- {result.safe_claim}",
        "## Forbidden claims",
        *[f"- {c}" for c in result.forbidden_claims],
        "## Next required step",
        "- Wire inspected DS005620 BIDS-like files into real Level M window extraction, preserving label-contract guardrails.",
        "- This output provides operational metadata candidates for future Level M and future Level T residual testing.",
    ])
    _validate_safe_text(txt)
    report.write_text(txt + "\n", encoding="utf-8")
    return {"file_inventory.json": str(inv), "label_candidates.json": str(labels), "contract_report.json": str(contract), "report.md": str(report)}
