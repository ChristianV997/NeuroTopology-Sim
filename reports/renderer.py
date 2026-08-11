"""Deterministic Markdown renderer for EvidenceReportV1.

No LLM call, no randomness, no wall-clock-dependent formatting beyond the
report's own `created_at` field (already fixed at build time) -- rendering
the same EvidenceReportV1 twice always produces byte-identical Markdown.
"""
from __future__ import annotations

from typing import Any

TEMPLATE_VERSION_LABEL = "reports.renderer markdown template v1"


def _bullet_list(items: list[str]) -> str:
    if not items:
        return "_None recorded._\n"
    return "\n".join(f"- {item}" for item in items) + "\n"


def _kv_table(rows: list[tuple[str, Any]]) -> str:
    lines = ["| Field | Value |", "|---|---|"]
    for key, value in rows:
        lines.append(f"| {key} | {value} |")
    return "\n".join(lines) + "\n"


def _status_table(title: str, counts: dict[str, int]) -> str:
    lines = [f"**{title}**", "", "| Status | Count |", "|---|---|"]
    for key in sorted(counts):
        lines.append(f"| {key} | {counts[key]} |")
    return "\n".join(lines) + "\n"


def render_markdown(report: Any) -> str:
    lines: list[str] = []

    # 1. Title and status
    lines.append(f"# {report.report_title or 'Governed Evidence Report'}")
    lines.append("")
    bundle_valid = report.validation_summary.get("bundle_valid")
    status_label = "VALID" if bundle_valid else "VALIDATION ERRORS PRESENT"
    lines.append(f"**Report status:** {status_label}  ")
    lines.append(f"**Report ID:** `{report.report_id}`  ")
    lines.append(f"**Source bundle ID:** `{report.bundle_id}`  ")
    lines.append(f"**Dataset:** `{report.dataset_id}`  ")
    lines.append(f"**Generated:** {report.created_at}  ")
    lines.append(f"**Repository commit:** `{report.repo_commit or 'unknown'}`")
    lines.append("")

    # 2. Executive summary
    lines.append("## Executive Summary")
    lines.append("")
    tx = report.transition_summary or {}
    ps = report.phase_space_summary or {}
    lines.append(
        f"This report deterministically summarizes an existing governed "
        f"evidence bundle for dataset `{report.dataset_id}` "
        f"(requested use: `{report.requested_use}`). It references "
        f"{tx.get('count', 0)} transition artifact(s) and "
        f"{ps.get('count', 0)} operational phase-space coordinate(s). "
        f"It is an exploratory-metric summary, not a theory result, and "
        f"generates no new scientific claim."
    )
    lines.append("")

    # 3. Source artifact and registry authorization
    lines.append("## Source Artifact and Registry Authorization")
    lines.append("")
    sa = report.source_artifacts or {}
    lines.append(_kv_table([
        ("Bundle path", f"`{sa.get('bundle_path')}`"),
        ("Artifact IDs", ", ".join(sa.get("artifact_ids") or []) or "_none_"),
        ("Registry path", f"`{report.registry_summary.get('registry_path')}`" if report.registry_summary.get("registry_path") else "_not used (--no-registry legacy mode)_"),
        ("Requested use", f"`{report.requested_use}`"),
    ]))
    lines.append("")
    lines.append("**Registry decisions:**")
    lines.append("")
    decisions = report.registry_summary.get("decisions") or []
    if decisions:
        lines.append("| ID | Kind | Requested use | Allowed | Reason |")
        lines.append("|---|---|---|---|---|")
        for d in decisions:
            lines.append(
                f"| `{d.get('id')}` | {d.get('kind')} | `{d.get('requested_use')}` | "
                f"{d.get('allowed')} | {d.get('reason')} |"
            )
        lines.append("")
    else:
        lines.append("_No registry decisions recorded (legacy `--no-registry` build)._")
        lines.append("")

    # 4. Dataset/artifact role and contamination status
    lines.append("## Dataset/Artifact Role and Contamination Status")
    lines.append("")
    cs = report.contamination_summary or {}
    updates = cs.get("updates") or []
    lines.append(f"Contamination updates applied by this bundle's build: {cs.get('n_updates', 0)}.")
    lines.append("")
    if updates:
        lines.append("| ID | Kind | Seen by | Note |")
        lines.append("|---|---|---|---|")
        for u in updates:
            lines.append(f"| `{u.get('id')}` | {u.get('kind')} | {u.get('seen_by')} | {u.get('note')} |")
        lines.append("")
    else:
        lines.append("_No contamination (mark-seen) updates were applied for this bundle build._")
        lines.append("")

    # 5. Transition records generated
    lines.append("## Transition Records Generated")
    lines.append("")
    lines.append(_kv_table([
        ("Transition artifact count", tx.get("count", 0)),
        ("Record levels", ", ".join(tx.get("record_levels") or []) or "_none_"),
        ("Feature set ID(s)", ", ".join(tx.get("feature_set_ids") or []) or "_none recorded_"),
        ("Feature families", ", ".join(tx.get("feature_families") or []) or "_none_"),
    ]))
    lines.append("")

    # 6. Phase-space coordinates generated
    lines.append("## Phase-Space Coordinates Generated")
    lines.append("")
    if ps.get("count", 0) > 0:
        lines.append(_status_table("Coordinate status counts", ps.get("status_counts", {})))
        lines.append("")
        lines.append(_status_table("Coordinate confidence counts", ps.get("confidence_counts", {})))
        lines.append("")
    else:
        lines.append("_No phase-space coordinates were requested or generated for this bundle._")
        lines.append("")

    # 7. Supported axes and insufficient-data axes
    lines.append("## Supported Axes and Insufficient-Data Axes")
    lines.append("")
    lines.append("**Axes with an estimated operational coordinate:**")
    lines.append("")
    lines.append(_bullet_list(ps.get("axes_estimated") or []))
    lines.append("**Axes with insufficient data (no estimate produced):**")
    lines.append("")
    lines.append(_bullet_list(ps.get("axes_insufficient_data") or []))

    # 8. Null-control summary
    lines.append("## Null-Control Summary")
    lines.append("")
    ncs = report.null_control_summary or {}
    lines.append(f"**Status:** `{ncs.get('status', 'not_provided')}`")
    lines.append("")
    if ncs.get("note"):
        lines.append(str(ncs["note"]))
        lines.append("")
    per_transition = ncs.get("per_transition") or {}
    if per_transition:
        lines.append("| Transition ID | Null-control status |")
        lines.append("|---|---|")
        for tid in sorted(per_transition):
            lines.append(f"| `{tid}` | {per_transition[tid]} |")
        lines.append("")

    # 9. Claim scope and evidence level
    lines.append("## Claim Scope and Evidence Level")
    lines.append("")
    css = report.claim_scope_summary or {}
    els = report.evidence_level_summary or {}
    lines.append(_kv_table([
        ("Claim scope ceiling", f"`{css.get('claim_scope_ceiling')}`"),
        ("Generated claim scope", f"`{css.get('generated_claim_scope')}`"),
        ("Evidence level ceiling", f"`{els.get('evidence_level_ceiling')}`"),
        ("Generated evidence level(s)", ", ".join(f"`{lvl}`" for lvl in (els.get("generated_evidence_levels") or [])) or "_none_"),
    ]))
    lines.append("")
    lines.append(
        "The generated claim scope and evidence level(s) above never exceed "
        "their respective ceiling; this is enforced by "
        "`EvidenceBundleV1.validate()` at build time and re-checked by "
        "`EvidenceReportV1.validate()` at report time."
    )
    lines.append("")

    # 10. Validation summary
    lines.append("## Validation Summary")
    lines.append("")
    vs = report.validation_summary or {}
    lines.append(f"**Source bundle valid:** {vs.get('bundle_valid')}")
    lines.append("")
    bundle_errors = vs.get("bundle_validation_errors") or []
    if bundle_errors:
        lines.append("**Bundle validation errors:**")
        lines.append("")
        lines.append(_bullet_list(bundle_errors))
    else:
        lines.append("_No bundle validation errors were recorded at report build time._")
        lines.append("")

    # 11. Limitations
    lines.append("## Limitations")
    lines.append("")
    lines.append(_bullet_list(report.limitations or []))

    # 12. Explicitly blocked interpretations
    lines.append("## Explicitly Blocked Interpretations")
    lines.append("")
    lines.append(_bullet_list(report.blocked_claims or []))

    # 13. Reproducibility commands
    lines.append("## Reproducibility Commands")
    lines.append("")
    lines.append("```bash")
    for cmd in report.reproducibility_commands or []:
        lines.append(cmd)
    lines.append("```")
    lines.append("")

    # 14. Generated artifact manifest
    lines.append("## Generated Artifact Manifest")
    lines.append("")
    lines.append(_bullet_list(report.generated_files or ["_(populated after this report is written to disk)_"]))

    # 15. Future work / next required validation
    lines.append("## Future Work / Next Required Validation")
    lines.append("")
    lines.append(
        "This report does not implement, and should not be read as implying, "
        "a Theory Competition Engine, Koopman/DMD analysis, Counterfactual "
        "Reachable Sets, a Phenomenology parser, a Holo-Atlas interpreter, or "
        "a Consciousness Atlas. Any future comparison across bundles, "
        "datasets, or theories should consume `EvidenceBundleV1`/`EvidenceReportV1` "
        "artifacts rather than raw transition/phase-space output directories, "
        "so registry authorization and contamination state are never silently "
        "dropped."
    )
    lines.append("")

    lines.append(f"_Rendered by {TEMPLATE_VERSION_LABEL}._")
    lines.append("")

    return "\n".join(lines)
