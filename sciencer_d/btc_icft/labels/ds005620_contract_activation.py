"""P16 — DS005620 human-reviewed label contract activation packet.

Audits local DS005620 metadata files and produces an explicit contract
activation proposal and human-review packet.

This module does NOT activate any label contract. It does NOT infer labels.
It does NOT emit y targets. It does NOT run P11.
Real activation requires a separate human-reviewed PR.

Public API
----------
DS005620MetadataValueAuditRow
DS005620ActivationProposal
DS005620ActivationResult
load_metadata_rows(path)
load_contract_drafts(path)
audit_metadata_values(metadata_rows)
prepare_ds005620_activation_proposal(metadata_rows, contract_drafts=None)
build_human_review_packet(result)
build_activation_blockers(result)
build_ds005620_activation_omega_event(result)
write_ds005620_activation_outputs(result, out_dir)
"""
from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

_SAFE_CLAIM = (
    "DS005620 local metadata was audited for explicit human-reviewed "
    "label-contract activation readiness without inferring labels or targets."
)

_BANNED_PHRASES: tuple[str, ...] = (
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

_FORBIDDEN_CLAIMS = [
    "No consciousness proof.",
    "No self or soul claim.",
    "No liberation or enlightenment claim.",
    "No afterlife claim.",
    "No ontology proof.",
    "No label inference.",
    "No target fabrication.",
    "No contract activation.",
    "No sedated/no_experience shortcut.",
    "No unresponsive/unconscious shortcut.",
]

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

_REQUIRED_HUMAN_DECISIONS = [
    "choose explicit_label_column",
    "declare positive_values",
    "declare negative_values",
    "declare label_scope",
    "verify join_keys",
    "verify metadata provenance",
    "justify semantic mapping",
    "confirm no shortcut inference",
    "approve contract activation in separate PR",
]

_DEFAULT_GUARDRAILS = [
    "no_label_inference",
    "no_target_fabrication",
    "no_contract_activation_without_human_review",
    "no_sedated_to_no_experience",
    "no_unresponsive_to_unconscious",
    "no_filename_derived_labels",
    "no_topology_derived_labels",
    "no_artifact_derived_labels",
    "no_ontology_claims",
    "no_soul_afterlife_claims",
    "no_liberation_claims",
]

_POSITIVE_COLUMN_HINTS = frozenset({
    "label", "state", "condition", "group", "class",
    "target", "response", "task",
})

_NEGATIVE_COLUMN_HINTS = frozenset({
    "notes", "description", "comment", "narrative", "text",
    "filename", "file", "path", "url",
})

_MAX_UNIQUE_FOR_LABEL = 20
_MIN_UNIQUE_FOR_BINARY = 2


def _validate_safe_text(text: str) -> None:
    lower = text.lower()
    for phrase in _BANNED_PHRASES:
        if phrase in lower:
            raise ValueError(f"Banned phrase detected: {phrase!r}")


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

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
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Metadata loading
# ---------------------------------------------------------------------------

def load_metadata_rows(path: str) -> list[dict]:
    """Load metadata rows from CSV, TSV, or JSON.

    Raises FileNotFoundError if file is missing.
    Raises ValueError for unsupported extensions.
    """
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"Metadata file not found: {path}")

    ext = p.suffix.lower()

    if ext == ".csv":
        return _read_csv_rows(p, delimiter=",")
    if ext == ".tsv":
        return _read_csv_rows(p, delimiter="\t")
    if ext == ".json":
        return _read_json_rows(p)

    raise ValueError(
        f"Unsupported metadata extension: {ext!r}. "
        "Supported: .csv, .tsv, .json"
    )


def _read_csv_rows(path: Path, delimiter: str) -> list[dict]:
    with path.open("r", newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh, delimiter=delimiter)
        return list(reader)


