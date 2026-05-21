"""
DS005620 ontology evaluator (O3).

Reads P18.1/P18.2 mock-or-real execution artifacts, applies the ontology
bridge registry and evidence requirement matrix, and produces the seven
ontology evaluation outputs.

Engineering claims only. No empirical, mechanism, theory, or ontology
claims are promoted by this evaluator.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from sciencer_d.btc_icft.ontology.bridges import (
    load_bridge_registry,
    parse_bridges,
    summarize_bridge_status,
    validate_bridge_registry,
)
from sciencer_d.btc_icft.ontology.evidence import (
    load_evidence_requirement_matrix,
    validate_evidence_requirement_matrix,
)
from sciencer_d.btc_icft.ontology.promotion import (
    build_claim_scope_matrix,
    build_layer_claim,
    build_ontology_promotion_decision,
    determine_max_claim_scope,
    determine_promotion_state,
)
from sciencer_d.btc_icft.ontology.safe_language import (
    FORBIDDEN_ONTOLOGY_PHRASES,
    validate_json_safe_text,
    validate_safe_text,
)
from sciencer_d.btc_icft.ontology.schema import (
    AlternativeExplanation,
    ClaimScope,
    Falsifier,
    OntologyEvaluationResult,
    OntologyLayer,
    PromotionState,
)


_SAFE_CLAIM = (
    "Ontology evaluation constrains DS005620 benchmark outputs to explicit "
    "claim scopes and keeps substrate, theory, and ontology claims "
    "quarantined unless required independent evidence exists."
)


_FORBIDDEN_CLAIM_DISCLAIMERS = [
    "No metaphysical, soteriological, or experiential promotion.",
    "No automatic ontology promotion.",
    "No empirical promotion of Level M markers from mock runs.",
    "No empirical promotion of Level T topology from mock runs.",
    "No substrate claim without independent biophysical evidence.",
    "No theory promotion beyond theory_consistency.",
    "No ontology candidate promotion beyond quarantine.",
]


_MOCK_MODES = {"mock_e2e", "mock-e2e", "dry_run"}


def load_execution_summary(root: Path) -> dict:
    p = root / "ds005620_real_benchmark_execution.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def load_evidence_packet(root: Path) -> dict:
    p = root / "evidence_packet.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def load_omega_event(root: Path) -> dict:
    p = root / "omega_event.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def load_controls_if_present(controls_root: Optional[Path]) -> set[str]:
    """Return the set of control filenames present under controls_root."""
    if controls_root is None:
        return set()
    p = Path(controls_root)
    if not p.exists() or not p.is_dir():
        return set()
    found: set[str] = set()
    for f in p.iterdir():
        if f.is_file():
            found.add(f.name)
    return found


def inspect_available_artifacts(execution_root: Path) -> set[str]:
    """Walk the execution root and collect filenames present."""
    found: set[str] = set()
    if not execution_root.exists() or not execution_root.is_dir():
        return found
    for path in execution_root.rglob("*"):
        if path.is_file():
            found.add(path.name)
    return found


def _coerce_run_mode(execution: dict, override: Optional[str]) -> str:
    if override:
        return override
    mode = execution.get("mode") or "unknown"
    if mode in ("mock_e2e", "mock-e2e"):
        return "mock_e2e"
    return mode


def evaluate_ds005620_ontology_claims(
    execution_root: Path,
    controls_root: Optional[Path],
    bridge_registry: dict,
    evidence_matrix: dict,
    *,
    run_mode_override: Optional[str] = None,
    independent_dataset_present: bool = False,
    independent_mechanism_evidence_present: bool = False,
    human_review_completed: bool = False,
) -> OntologyEvaluationResult:
    execution = load_execution_summary(execution_root)
    evidence_packet = load_evidence_packet(execution_root)
    omega = load_omega_event(execution_root)

    run_mode = _coerce_run_mode(execution, run_mode_override)
    is_mock = run_mode in _MOCK_MODES

    available_artifacts = inspect_available_artifacts(execution_root)
    available_controls = load_controls_if_present(controls_root)

    max_scope = determine_max_claim_scope(
        run_mode,
        available_artifacts,
        available_controls,
        independent_dataset_present=independent_dataset_present,
        independent_mechanism_evidence_present=independent_mechanism_evidence_present,
        human_review_completed=human_review_completed,
    )
    promotion_state = determine_promotion_state(
        run_mode,
        available_artifacts,
        available_controls,
        independent_dataset_present=independent_dataset_present,
        independent_mechanism_evidence_present=independent_mechanism_evidence_present,
        human_review_completed=human_review_completed,
    )

    scope_matrix = build_claim_scope_matrix(
        run_mode,
        available_artifacts,
        available_controls,
        independent_dataset_present=independent_dataset_present,
        independent_mechanism_evidence_present=independent_mechanism_evidence_present,
        human_review_completed=human_review_completed,
    )

    # Build per-layer claims with current promotion status
    claims = [
        build_layer_claim(
            "D1",
            "Phenomenology / behavioral context",
            OntologyLayer.D_PHENOMENOLOGY,
            ClaimScope.ENGINEERING_RUNTIME,
            "Reviewed labels stand in for behavioral context for benchmark purposes only.",
            allowed=True,
            promotion_state=PromotionState.ENGINEERING_VALIDATED,
        ),
        build_layer_claim(
            "M1",
            "Marker association claim",
            OntologyLayer.M_MARKER,
            ClaimScope.MARKER_ASSOCIATION,
            "Level M markers may associate with reviewed labels under controls.",
            allowed=scope_matrix[ClaimScope.MARKER_ASSOCIATION]["allowed"],
            promotion_state=scope_matrix[ClaimScope.MARKER_ASSOCIATION]["max_state"],
            required_evidence=["features_m_signal_labeled.csv", "metrics_signal_mt.json"],
            required_controls=["leakage_report.json", "artifact_report.json"],
            blockers=scope_matrix[ClaimScope.MARKER_ASSOCIATION]["blockers"],
        ),
        build_layer_claim(
            "T1",
            "Topology residual claim",
            OntologyLayer.T_TOPOLOGY,
            ClaimScope.TOPOLOGY_RESIDUAL,
            "Topology telemetry may show residual predictive value beyond Level M markers.",
            allowed=scope_matrix[ClaimScope.TOPOLOGY_RESIDUAL]["allowed"],
            promotion_state=scope_matrix[ClaimScope.TOPOLOGY_RESIDUAL]["max_state"],
            required_evidence=["metrics_signal_mt.json", "nulls.json", "ablations.json"],
            required_controls=["leakage_report.json", "artifact_report.json"],
            blockers=scope_matrix[ClaimScope.TOPOLOGY_RESIDUAL]["blockers"],
        ),
        build_layer_claim(
            "C1",
            "Substrate mechanism candidate",
            OntologyLayer.C_SUBSTRATE,
            ClaimScope.MECHANISM_CANDIDATE,
            "A specific mechanism is proposed as a candidate, contingent on independent biophysical evidence.",
            allowed=scope_matrix[ClaimScope.MECHANISM_CANDIDATE]["allowed"],
            promotion_state=scope_matrix[ClaimScope.MECHANISM_CANDIDATE]["max_state"],
            required_evidence=["independent_mechanism_evidence_packet.json"],
            required_controls=["mechanism_controls.json"],
            blockers=scope_matrix[ClaimScope.MECHANISM_CANDIDATE]["blockers"],
        ),
        build_layer_claim(
            "Q1",
            "Theory consistency claim",
            OntologyLayer.Q_THEORY,
            ClaimScope.THEORY_CONSISTENCY,
            "Findings are discussed as theoretically consistent with the dynamical organization framework, not as confirmation.",
            allowed=scope_matrix[ClaimScope.THEORY_CONSISTENCY]["allowed"],
            promotion_state=scope_matrix[ClaimScope.THEORY_CONSISTENCY]["max_state"],
            blockers=scope_matrix[ClaimScope.THEORY_CONSISTENCY]["blockers"],
        ),
        build_layer_claim(
            "O1",
            "Ontology candidate quarantine",
            OntologyLayer.O_ONTOLOGY_CANDIDATE,
            ClaimScope.ONTOLOGY_CANDIDATE,
            "Ontology candidates remain quarantined; benchmark evidence cannot promote them.",
            allowed=False,
            promotion_state=PromotionState.ONTOLOGY_QUARANTINED,
            required_evidence=[
                "independent_dataset_replication.json",
                "independent_mechanism_evidence_packet.json",
                "alternative_explanations_report.json",
            ],
            required_controls=["cross_dataset_controls.json", "mechanism_controls.json"],
            blockers=scope_matrix[ClaimScope.ONTOLOGY_CANDIDATE]["blockers"],
        ),
    ]

    # Bridge statuses
    bridges = parse_bridges(bridge_registry)
    bridge_statuses = [
        summarize_bridge_status(b, available_artifacts, available_controls, run_mode)
        for b in bridges
    ]

    # Falsifier statuses (informational; not evaluated empirically by this layer)
    falsifier_statuses: list[Falsifier] = []
    for b in bridges:
        for fid, fdesc in enumerate(b.falsifiers):
            falsifier_statuses.append(
                Falsifier(
                    falsifier_id=f"{b.bridge_id}_F{fid+1}",
                    description=fdesc,
                    status="not_evaluated" if is_mock else "pending_evaluation",
                    required_artifacts=list(b.required_artifacts),
                )
            )

    # Alternative explanations status
    alternative_explanations: list[AlternativeExplanation] = []
    for b in bridges:
        for aid, adesc in enumerate(b.alternative_explanations):
            alternative_explanations.append(
                AlternativeExplanation(
                    alternative_id=f"{b.bridge_id}_A{aid+1}",
                    description=adesc,
                    status="not_evaluated" if is_mock else "pending_evaluation",
                    required_checks=list(b.required_controls),
                )
            )

    # Aggregate blockers
    blockers: list[str] = []
    if is_mock:
        blockers.append("run_mode_is_mock_e2e_blocks_empirical_promotion")
    if "features_m_signal_labeled.csv" not in available_artifacts:
        blockers.append("reviewed_label_artifact_missing")
    if not available_controls:
        blockers.append("controls_root_empty_or_missing")
    if not independent_dataset_present:
        blockers.append("independent_dataset_replication_missing")
    if not independent_mechanism_evidence_present:
        blockers.append("independent_mechanism_evidence_missing")
    if not human_review_completed:
        blockers.append("human_review_not_completed")

    omega_invariants = {
        "labels_inferred": bool(omega.get("labels_inferred", False)),
        "targets_fabricated": bool(omega.get("targets_fabricated", False)),
        "source_contracts_modified": bool(omega.get("source_contracts_modified", False)),
        "legacy_mt_real_modified": bool(omega.get("legacy_mt_real_modified", False)),
        "contracts_activated_by_executor": bool(omega.get("contracts_activated_by_executor", False)),
        "p11_promotion_gate_modified": bool(omega.get("p11_promotion_gate_modified", False)),
        "consciousness_claims_made": bool(omega.get("consciousness_claims_made", False)),
        "ontology_promotion_attempted": False,
        "metaphysical_claim_made": False,
        "empirical_promotion_from_mock": False,
    }

    result = OntologyEvaluationResult(
        dataset_id=str(execution.get("dataset_id", "DS005620")),
        run_mode=run_mode,
        max_claim_scope=max_scope,
        promotion_state=promotion_state,
        claims=claims,
        bridge_statuses=bridge_statuses,
        falsifier_statuses=falsifier_statuses,
        alternative_explanations=alternative_explanations,
        blockers=blockers,
        warnings=[],
        safe_claim=_SAFE_CLAIM,
        forbidden_claims=list(_FORBIDDEN_CLAIM_DISCLAIMERS),
        omega_invariants=omega_invariants,
        ontology_claim_status=PromotionState.ONTOLOGY_QUARANTINED,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )
    return result


def _render_report_md(
    result: OntologyEvaluationResult,
    promotion_decision: dict,
    scope_matrix: dict,
) -> str:
    lines: list[str] = []
    lines.append("# DS005620 Ontology Claim Evaluation")
    lines.append("")
    lines.append(f"**Dataset:** {result.dataset_id}")
    lines.append(f"**Run mode:** {result.run_mode}")
    lines.append(f"**Max claim scope:** `{result.max_claim_scope}`")
    lines.append(f"**Promotion state:** `{result.promotion_state}`")
    lines.append(f"**Ontology claim status:** `{result.ontology_claim_status}`")
    lines.append("")
    lines.append("## Safe Claim")
    lines.append("")
    lines.append(result.safe_claim)
    lines.append("")
    lines.append("## Forbidden Claims (none of these are made)")
    lines.append("")
    for fc in result.forbidden_claims:
        lines.append(f"- {fc}")
    lines.append("")
    lines.append("## Per-Layer Claims")
    lines.append("")
    for c in result.claims:
        lines.append(f"### {c.claim_id} — {c.title}")
        lines.append("")
        lines.append(f"- Layer: `{c.layer}`")
        lines.append(f"- Scope: `{c.scope}`")
        lines.append(f"- Allowed at current evidence: {c.allowed}")
        lines.append(f"- Promotion state: `{c.promotion_state}`")
        lines.append(f"- Statement: {c.statement}")
        if c.blockers:
            lines.append("- Blockers:")
            for b in c.blockers:
                lines.append(f"  - {b}")
        lines.append("")
    lines.append("## Bridge Claim Status")
    lines.append("")
    for bs in result.bridge_statuses:
        lines.append(f"- **{bs['bridge_id']}** ({bs['source_layer']} -> {bs['target_layer']}): `{bs['status']}` — {bs['reason']}")
    lines.append("")
    lines.append("## Claim Scope Matrix")
    lines.append("")
    for scope, info in scope_matrix.items():
        lines.append(f"- `{scope}`: allowed={info['allowed']}, max_state=`{info['max_state']}`")
        if info.get("blockers"):
            for b in info["blockers"]:
                lines.append(f"  - blocker: {b}")
    lines.append("")
    lines.append("## Ontology Promotion Decision")
    lines.append("")
    lines.append(f"- max_claim_scope: `{promotion_decision['max_claim_scope']}`")
    lines.append(f"- promotion_state: `{promotion_decision['promotion_state']}`")
    lines.append(f"- ontology_claim_status: `{promotion_decision['ontology_claim_status']}`")
    lines.append(f"- empirical_marker_promotion: {promotion_decision['empirical_marker_promotion']}")
    lines.append(f"- empirical_topology_promotion: {promotion_decision['empirical_topology_promotion']}")
    lines.append(f"- mechanism_promotion: {promotion_decision['mechanism_promotion']}")
    lines.append(f"- ontology_promotion: {promotion_decision['ontology_promotion']}")
    lines.append(f"- metaphysical_promotion: {promotion_decision['metaphysical_promotion']}")
    lines.append("")
    lines.append("## Omega Invariants (all must be false)")
    lines.append("")
    for k, v in result.omega_invariants.items():
        lines.append(f"- `{k}`: {v}")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("_O1-O3 ontology evaluation — no pipeline stages executed, no data downloaded, no contracts activated._")
    return "\n".join(lines)


def write_ontology_evaluation_outputs(
    result: OntologyEvaluationResult,
    scope_matrix: dict,
    out_dir: Path,
    *,
    bridge_registry_path: Optional[str] = None,
    evidence_matrix_path: Optional[str] = None,
) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)

    eval_dict = result.to_dict()
    eval_dict["sources"] = {
        "bridge_registry_path": bridge_registry_path,
        "evidence_matrix_path": evidence_matrix_path,
    }
    eval_path = out_dir / "ontology_claim_evaluation.json"
    eval_path.write_text(json.dumps(eval_dict, indent=2), encoding="utf-8")

    scope_path = out_dir / "claim_scope_matrix.json"
    scope_path.write_text(json.dumps(scope_matrix, indent=2), encoding="utf-8")

    bridges_path = out_dir / "bridge_claim_status.json"
    bridges_path.write_text(
        json.dumps({"bridge_statuses": result.bridge_statuses}, indent=2),
        encoding="utf-8",
    )

    falsifier_path = out_dir / "falsifier_status.json"
    falsifier_path.write_text(
        json.dumps({"falsifiers": [f.to_dict() for f in result.falsifier_statuses]}, indent=2),
        encoding="utf-8",
    )

    alt_path = out_dir / "alternative_explanations.json"
    alt_path.write_text(
        json.dumps(
            {"alternative_explanations": [a.to_dict() for a in result.alternative_explanations]},
            indent=2,
        ),
        encoding="utf-8",
    )

    promotion_decision = build_ontology_promotion_decision(
        dataset_id=result.dataset_id,
        run_mode=result.run_mode,
        max_claim_scope=result.max_claim_scope,
        promotion_state=result.promotion_state,
        blockers=result.blockers,
    )
    promotion_path = out_dir / "ontology_promotion_decision.json"
    promotion_path.write_text(json.dumps(promotion_decision, indent=2), encoding="utf-8")

    omega_event = {
        "event_id": _omega_event_id(result),
        "event_type": "ds005620_ontology_evaluation",
        "dataset_id": result.dataset_id,
        "run_mode": result.run_mode,
        "max_claim_scope": result.max_claim_scope,
        "promotion_state": result.promotion_state,
        "ontology_claim_status": result.ontology_claim_status,
        "omega_invariants": result.omega_invariants,
        "safe_claim": result.safe_claim,
        "forbidden_claims": result.forbidden_claims,
        "generated_at": result.generated_at,
    }
    omega_path = out_dir / "omega_event.json"
    omega_path.write_text(json.dumps(omega_event, indent=2), encoding="utf-8")

    report_md = _render_report_md(result, promotion_decision, scope_matrix)
    report_path = out_dir / "report.md"
    report_path.write_text(report_md, encoding="utf-8")

    return {
        "ontology_claim_evaluation.json": str(eval_path),
        "claim_scope_matrix.json": str(scope_path),
        "bridge_claim_status.json": str(bridges_path),
        "falsifier_status.json": str(falsifier_path),
        "alternative_explanations.json": str(alt_path),
        "ontology_promotion_decision.json": str(promotion_path),
        "omega_event.json": str(omega_path),
        "report.md": str(report_path),
    }


def _omega_event_id(result: OntologyEvaluationResult) -> str:
    import hashlib

    raw = json.dumps(
        {
            "dataset_id": result.dataset_id,
            "run_mode": result.run_mode,
            "max_claim_scope": result.max_claim_scope,
            "promotion_state": result.promotion_state,
            "ts": result.generated_at,
        },
        sort_keys=True,
    )
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def run_evaluation(
    execution_root: str,
    controls_root: Optional[str],
    out_dir: str,
    *,
    bridge_registry_path: str,
    evidence_matrix_path: str,
    evidence_packet_path: Optional[str] = None,
    run_mode_override: Optional[str] = None,
    independent_dataset_present: bool = False,
    independent_mechanism_evidence_present: bool = False,
    human_review_completed: bool = False,
) -> dict[str, str]:
    bridge_registry = load_bridge_registry(bridge_registry_path)
    bridge_errors = validate_bridge_registry(bridge_registry)
    if bridge_errors:
        raise ValueError(f"invalid bridge registry: {bridge_errors}")

    evidence_matrix = load_evidence_requirement_matrix(evidence_matrix_path)
    matrix_errors = validate_evidence_requirement_matrix(evidence_matrix)
    if matrix_errors:
        raise ValueError(f"invalid evidence matrix: {matrix_errors}")

    result = evaluate_ds005620_ontology_claims(
        execution_root=Path(execution_root),
        controls_root=Path(controls_root) if controls_root else None,
        bridge_registry=bridge_registry,
        evidence_matrix=evidence_matrix,
        run_mode_override=run_mode_override,
        independent_dataset_present=independent_dataset_present,
        independent_mechanism_evidence_present=independent_mechanism_evidence_present,
        human_review_completed=human_review_completed,
    )

    scope_matrix = build_claim_scope_matrix(
        result.run_mode,
        inspect_available_artifacts(Path(execution_root)),
        load_controls_if_present(Path(controls_root) if controls_root else None),
        independent_dataset_present=independent_dataset_present,
        independent_mechanism_evidence_present=independent_mechanism_evidence_present,
        human_review_completed=human_review_completed,
    )

    paths = write_ontology_evaluation_outputs(
        result,
        scope_matrix,
        Path(out_dir),
        bridge_registry_path=bridge_registry_path,
        evidence_matrix_path=evidence_matrix_path,
    )

    # Self-check: scan all written outputs for forbidden phrases.
    for name, path in paths.items():
        text = Path(path).read_text(encoding="utf-8")
        hits = validate_safe_text(text)
        if hits:
            raise RuntimeError(
                f"forbidden phrase(s) {hits!r} found in generated output {name}"
            )
    return paths
