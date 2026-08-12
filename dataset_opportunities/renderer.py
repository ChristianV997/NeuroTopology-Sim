"""Deterministic Markdown renderer for a `DatasetOpportunityBatchV1` +
optional `DatasetOpportunityPlanV1` pair. Stdlib-only, no LLM call, no
randomness -- rendering the same batch/plan twice produces byte-identical
Markdown. Every free-text field is scanned for banned phrases before being
written; `render_opportunity_summary` raises rather than writes if any are
found.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional, Union

from dataset_opportunities.opportunity_batch import DatasetOpportunityBatchV1
from dataset_opportunities.planner import DatasetOpportunityPlanV1
from dataset_opportunities.validation import DatasetOpportunityStoreError, scan_text_for_banned_phrases

_HEADER = "# Dataset Opportunity Scouting Report\n"

_DISCLAIMER = (
    "> This report ranks metadata-only scouting opportunities. It does not create evidence. "
    "Real analysis requires separate acquisition, explicit mappings, bounded feature recipes, "
    "and governed report generation. Nothing in this report is a clinical, diagnostic, or "
    "spiritual-attainment claim."
)


def _table(headers: list[str], rows: list[list[str]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(str(v) for v in row) + " |")
    return "\n".join(lines)


def render_opportunity_summary(
    batch: DatasetOpportunityBatchV1,
    plan: Optional[DatasetOpportunityPlanV1] = None,
    *,
    reproducibility_commands: Optional[list[str]] = None,
) -> str:
    batch_errs = batch.validate()
    if batch_errs:
        raise DatasetOpportunityStoreError(f"batch failed validation: {'; '.join(batch_errs)}")
    if plan is not None:
        plan_errs = plan.validate()
        if plan_errs:
            raise DatasetOpportunityStoreError(f"plan failed validation: {'; '.join(plan_errs)}")

    sections: list[str] = [_HEADER, _DISCLAIMER, ""]

    sections.append("## Query summary")
    sections.append(f"- source_catalog: `{batch.source_catalog}`")
    sections.append(f"- query_summary: {batch.query_summary or '(none)'}")
    sections.append(f"- generated_at: {batch.generated_at}")
    sections.append(f"- batch_id: `{batch.batch_id}`")
    sections.append("")

    sections.append("## Candidate counts")
    sections.append(f"- total_candidates_seen: {batch.total_candidates_seen}")
    sections.append(f"- total_opportunities_ranked: {batch.total_opportunities_ranked}")
    sections.append(f"- total_rejected: {len(batch.rejected_opportunities)}")
    sections.append("")

    sections.append("## Top opportunities")
    if batch.ranked_opportunities:
        rows = [
            [
                o.get("source_dataset_id", ""), o.get("dataset_name", ""), o.get("modality", ""),
                o.get("total_score", ""), ", ".join(o.get("recommended_next_actions") or []),
            ]
            for o in batch.ranked_opportunities
        ]
        sections.append(_table(["dataset_id", "name", "modality", "total_score", "recommended_next_actions"], rows))
    else:
        sections.append("(none ranked)")
    sections.append("")

    sections.append("## Recommended next actions")
    sections.append(", ".join(batch.top_recommended_actions) or "(none)")
    sections.append("")

    sections.append("## Dataset risks")
    risk_rows = [[o.get("source_dataset_id", ""), ", ".join(o.get("risk_flags") or [])] for o in batch.ranked_opportunities if o.get("risk_flags")]
    sections.append(_table(["dataset_id", "risk_flags"], risk_rows) if risk_rows else "(no risk flags recorded)")
    sections.append("")

    sections.append("## Acquisition planning candidates")
    acq = plan.planned_acquisition_candidates if plan else []
    sections.append(
        _table(["dataset_id", "suggested_requested_action", "safety_notes"],
               [[a["source_dataset_id"], a["suggested_requested_action"], a["safety_notes"]] for a in acq])
        if acq else "(none proposed)"
    )
    sections.append("")

    sections.append("## Benchmark-pack proposal candidates")
    bench = plan.planned_benchmark_pack_candidates if plan else []
    sections.append(
        _table(["dataset_id", "proposed_input_mode", "missing_requirements"],
               [[b["source_dataset_id"], b["proposed_input_mode"], ", ".join(b["missing_requirements"])] for b in bench])
        if bench else "(none proposed)"
    )
    sections.append("")

    sections.append("## Literature-review tasks")
    lit = plan.planned_literature_review_tasks if plan else []
    sections.append(
        _table(["dataset_id", "topic", "search_terms"],
               [[t["source_dataset_id"], t["topic"], ", ".join(t["search_terms"])] for t in lit])
        if lit else "(none proposed)"
    )
    sections.append("")

    sections.append("## Researcher-outreach candidates (require human review)")
    outreach = plan.planned_outreach_candidates if plan else []
    sections.append(
        _table(["dataset_id", "identifier", "why_relevant", "requires_human_review"],
               [[o["source_dataset_id"], o["identifier"], o["why_relevant"], o["requires_human_review"]] for o in outreach])
        if outreach else "(none proposed)"
    )
    sections.append("")

    sections.append("## Limitations")
    for line in batch.limitations:
        sections.append(f"- {line}")
    if plan:
        for line in plan.limitations:
            sections.append(f"- {line}")
    sections.append("")

    sections.append("## Blocked actions")
    blocked = sorted({a for o in batch.ranked_opportunities for a in (o.get("blocked_actions") or [])})
    for a in blocked:
        sections.append(f"- {a}")
    sections.append("")

    sections.append("## Reproducibility")
    for cmd in (reproducibility_commands or []):
        sections.append(f"- `{cmd}`")
    sections.append("")

    sections.append("## Awareness Studio ingest path")
    sections.append(f"`{plan.awareness_studio_manifest_path}`" if plan and plan.awareness_studio_manifest_path else "(not generated)")
    sections.append("")

    text = "\n".join(sections) + "\n"
    hits = scan_text_for_banned_phrases(text)
    if hits:
        raise DatasetOpportunityStoreError(f"rendered opportunity summary contains banned phrase(s): {hits}")
    return text


def write_opportunity_summary(
    batch: DatasetOpportunityBatchV1,
    plan: Optional[DatasetOpportunityPlanV1],
    path: Union[str, Path],
    **kwargs,
) -> Path:
    text = render_opportunity_summary(batch, plan, **kwargs)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path
