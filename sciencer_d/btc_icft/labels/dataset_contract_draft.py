from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
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
_DEFAULT_JOIN_KEYS = ["dataset_id", "row_id", "source_file", "window_id", "window_start_s", "window_end_s", "sample_start", "sample_end"]
_REQUIRED_DECISIONS = [
    "choose explicit_label_column", "declare positive_values", "declare negative_values",
    "declare label_scope", "verify join_keys", "verify no semantic shortcut is used",
    "approve contract activation in a separate PR",
]
_DEFAULT_GUARDRAILS = [
    "no_label_inference", "no_target_fabrication", "no_contract_activation_without_human_review",
    "no_sedated_to_no_experience", "no_unresponsive_to_unconscious", "no_ontology_claims",
    "no_soul_afterlife_claims", "no_liberation_claims",
]


@dataclass
class DatasetLabelContractDraft:
    dataset_id: str
    title: str
    status: str
    source_adapter_status: str
    explicit_label_column: str | None
    candidate_label_columns: list[str]
    label_scope: str
    join_keys: list[str]
    positive_values: list[str]
    negative_values: list[str]
    unresolved_values: list[str]
    activation_blockers: list[str]
    required_human_decisions: list[str]
    caveats: list[str]
    guardrails: list[str]


@dataclass
class ContractDraftResult:
    n_datasets: int
    n_drafts: int
    n_ready_for_human_review: int
    drafts: list[dict]
    review_checklists: list[dict]
    summary: dict
    omega_event: dict
    safe_claim: str
    forbidden_claims: list[str]
    warnings: list[str]


def _validate_safe_text(text: str) -> None:
    low = text.lower()
    for phrase in _BANNED_PHRASES:
        if phrase in low:
            raise ValueError(f"Banned phrase detected: {phrase}")


