from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from pathlib import Path

from sciencer_d.btc_icft.report_guardrails import BANNED_REPORT_PHRASES, validate_safe_text

BANNED_TEXT_TERMS = (
    "liberation",
    "enlightenment",
    "soul",
    "afterlife",
    "ultimate reality",
    "ontology solved",
)


@dataclass(frozen=True)
class DS005620DatasetConfig:
    dataset_id: str = "ds005620"
    dataset_name: str = "DS005620 anesthesia-state label contract scaffold"
    bids_root: str | None = None
    output_root: str = "outputs/btc_icft/ds005620"
    required_tasks: list[str] = field(default_factory=list)
    subject_split_required: bool = True
    artifact_report_required: bool = True
    allowed_state_labels: list[str] = field(default_factory=list)
    allowed_behavior_labels: list[str] = field(default_factory=list)
    allowed_report_labels: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class DS005620LabelRow:
    row_id: str
    subject_id: str
    session_id: str | None = None
    run_id: str | None = None
    window_id: str | None = None
    state_label: str | None = None
    behavior_label: str | None = None
    report_label: str | None = None
    task_label: str | None = None
    confidence: float | None = None
    source: str | None = None
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class DS005620DatasetCard:
    dataset_id: str
    dataset_name: str
    n_rows: int
    n_subjects: int
    state_labels: dict[str, int]
    behavior_labels: dict[str, int]
    report_labels: dict[str, int]
    required_tasks: list[str]
    subject_split_required: bool
    artifact_report_required: bool
    caveats: list[str]
    safe_claim: str
    forbidden_claims: list[str]


@dataclass(frozen=True)
class DS005620ContractReport:
    dataset_id: str
    n_rows: int
    n_subjects: int
    valid: bool
    errors: list[str]
    warnings: list[str]
    label_counts: dict[str, dict[str, int]]
    required_outputs: list[str]
    safe_claim: str
    forbidden_claims: list[str]


def _validate_safe_text(text: str) -> None:
    validate_safe_text(text)


