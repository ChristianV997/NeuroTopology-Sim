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

_SAFE_CLAIM = (
    "DS005620 local metadata was audited for explicit human-reviewed label-contract activation "
    "readiness without inferring labels or targets."
)

_DEFAULT_JOIN_KEYS = [
    "dataset_id",
    "row_id",
    "source_file",
    "window_id",
    "window_start_s",
    "window_end_s",
    "sample_start",
    "sample_end",
]

_POSITIVE_HINTS = ("label", "state", "condition", "group", "class", "target", "response", "task")
_NEGATIVE_HINTS = ("notes", "description", "comment", "narrative", "text", "filename", "file", "path", "url")


@dataclass
class DS005620MetadataValueAuditRow:
    column: str
    n_rows: int
    n_nonempty: int
    n_unique: int
    unique_values: list[str]
    binary_candidate: bool
    likely_label_candidate: bool
    rejected_reason: str | None
    warnings: list[str] = field(default_factory=list)


@dataclass
class DS005620ActivationProposal:
    dataset_id: str
    explicit_label_column: str | None
    candidate_label_columns: list[str]
    unresolved_values: list[str]
    positive_values: list[str]
    negative_values: list[str]
    label_scope: str
    join_keys: list[str]
    metadata_provenance: str
    semantic_justification_required: bool
    no_shortcut_inference_required: bool
    contract_activation_allowed: bool
    activation_blockers: list[str]
    required_human_decisions: list[str]
    guardrails: list[str]


@dataclass
class DS005620ActivationResult:
    dataset_id: str
    n_metadata_rows: int
    n_metadata_columns: int
    metadata_file_exists: bool
    metadata_value_audit: list[dict]
    activation_proposal: dict
    human_review_packet: dict
    activation_blockers: dict
    omega_event: dict
    safe_claim: str
    forbidden_claims: list[str]
    warnings: list[str]


def _validate_safe_text(text: str) -> None:
    lower = text.lower()
    for phrase in _BANNED_PHRASES:
        if phrase in lower:
            raise ValueError(f"Banned phrase detected: {phrase}")


def _stringify_row(row: dict) -> dict:
    return {str(k): "" if v is None else str(v) for k, v in row.items()}