def load_adapter_readiness_summary(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_dataset_adapter_plan(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def discover_adapter_plan_files(readiness_dir: str) -> list[str]:
    out = []
    for p in sorted(Path(readiness_dir).glob("*.json")):
        if p.name in {"adapter_readiness_summary.json", "omega_event.json"}:
            continue
        d = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(d, dict) and ("dataset_id" in d or "readiness_status" in d or "adapter_spec" in d):
            out.append(str(p))
    return out


def draft_contract_from_adapter_plan(dataset_id: str, adapter_plan: dict) -> DatasetLabelContractDraft:
    status = adapter_plan.get("readiness_status", "planning_required")
    best = adapter_plan.get("best_probe") or {}
    cols = list(dict.fromkeys(best.get("candidate_label_columns", []) or adapter_plan.get("candidate_label_columns", [])))
    values = []
    uniq = best.get("unique_values", {})
    for k in cols:
        values.extend([str(v) for v in uniq.get(k, [])])
    values = list(dict.fromkeys(values))
    blockers = []
    if status in {"metadata_file_not_found", "metadata_empty_or_unreadable"}:
        draft_status = "draft_blocked_no_metadata"; blockers.append("metadata_required")
    elif status == "no_candidate_label_column":
        draft_status = "draft_blocked_no_candidate_column"; blockers.append("explicit_label_column_required")
    elif status == "insufficient_label_values":
        draft_status = "draft_blocked_insufficient_values"
    elif status == "needs_explicit_mapping":
        draft_status = "draft_blocked_needs_explicit_mapping"
    else:
        draft_status = "draft_inactive_human_review_required"
    if len(cols) > 1:
        blockers.append("human_must_choose_explicit_label_column")
    if values:
        blockers.append("human_must_declare_positive_and_negative_values")
    blockers.append("human_must_verify_join_keys")
    return DatasetLabelContractDraft(
        dataset_id=dataset_id,
        title=f"Dataset contract draft for {dataset_id}",
        status=draft_status,
        source_adapter_status=status,
        explicit_label_column=cols[0] if cols else None,
        candidate_label_columns=cols,
        label_scope="window",
        join_keys=_DEFAULT_JOIN_KEYS[:],
        positive_values=[],
        negative_values=[],
        unresolved_values=values,
        activation_blockers=list(dict.fromkeys(blockers)),
        required_human_decisions=_REQUIRED_DECISIONS[:],
        caveats=["Inactive draft only; human review required before any contract activation."],
        guardrails=_DEFAULT_GUARDRAILS[:],
    )


def build_contract_draft_review_checklist(draft: DatasetLabelContractDraft) -> dict:
    return {
        "dataset_id": draft.dataset_id,
        "checklist": [
            "Confirm metadata provenance.", "Select explicit label column.",
            "Declare positive and negative values.", "Validate join keys and scope.",
        ],
        "required_decisions": draft.required_human_decisions,
        "evidence_needed": ["Metadata file path", "Distinct label value table", "Mapping rationale"],
        "activation_allowed": False,
    }


def build_contract_draft_omega_event(result: ContractDraftResult) -> dict:
    _validate_safe_text(result.safe_claim)
    payload = f"{result.n_drafts}:{result.safe_claim}"
    return {
        "event_id": hashlib.sha256(payload.encode()).hexdigest()[:16],
        "event_type": "dataset_label_contract_drafts",
        "n_drafts": result.n_drafts,
        "safe_claim": result.safe_claim,
        "forbidden_claims": result.forbidden_claims,
    }


def draft_contracts_from_readiness_dir(readiness_dir: str) -> ContractDraftResult:
    rd = Path(readiness_dir)
    summary_path = rd / "adapter_readiness_summary.json"
    if not rd.exists() or not summary_path.exists():
        raise FileNotFoundError("P14 adapter readiness outputs are required. Run plan_dataset_label_adapters first or use --mock-fixture.")
    summary = load_adapter_readiness_summary(str(summary_path))
    drafts = []
    if isinstance(summary.get("per_dataset"), dict):
        for ds, plan in summary["per_dataset"].items():
            drafts.append(asdict(draft_contract_from_adapter_plan(ds, plan)))
    for f in discover_adapter_plan_files(readiness_dir):
        d = load_dataset_adapter_plan(f)
        ds = d.get("dataset_id")
        if ds and not any(x["dataset_id"] == ds for x in drafts):
            drafts.append(asdict(draft_contract_from_adapter_plan(ds, d)))
    checklists = [build_contract_draft_review_checklist(DatasetLabelContractDraft(**d)) for d in drafts]
    statuses = {}
    for d in drafts:
        statuses[d["status"]] = statuses.get(d["status"], 0) + 1
    safe_claim = "Dataset label adapter readiness was converted into inactive P12 contract drafts for human review without inferring labels or targets."
    forbidden = ["No consciousness proof.", "No self or soul claim.", "No liberation or enlightenment claim.", "No afterlife claim.", "No ontology proof.", "No label inference.", "No target fabrication.", "No contract activation.", "No sedated/no_experience shortcut.", "No unresponsive/unconscious shortcut."]
    res = ContractDraftResult(len(drafts), len(drafts), statuses.get("draft_inactive_human_review_required", 0), drafts, checklists, {"n_datasets": len(drafts), "n_drafts": len(drafts), "n_ready_for_human_review": statuses.get("draft_inactive_human_review_required", 0), "statuses": statuses, "datasets": [d["dataset_id"] for d in drafts], "warnings": []}, {}, safe_claim, forbidden, [])
    res.omega_event = build_contract_draft_omega_event(res)
    return res


def write_contract_draft_outputs(result: ContractDraftResult, out_dir: str) -> dict[str, str]:
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    outputs = {}
    p = out / "contract_draft_summary.json"; p.write_text(json.dumps(result.summary, indent=2), encoding="utf-8"); outputs[p.name] = str(p)
    p = out / "contract_drafts.json"; p.write_text(json.dumps({"drafts": result.drafts}, indent=2), encoding="utf-8"); outputs[p.name] = str(p)
    p = out / "human_review_checklists.json"; p.write_text(json.dumps(result.review_checklists, indent=2), encoding="utf-8"); outputs[p.name] = str(p)
    p = out / "activation_blockers.json"; p.write_text(json.dumps([{"dataset_id": d["dataset_id"], "activation_blockers": d["activation_blockers"]} for d in result.drafts], indent=2), encoding="utf-8"); outputs[p.name] = str(p)
    p = out / "omega_event.json"; p.write_text(json.dumps(result.omega_event, indent=2), encoding="utf-8"); outputs[p.name] = str(p)
    report = "# Dataset Label Contract Drafts\n\n## Stage\nInactive P12 contract draft generation from adapter readiness.\n\n## Input adapter readiness\n- datasets: {}\n\n## Drafts produced\n- n_drafts: {}\n\n## Human review requirements\n- All drafts are inactive and require explicit human declaration.\n\n## Activation blockers\n{}\n\n## Safe claim\n{}\n\n## Forbidden claims\n{}\n\n## Next required step\nA human reviewer must declare positive_values, negative_values, label_scope, and join_keys in a separate contract-activation PR before targets can be emitted.\n".format(result.summary.get("n_datasets"), result.summary.get("n_drafts"), "\n".join(f"- {d['dataset_id']}: {', '.join(d['activation_blockers'])}" for d in result.drafts), result.safe_claim, "\n".join(f"- {x}" for x in result.forbidden_claims))
    _validate_safe_text(report)
    p = out / "report.md"; p.write_text(report, encoding="utf-8"); outputs[p.name] = str(p)
    return outputs