def _read_json_rows(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and "rows" in data:
        return data["rows"]
    raise ValueError(
        "JSON metadata must be a list[dict] or {'rows': list[dict]}."
    )


def load_contract_drafts(path: str) -> dict:
    """Load P14.1 contract_drafts.json. Used as inactive hints only."""
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(
            f"Contract drafts file not found: {path}. "
            "Run draft_dataset_label_contracts first or omit --contract-drafts."
        )
    return json.loads(p.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Audit logic
# ---------------------------------------------------------------------------

def _classify_column(col: str, values: list[str], n_rows: int) -> tuple[bool, bool, str | None, list[str]]:
    """Return (binary_candidate, likely_label_candidate, rejected_reason, warnings)."""
    col_lower = col.lower()
    warnings: list[str] = []
    n_nonempty = len(values)
    n_unique = len(set(values))

    if n_nonempty == 0:
        return False, False, "empty_column", []

    if n_unique == 1:
        return False, False, "single_value_only", [f"Column {col!r} has only one distinct value."]

    is_neg_hint = any(hint in col_lower for hint in _NEGATIVE_COLUMN_HINTS)
    if is_neg_hint:
        return False, False, "likely_free_text" if "notes" in col_lower or "text" in col_lower or "description" in col_lower or "comment" in col_lower or "narrative" in col_lower else "likely_file_path", []

    if n_unique > _MAX_UNIQUE_FOR_LABEL:
        avg_len = sum(len(v) for v in values) / max(len(values), 1)
        if avg_len > 20:
            return False, False, "likely_free_text", [f"Column {col!r} has {n_unique} unique values with long strings; likely free text."]
        return False, False, "too_many_unique_values", [f"Column {col!r} has {n_unique} unique values."]

    is_pos_hint = any(hint in col_lower for hint in _POSITIVE_COLUMN_HINTS)
    binary_candidate = n_unique >= _MIN_UNIQUE_FOR_BINARY and n_unique <= _MAX_UNIQUE_FOR_LABEL
    likely_label = is_pos_hint or binary_candidate

    if not likely_label:
        return False, False, "no_label_signal", []

    return binary_candidate, likely_label, None, warnings


def audit_metadata_values(metadata_rows: list[dict]) -> list[DS005620MetadataValueAuditRow]:
    """Produce per-column audit rows. Does not choose labels or infer targets."""
    if not metadata_rows:
        return []

    columns = list(metadata_rows[0].keys())
    n_rows = len(metadata_rows)
    result = []

    for col in columns:
        all_vals = [str(r.get(col, "")).strip() for r in metadata_rows]
        nonempty = [v for v in all_vals if v]
        unique_vals = sorted(set(nonempty))

        binary_cand, likely_label, rejected, warnings = _classify_column(
            col, nonempty, n_rows
        )

        result.append(DS005620MetadataValueAuditRow(
            column=col,
            n_rows=n_rows,
            n_nonempty=len(nonempty),
            n_unique=len(unique_vals),
            unique_values=unique_vals,
            binary_candidate=binary_cand,
            likely_label_candidate=likely_label,
            rejected_reason=rejected,
            warnings=warnings,
        ))

    return result


# ---------------------------------------------------------------------------
# Proposal logic
# ---------------------------------------------------------------------------

def _extract_ds005620_hints_from_draft(contract_drafts: dict) -> tuple[list[str], list[str], list[str]]:
    """Extract candidate columns and unresolved values from P14.1 drafts as hints only.

    Returns (candidate_cols, unresolved_values, warnings).
    Never activates. Never sets positive/negative values.
    """
    warnings: list[str] = []
    candidate_cols: list[str] = []
    unresolved: list[str] = []

    drafts = contract_drafts.get("drafts", [])
    if isinstance(drafts, list):
        for draft in drafts:
            if isinstance(draft, dict) and draft.get("dataset_id") == "DS005620":
                # Check for any attempt to mark activation
                status = draft.get("status", "")
                if "ready_to_activate" in status or "active" in status.lower():
                    warnings.append(
                        f"Contract draft has status {status!r} for DS005620; "
                        "downgraded to inactive hint — human review required."
                    )

                candidate_cols = [
                    c for c in draft.get("candidate_label_columns", [])
                    if isinstance(c, str)
                ]
                # unresolved_values are hints only; never move to pos/neg
                unresolved = [
                    v for v in draft.get("unresolved_values", [])
                    if isinstance(v, str)
                ]
                # Guard: if draft has non-empty positive/negative, downgrade
                if draft.get("positive_values") or draft.get("negative_values"):
                    warnings.append(
                        "Contract draft for DS005620 has non-empty positive_values/"
                        "negative_values; ignored — these require explicit human declaration."
                    )
                break

    return candidate_cols, unresolved, warnings


def _build_activation_blockers_list(
    metadata_rows: list[dict],
    audit_rows: list[DS005620MetadataValueAuditRow],
) -> list[str]:
    blockers = []
    if not metadata_rows:
        blockers.append("metadata_required")
    blockers.append("explicit_label_column_required")
    blockers.append("positive_values_required")
    blockers.append("negative_values_required")
    blockers.append("both_classes_required")
    blockers.append("human_review_required")
    blockers.append("semantic_justification_required")
    blockers.append("no_shortcut_inference_confirmation_required")
    blockers.append("separate_contract_activation_pr_required")
    return blockers


def prepare_ds005620_activation_proposal(
    metadata_rows: list[dict],
    contract_drafts: dict | None = None,
) -> DS005620ActivationResult:
    """Build the full P16 activation result.

    contract_activation_allowed is always False.
    positive_values and negative_values are always empty lists.
    candidate values go to unresolved_values only.
    """
    dataset_id = "DS005620"
    warnings: list[str] = []

    audit_rows = audit_metadata_values(metadata_rows)
    audit_dicts = [asdict(r) for r in audit_rows]

    # Candidate columns from audit
    candidate_cols = [
        r.column for r in audit_rows if r.likely_label_candidate
    ]

    # Unresolved values from audit (hints only)
    unresolved_from_audit: list[str] = []
    for r in audit_rows:
        if r.binary_candidate:
            unresolved_from_audit.extend(r.unique_values)

    # Incorporate P14.1 draft hints if supplied
    draft_cols: list[str] = []
    draft_unresolved: list[str] = []
    if contract_drafts is not None:
        draft_cols, draft_unresolved, draft_warnings = _extract_ds005620_hints_from_draft(
            contract_drafts
        )
        warnings.extend(draft_warnings)

    # Merge candidate columns preserving order, deduplicating
    merged_cols = list(dict.fromkeys(candidate_cols + draft_cols))
    merged_unresolved = list(dict.fromkeys(unresolved_from_audit + draft_unresolved))

    for r in audit_rows:
        warnings.extend(r.warnings)

    activation_blockers_list = _build_activation_blockers_list(metadata_rows, audit_rows)

    proposal = DS005620ActivationProposal(
        dataset_id=dataset_id,
        explicit_label_column=None,
        candidate_label_columns=merged_cols,
        unresolved_values=merged_unresolved,
        positive_values=[],
        negative_values=[],
        label_scope="window",
        join_keys=_DEFAULT_JOIN_KEYS[:],
        metadata_provenance="local_file_audit_only",
        semantic_justification_required=True,
        no_shortcut_inference_required=True,
        contract_activation_allowed=False,
        activation_blockers=activation_blockers_list,
        required_human_decisions=_REQUIRED_HUMAN_DECISIONS[:],
        guardrails=_DEFAULT_GUARDRAILS[:],
    )
    proposal_dict = asdict(proposal)

    human_review = build_human_review_packet_from_proposal(proposal)
    blockers = build_activation_blockers_from_proposal(proposal)
    omega = _build_omega_from_proposal(proposal)

    return DS005620ActivationResult(
        dataset_id=dataset_id,
        n_metadata_rows=len(metadata_rows),
        n_metadata_columns=len(metadata_rows[0]) if metadata_rows else 0,
        metadata_file_exists=len(metadata_rows) > 0,
        metadata_value_audit=audit_dicts,
        activation_proposal=proposal_dict,
        human_review_packet=human_review,
        activation_blockers=blockers,
        omega_event=omega,
        safe_claim=_SAFE_CLAIM,
        forbidden_claims=_FORBIDDEN_CLAIMS[:],
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Packet builders
# ---------------------------------------------------------------------------

def build_human_review_packet_from_proposal(proposal: DS005620ActivationProposal) -> dict:
    return {
        "dataset_id": proposal.dataset_id,
        "checklist": [
            "Confirm metadata provenance and file path.",
            "Select explicit_label_column from candidate_label_columns.",
            "Declare positive_values (non-ambiguous, semantically validated).",
            "Declare negative_values (non-ambiguous, semantically validated).",
            "Confirm join_keys are correct for the label_scope.",
            "Confirm label_scope (window / file / subject / session).",
            "Justify semantic mapping — why the values map to positive/negative.",
            "Confirm no shortcut inference is used (no filename/topology/artifact labels).",
            "Create separate contract-activation PR with all declarations.",
            "Peer-review and merge contract-activation PR before activating.",
        ],
        "required_decisions": proposal.required_human_decisions,
        "evidence_needed": [
            "Metadata file path and provenance",
            "Distinct label value table with counts",
            "Semantic mapping rationale",
            "Negative confirmation: no shortcut inference used",
        ],
        "reviewer_questions": [
            "Which column in the metadata contains the explicit label?",
            "Which values indicate the positive class?",
            "Which values indicate the negative class?",
            "Are there ambiguous or N/A values that must be excluded?",
            "What is the label_scope (window/file/subject/session)?",
            "Are the join_keys correct for aligning metadata to P9 features?",
            "Is the mapping semantically valid and free from shortcut inference?",
        ],
        "activation_allowed": False,
    }


def build_activation_blockers_from_proposal(proposal: DS005620ActivationProposal) -> dict:
    return {
        "dataset_id": proposal.dataset_id,
        "contract_activation_allowed": False,
        "blockers": proposal.activation_blockers,
        "gates": {
            "metadata_file_exists": proposal.metadata_provenance != "none",
            "explicit_label_column_declared": proposal.explicit_label_column is not None,
            "positive_values_declared": len(proposal.positive_values) > 0,
            "negative_values_declared": len(proposal.negative_values) > 0,
            "label_scope_declared": proposal.label_scope != "",
            "join_keys_declared": len(proposal.join_keys) > 0,
            "both_classes_present": False,
            "ambiguous_values_rejected": False,
            "human_review_required": True,
            "contract_activation_allowed": False,
        },
    }


def _build_omega_from_proposal(proposal: DS005620ActivationProposal) -> dict:
    _validate_safe_text(_SAFE_CLAIM)
    payload = f"ds005620_activation:{proposal.contract_activation_allowed}:{_SAFE_CLAIM}"
    return {
        "event_id": hashlib.sha256(payload.encode()).hexdigest()[:16],
        "event_type": "ds005620_contract_activation_audit",
        "dataset_id": proposal.dataset_id,
        "safe_claim": _SAFE_CLAIM,
        "contract_activation_allowed": False,
        "human_review_required": True,
        "forbidden_claims": _FORBIDDEN_CLAIMS[:],
    }


# ---------------------------------------------------------------------------
# Public bridge functions (for CLI and tests)
# ---------------------------------------------------------------------------

def build_human_review_packet(result: DS005620ActivationResult) -> dict:
    return result.human_review_packet


def build_activation_blockers(result: DS005620ActivationResult) -> dict:
    return result.activation_blockers


def build_ds005620_activation_omega_event(result: DS005620ActivationResult) -> dict:
    return result.omega_event


# ---------------------------------------------------------------------------
# Output writer
# ---------------------------------------------------------------------------

def write_ds005620_activation_outputs(
    result: DS005620ActivationResult,
    out_dir: str,
) -> dict[str, str]:
    """Write exactly 6 output files to out_dir."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    outputs: dict[str, str] = {}

    # 1. activation_proposal.json
    p = out / "activation_proposal.json"
    p.write_text(json.dumps(result.activation_proposal, indent=2), encoding="utf-8")
    outputs["activation_proposal"] = str(p)

    # 2. human_review_packet.json
    p = out / "human_review_packet.json"
    p.write_text(json.dumps(result.human_review_packet, indent=2), encoding="utf-8")
    outputs["human_review_packet"] = str(p)

    # 3. metadata_value_audit.csv
    p = out / "metadata_value_audit.csv"
    fieldnames = [
        "column", "n_rows", "n_nonempty", "n_unique",
        "unique_values", "binary_candidate", "likely_label_candidate",
        "rejected_reason", "warnings",
    ]
    with p.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in result.metadata_value_audit:
            writer.writerow({
                "column": row["column"],
                "n_rows": row["n_rows"],
                "n_nonempty": row["n_nonempty"],
                "n_unique": row["n_unique"],
                "unique_values": "|".join(row["unique_values"]),
                "binary_candidate": row["binary_candidate"],
                "likely_label_candidate": row["likely_label_candidate"],
                "rejected_reason": row.get("rejected_reason") or "",
                "warnings": "|".join(row.get("warnings", [])),
            })
    outputs["metadata_value_audit"] = str(p)

    # 4. activation_blockers.json
    p = out / "activation_blockers.json"
    p.write_text(json.dumps(result.activation_blockers, indent=2), encoding="utf-8")
    outputs["activation_blockers"] = str(p)

    # 5. omega_event.json
    p = out / "omega_event.json"
    p.write_text(json.dumps(result.omega_event, indent=2), encoding="utf-8")
    outputs["omega_event"] = str(p)

    # 6. report.md
    proposal = result.activation_proposal
    report_lines = [
        "# DS005620 Human-Reviewed Contract Activation Packet",
        "",
        "## Stage",
        "",
        "P16 — DS005620 human-reviewed label contract activation packet. "
        "Read-only metadata audit; no labels inferred, no targets fabricated, "
        "no contract activated.",
        "",
        "## Dataset",
        "",
        f"- dataset_id: {result.dataset_id}",
        f"- n_metadata_rows: {result.n_metadata_rows}",
        f"- n_metadata_columns: {result.n_metadata_columns}",
        f"- metadata_file_exists: {result.metadata_file_exists}",
        "",
        "## Metadata Audit",
        "",
    ]

    for row in result.metadata_value_audit:
        status = "binary_candidate" if row["binary_candidate"] else (
            "label_candidate" if row["likely_label_candidate"] else
            f"rejected ({row.get('rejected_reason', 'unknown')})"
        )
        report_lines.append(
            f"- `{row['column']}`: {row['n_unique']} unique values, status={status}"
        )

    report_lines += [
        "",
        "## Activation Proposal",
        "",
        f"- explicit_label_column: {proposal.get('explicit_label_column') or 'not declared'}",
        f"- candidate_label_columns: {proposal.get('candidate_label_columns', [])}",
        f"- unresolved_values: {proposal.get('unresolved_values', [])}",
        f"- positive_values: {proposal.get('positive_values', [])} (must be declared by human)",
        f"- negative_values: {proposal.get('negative_values', [])} (must be declared by human)",
        f"- label_scope: {proposal.get('label_scope', 'window')}",
        f"- join_keys: {proposal.get('join_keys', [])}",
        f"- contract_activation_allowed: {proposal.get('contract_activation_allowed', False)}",
        "",
        "## Human Review Packet",
        "",
        "A human reviewer must complete all items in the activation checklist:",
        "",
    ]

    for item in result.human_review_packet.get("checklist", []):
        report_lines.append(f"- [ ] {item}")

    report_lines += [
        "",
        "## Activation Blockers",
        "",
    ]
    for b in result.activation_blockers.get("blockers", []):
        report_lines.append(f"- {b}")

    report_lines += [
        "",
        "## Safe Claim",
        "",
        result.safe_claim,
        "",
        "## Forbidden Claims",
        "",
    ]
    for fc in result.forbidden_claims:
        report_lines.append(f"- {fc}")

    report_lines += [
        "",
        "## Next Required Step",
        "",
        "Open a separate contract-activation PR only after a human reviewer declares "
        "explicit_label_column, positive_values, negative_values, label_scope, join_keys, "
        "metadata provenance, and no-shortcut justification.",
        "",
        "This audit (P16) does not activate any contract. "
        "Do NOT merge a contract-activation PR without peer review.",
        "",
        "## Guardrails",
        "",
        "- No label inference from file names, topology, or artifacts.",
        "- No target fabrication.",
        "- sedated does not imply no_experience.",
        "- unresponsive does not imply unconscious.",
        "- No consciousness, self, soul, liberation, afterlife, or ontology proof claims.",
        "- contract_activation_allowed is always false in this audit.",
    ]

    report_text = "\n".join(report_lines) + "\n"
    _validate_safe_text(report_text)

    p = out / "report.md"
    p.write_text(report_text, encoding="utf-8")
    outputs["report"] = str(p)

    return outputs