def _count(rows: list[DS005620LabelRow], field_name: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for row in rows:
        value = getattr(row, field_name)
        if value is None:
            continue
        out[value] = out.get(value, 0) + 1
    return out


def validate_ds005620_label_row(row: DS005620LabelRow) -> list[str]:
    errors: list[str] = []
    if not row.row_id:
        errors.append("row_id is required")
    if not row.subject_id:
        errors.append("subject_id is required")
    if row.confidence is not None and not (0.0 <= row.confidence <= 1.0):
        errors.append(f"row {row.row_id}: confidence must be in [0, 1]")
    if row.behavior_label == "no_experience":
        errors.append(f"row {row.row_id}: no_experience may only appear as report_label")
    if row.state_label == "unconscious":
        errors.append(f"row {row.row_id}: unconscious must not be used as state_label")
    if row.state_label in {"experience", "no_experience"}:
        errors.append(f"row {row.row_id}: state_label cannot be an experience label")

    fields = [row.state_label or "", row.behavior_label or "", row.report_label or "", row.task_label or "", row.source or "", " ".join(row.notes)]
    blob = " ".join(fields).lower()
    for term in BANNED_TEXT_TERMS:
        if term in blob:
            errors.append(f"row {row.row_id}: forbidden ontology term detected: {term}")
    if "unresponsive" in blob and "unconscious" in blob:
        errors.append(f"row {row.row_id}: unresponsive must not be equated with unconscious")
    if "sedated" in blob and "no_experience" in blob and "means" in blob:
        errors.append(f"row {row.row_id}: sedated must not be asserted as no_experience")
    return errors


def validate_ds005620_contract(rows: list[DS005620LabelRow], config: DS005620DatasetConfig) -> DS005620ContractReport:
    errors: list[str] = []
    warnings: list[str] = []
    for row in rows:
        errors.extend(validate_ds005620_label_row(row))
        if row.state_label and row.state_label not in config.allowed_state_labels:
            warnings.append(f"row {row.row_id}: unknown state_label={row.state_label}")
        if row.behavior_label and row.behavior_label not in config.allowed_behavior_labels:
            warnings.append(f"row {row.row_id}: unknown behavior_label={row.behavior_label}")
        if row.report_label and row.report_label not in config.allowed_report_labels:
            warnings.append(f"row {row.row_id}: unknown report_label={row.report_label}")

    subjects = {r.subject_id for r in rows if r.subject_id}
    if config.subject_split_required and len(subjects) < 2:
        errors.append("subject_split_required=true needs at least 2 unique subjects")

    required_outputs = ["dataset_card.json", "label_contract_report.json", "report.md"]
    if config.artifact_report_required:
        required_outputs.append("artifact_report.json")

    safe_claim = (
        "DS005620 metadata can be used to define operational anesthesia-state and report/behavior "
        "label contracts for future BTC/ICFT Level M and Level T residual testing."
    )
    forbidden_claims = [
        "This contract does not prove consciousness ontology.",
        "This contract does not equate unresponsiveness with unconsciousness.",
        "This contract does not equate sedation with no experience.",
        "This contract does not prove self, soul, liberation, afterlife, enlightenment, or ultimate reality.",
    ]

    label_counts = {
        "state": _count(rows, "state_label"),
        "behavior": _count(rows, "behavior_label"),
        "report": _count(rows, "report_label"),
    }

    return DS005620ContractReport(
        dataset_id=config.dataset_id,
        n_rows=len(rows),
        n_subjects=len(subjects),
        valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
        label_counts=label_counts,
        required_outputs=required_outputs,
        safe_claim=safe_claim,
        forbidden_claims=forbidden_claims,
    )


def build_ds005620_dataset_card(config: DS005620DatasetConfig, rows: list[DS005620LabelRow]) -> DS005620DatasetCard:
    report = validate_ds005620_contract(rows, config)
    return DS005620DatasetCard(
        dataset_id=config.dataset_id,
        dataset_name=config.dataset_name,
        n_rows=report.n_rows,
        n_subjects=report.n_subjects,
        state_labels=report.label_counts["state"],
        behavior_labels=report.label_counts["behavior"],
        report_labels=report.label_counts["report"],
        required_tasks=config.required_tasks,
        subject_split_required=config.subject_split_required,
        artifact_report_required=config.artifact_report_required,
        caveats=config.notes,
        safe_claim=report.safe_claim,
        forbidden_claims=report.forbidden_claims,
    )


def write_ds005620_contract_outputs(config: DS005620DatasetConfig, rows: list[DS005620LabelRow], out_dir: str) -> dict[str, str]:
    report = validate_ds005620_contract(rows, config)
    card = build_ds005620_dataset_card(config, rows)
    base = Path(out_dir)
    base.mkdir(parents=True, exist_ok=True)

    report_md = "\n".join([
        "# DS005620 BTC/ICFT Dataset Contract",
        f"- dataset_id: {config.dataset_id}",
        f"- n_rows: {report.n_rows}",
        f"- n_subjects: {report.n_subjects}",
        f"- validation status: {'valid' if report.valid else 'invalid'}",
        "- caveats:",
        *[f"  - {c}" for c in config.notes],
        f"- safe claim: {report.safe_claim}",
        "- forbidden claims:",
        "  - This contract does not support ontology-level conclusions.",
        "  - This contract does not equate unresponsive behavior with unawareness.",
        "  - This contract does not equate sedation with absent report by default.",
        "- required next step: prepare Level M baseline datasets with subject-safe split and artifact report.",
    ])
    _validate_safe_text(report_md)

    card_path = base / "dataset_card.json"
    contract_path = base / "label_contract_report.json"
    report_path = base / "report.md"
    card_path.write_text(json.dumps(asdict(card), indent=2), encoding="utf-8")
    contract_path.write_text(json.dumps(asdict(report), indent=2), encoding="utf-8")
    report_path.write_text(report_md + "\n", encoding="utf-8")
    return {
        "dataset_card.json": str(card_path),
        "label_contract_report.json": str(contract_path),
        "report.md": str(report_path),
    }