def load_metadata_rows(path: str) -> list[dict]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Metadata file not found: {p}")

    ext = p.suffix.lower()
    if ext not in {".csv", ".tsv", ".json"}:
        raise ValueError(f"Unsupported metadata extension: {ext}")

    if ext in {".csv", ".tsv"}:
        with p.open("r", newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh, delimiter="\t" if ext == ".tsv" else ",")
            return [_stringify_row(r) for r in reader]

    payload = json.loads(p.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        rows = payload.get("rows", [])
    else:
        rows = []
    return [_stringify_row(r) for r in rows if isinstance(r, dict)]


def load_contract_drafts(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Contract drafts not found: {p}")
    payload = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Contract drafts payload must be a JSON object.")
    return payload


def _looks_like_free_text(column: str, values: list[str]) -> bool:
    cl = column.lower()
    if any(h in cl for h in ("notes", "description", "comment", "narrative", "text")):
        return True
    if not values:
        return False
    longish = [v for v in values if len(v) > 30 or (" " in v and len(v) > 16)]
    return len(longish) >= max(1, len(values) // 2)


def _looks_like_file_path(column: str, values: list[str]) -> bool:
    cl = column.lower()
    if any(h in cl for h in ("filename", "file", "path", "url")):
        return True
    for v in values:
        lv = v.lower()
        if "/" in v or "\\" in v or lv.startswith("http://") or lv.startswith("https://"):
            return True
        if lv.endswith((".edf", ".csv", ".tsv", ".json", ".npy")):
            return True
    return False


def audit_metadata_values(metadata_rows: list[dict]) -> list[DS005620MetadataValueAuditRow]:
    if not metadata_rows:
        return []

    columns: list[str] = []
    seen: set[str] = set()
    for row in metadata_rows:
        for c in row.keys():
            if c not in seen:
                seen.add(c)
                columns.append(c)

    audits: list[DS005620MetadataValueAuditRow] = []
    n_rows = len(metadata_rows)
    for col in columns:
        values = [str(r.get(col, "")).strip() for r in metadata_rows]
        nonempty = [v for v in values if v != ""]
        unique_values = sorted(set(nonempty))
        n_nonempty = len(nonempty)
        n_unique = len(unique_values)
        binary_candidate = n_unique == 2

        warnings: list[str] = []
        rejected_reason: str | None = None
        if n_nonempty == 0:
            rejected_reason = "empty_column"
        elif n_unique == 1:
            rejected_reason = "single_value_only"
        elif _looks_like_file_path(col, unique_values):
            rejected_reason = "likely_file_path"
        elif _looks_like_free_text(col, unique_values):
            rejected_reason = "likely_free_text"
        elif n_unique > 20:
            rejected_reason = "too_many_unique_values"
        elif not any(h in col.lower() for h in _POSITIVE_HINTS):
            rejected_reason = "no_label_signal"

        likely_label_candidate = rejected_reason is None and (
            any(h in col.lower() for h in _POSITIVE_HINTS)
            and not any(h in col.lower() for h in _NEGATIVE_HINTS)
        )

        if binary_candidate and rejected_reason is not None:
            warnings.append("binary_candidate_rejected")

        audits.append(
            DS005620MetadataValueAuditRow(
                column=col,
                n_rows=n_rows,
                n_nonempty=n_nonempty,
                n_unique=n_unique,
                unique_values=unique_values,
                binary_candidate=binary_candidate,
                likely_label_candidate=likely_label_candidate,
                rejected_reason=rejected_reason,
                warnings=warnings,
            )
        )
    return audits


def _resolve_metadata_provenance(contract_drafts: dict | None) -> str:
    if not isinstance(contract_drafts, dict):
        return "local_metadata_unverified"
    for key in ("metadata_provenance", "provenance"):
        if key in contract_drafts and str(contract_drafts[key]).strip():
            return str(contract_drafts[key]).strip()
    ds = contract_drafts.get("DS005620")
    if isinstance(ds, dict):
        for key in ("metadata_provenance", "provenance"):
            if key in ds and str(ds[key]).strip():
                return str(ds[key]).strip()
    return "local_metadata_unverified"


def prepare_ds005620_activation_proposal(
    metadata_rows: list[dict],
    contract_drafts: dict | None = None,
) -> DS005620ActivationResult:
    metadata_rows = [_stringify_row(r) for r in metadata_rows if isinstance(r, dict)]
    metadata_audit_rows = audit_metadata_values(metadata_rows)

    candidate_columns = [a.column for a in metadata_audit_rows if a.binary_candidate or a.likely_label_candidate]
    unresolved_values = sorted(
        {
            v
            for a in metadata_audit_rows
            if a.column in candidate_columns
            for v in a.unique_values
            if v != ""
        }
    )

    blockers: list[str] = []
    metadata_exists = bool(metadata_rows)
    if not metadata_rows:
        blockers.append("metadata_required")

    blockers.extend(
        [
            "explicit_label_column_required",
            "positive_values_required",
            "negative_values_required",
            "both_classes_required",
            "human_review_required",
            "semantic_justification_required",
            "no_shortcut_inference_confirmation_required",
            "separate_contract_activation_pr_required",
        ]
    )
    if unresolved_values:
        blockers.append("ambiguous_values_rejected")

    blockers = sorted(set(blockers), key=blockers.index)

    proposal = DS005620ActivationProposal(
        dataset_id="DS005620",
        explicit_label_column=None,
        candidate_label_columns=candidate_columns,
        unresolved_values=unresolved_values,
        positive_values=[],
        negative_values=[],
        label_scope="window",
        join_keys=_DEFAULT_JOIN_KEYS.copy(),
        metadata_provenance=_resolve_metadata_provenance(contract_drafts),
        semantic_justification_required=True,
        no_shortcut_inference_required=True,
        contract_activation_allowed=False,
        activation_blockers=blockers,
        required_human_decisions=[
            "choose explicit_label_column",
            "declare positive_values",
            "declare negative_values",
            "declare label_scope",
            "verify join_keys",
            "verify metadata provenance",
            "justify semantic mapping",
            "confirm no shortcut inference",
            "approve contract activation in separate PR",
        ],
        guardrails=[
            "no_data_download",
            "no_label_inference",
            "no_target_fabrication",
            "no_sedated_to_no_experience",
            "no_unresponsive_to_unconscious",
            "no_filename_derived_labels",
            "no_topology_derived_labels",
            "no_artifact_derived_labels",
            "no_automatic_real_contract_activation",
            "no_p11_gate_modification",
            "no_legacy_mt_real_change",
            "no_level_o",
            "no_ontology_claims",
            "no_soul_afterlife_claims",
            "no_liberation_claims",
        ],
    )

    result = DS005620ActivationResult(
        dataset_id="DS005620",
        n_metadata_rows=len(metadata_rows),
        n_metadata_columns=len({k for row in metadata_rows for k in row.keys()}),
        metadata_file_exists=metadata_exists,
        metadata_value_audit=[asdict(r) for r in metadata_audit_rows],
        activation_proposal=asdict(proposal),
        human_review_packet={},
        activation_blockers={},
        omega_event={},
        safe_claim=_SAFE_CLAIM,
        forbidden_claims=[
            "No consciousness proof.",
            "No self or soul claim.",
            "No liberation or enlightenment claim.",
            "No afterlife claim.",
            "No ontology proof.",
            "No label inference.",
            "No target fabrication.",
            "No sedated/no_experience shortcut.",
            "No unresponsive/unconscious shortcut.",
        ],
        warnings=[],
    )
    result.human_review_packet = build_human_review_packet(result)
    result.activation_blockers = build_activation_blockers(result)
    result.omega_event = build_ds005620_activation_omega_event(result)
    return result


def build_human_review_packet(result: DS005620ActivationResult) -> dict:
    packet = {
        "dataset_id": result.dataset_id,
        "checklist": [
            "Confirm explicit label column is human-declared.",
            "Confirm positive/negative value sets are human-declared.",
            "Confirm label scope and join keys match metadata provenance.",
            "Confirm no shortcut inference is used.",
            "Confirm activation is proposed in a separate PR.",
        ],
        "required_decisions": result.activation_proposal.get("required_human_decisions", []),
        "evidence_needed": [
            "Local metadata file path and hash.",
            "Reviewed column/value audit output.",
            "Human semantic mapping rationale.",
            "Join-key verification notes.",
        ],
        "reviewer_questions": [
            "Which explicit_label_column is declared?",
            "What are positive_values and negative_values?",
            "What is the approved label_scope?",
            "Are join_keys valid for all rows?",
            "What confirms no shortcut inference was used?",
        ],
        "activation_allowed": False,
    }
    _validate_safe_text(json.dumps(packet))
    return packet


def build_activation_blockers(result: DS005620ActivationResult) -> dict:
    proposal = result.activation_proposal
    unresolved = proposal.get("unresolved_values", [])
    positive = proposal.get("positive_values", [])
    negative = proposal.get("negative_values", [])
    explicit = proposal.get("explicit_label_column")

    gates = {
        "metadata_file_exists": bool(result.metadata_file_exists),
        "explicit_label_column_declared": bool(explicit),
        "positive_values_declared": bool(positive),
        "negative_values_declared": bool(negative),
        "label_scope_declared": bool(proposal.get("label_scope")),
        "join_keys_declared": bool(proposal.get("join_keys")),
        "both_classes_present": bool(positive and negative),
        "ambiguous_values_rejected": len(unresolved) == 0,
        "human_review_required": False,
        "contract_activation_allowed": False,
    }

    blockers = list(proposal.get("activation_blockers", []))
    if not gates["metadata_file_exists"] and "metadata_required" not in blockers:
        blockers.insert(0, "metadata_required")

    payload = {
        "dataset_id": result.dataset_id,
        "contract_activation_allowed": False,
        "blockers": blockers,
        "gates": gates,
    }
    _validate_safe_text(json.dumps(payload))
    return payload


def build_ds005620_activation_omega_event(result: DS005620ActivationResult) -> dict:
    payload = f"{result.dataset_id}:{result.n_metadata_rows}:{result.safe_claim}"
    event = {
        "event_id": hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16],
        "stage": "btc_icft_p16_ds005620_contract_activation_packet",
        "dataset_id": result.dataset_id,
        "safe_claim": result.safe_claim,
        "forbidden_claims": result.forbidden_claims,
        "contract_activation_allowed": False,
    }
    _validate_safe_text(json.dumps(event))
    return event


def write_ds005620_activation_outputs(result: DS005620ActivationResult, out_dir: str) -> dict[str, str]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    outputs: dict[str, str] = {}

    p = out / "activation_proposal.json"
    p.write_text(json.dumps(result.activation_proposal, indent=2), encoding="utf-8")
    outputs[p.name] = str(p)

    p = out / "human_review_packet.json"
    p.write_text(json.dumps(result.human_review_packet, indent=2), encoding="utf-8")
    outputs[p.name] = str(p)

    p = out / "metadata_value_audit.csv"
    with p.open("w", newline="", encoding="utf-8") as fh:
        cols = [
            "column",
            "n_rows",
            "n_nonempty",
            "n_unique",
            "unique_values",
            "binary_candidate",
            "likely_label_candidate",
            "rejected_reason",
            "warnings",
        ]
        writer = csv.DictWriter(fh, fieldnames=cols)
        writer.writeheader()
        for row in result.metadata_value_audit:
            writer.writerow(
                {
                    "column": row.get("column", ""),
                    "n_rows": row.get("n_rows", 0),
                    "n_nonempty": row.get("n_nonempty", 0),
                    "n_unique": row.get("n_unique", 0),
                    "unique_values": "|".join(row.get("unique_values", [])),
                    "binary_candidate": row.get("binary_candidate", False),
                    "likely_label_candidate": row.get("likely_label_candidate", False),
                    "rejected_reason": row.get("rejected_reason", "") or "",
                    "warnings": "|".join(row.get("warnings", [])),
                }
            )
    outputs[p.name] = str(p)

    p = out / "activation_blockers.json"
    p.write_text(json.dumps(result.activation_blockers, indent=2), encoding="utf-8")
    outputs[p.name] = str(p)

    p = out / "omega_event.json"
    p.write_text(json.dumps(result.omega_event, indent=2), encoding="utf-8")
    outputs[p.name] = str(p)

    report = "\n".join(
        [
            "# DS005620 Human-Reviewed Contract Activation Packet",
            "",
            "## Stage",
            "",
            "P16 activation-planning scaffold for DS005620.",
            "",
            "## Dataset",
            "",
            f"- dataset_id: {result.dataset_id}",
            "",
            "## Metadata audit",
            "",
            f"- n_metadata_rows: {result.n_metadata_rows}",
            f"- n_metadata_columns: {result.n_metadata_columns}",
            f"- metadata_file_exists: {result.metadata_file_exists}",
            "",
            "## Activation proposal",
            "",
            f"- contract_activation_allowed: {result.activation_proposal.get('contract_activation_allowed', False)}",
            f"- explicit_label_column: {result.activation_proposal.get('explicit_label_column')}",
            f"- candidate_label_columns: {result.activation_proposal.get('candidate_label_columns', [])}",
            f"- unresolved_values: {result.activation_proposal.get('unresolved_values', [])}",
            "",
            "## Human review packet",
            "",
            "- activation_allowed: false",
            "- This packet is human-reviewed and conservative by design.",
            "",
            "## Activation blockers",
            "",
            f"- blockers: {result.activation_blockers.get('blockers', [])}",
            "",
            "## Safe claim",
            "",
            result.safe_claim,
            "",
            "## Forbidden claims",
            "",
            *[f"- {x}" for x in result.forbidden_claims],
            "",
            "## Next required step",
            "",
            "Open a separate contract-activation PR only after a human reviewer declares explicit_label_column, positive_values, negative_values, label_scope, join_keys, metadata provenance, and no-shortcut justification.",
        ]
    ) + "\n"
    _validate_safe_text(report)
    p = out / "report.md"
    p.write_text(report, encoding="utf-8")
    outputs[p.name] = str(p)

    return outputs
