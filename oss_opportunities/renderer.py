"""Deterministic Markdown (and optional static HTML) renderer for an
`OpenSourceLeverageBatchV1` + optional `OpenSourceIntegrationPlanV1` pair.
Stdlib-only, no LLM call, no randomness -- rendering the same batch/plan
twice produces byte-identical output. Every free-text field is scanned for
banned phrases before being written; both render functions raise rather
than write if any are found. Never reproduces raw Trendshift Signal API
data (mission rule 13) -- only already-validated, already-summarized
`OpenSourceRepositoryCandidateV1`/opportunity fields are ever rendered.
"""
from __future__ import annotations

import html as _html
from pathlib import Path
from typing import Optional, Union

from oss_opportunities.opportunity_batch import OpenSourceLeverageBatchV1
from oss_opportunities.planner import OpenSourceIntegrationPlanV1
from oss_opportunities.validation import OssOpportunityStoreError, scan_text_for_banned_phrases

_DISCLAIMER = (
    "This report ranks and plans open-source leverage opportunities. It does not perform any "
    "integration, does not install dependencies, does not execute or clone external code, and does "
    "not redistribute raw third-party API data. Trending/star counts are a discovery-priority signal "
    "only, never proof of quality, correctness, or license safety."
)


def _md_table(headers: list[str], rows: list[list[str]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(str(v) for v in row) + " |")
    return "\n".join(lines)


def render_oss_opportunity_summary(
    batch: OpenSourceLeverageBatchV1,
    plan: Optional[OpenSourceIntegrationPlanV1] = None,
    *,
    reproducibility_commands: Optional[list[str]] = None,
) -> str:
    batch_errs = batch.validate()
    if batch_errs:
        raise OssOpportunityStoreError(f"batch failed validation: {'; '.join(batch_errs)}")
    if plan is not None:
        plan_errs = plan.validate()
        if plan_errs:
            raise OssOpportunityStoreError(f"plan failed validation: {'; '.join(plan_errs)}")

    sections: list[str] = ["# Open-Source Leverage Scouting Report", "", f"> {_DISCLAIMER}", ""]

    sections.append("## Sources scanned")
    for source in batch.sources_scanned:
        sections.append(f"- `{source}`")
    sections.append(f"- candidates_seen: {batch.candidates_seen}")
    sections.append(f"- opportunities_ranked: {len(batch.opportunities_ranked)}")
    sections.append(f"- opportunities_rejected: {len(batch.opportunities_rejected)}")
    sections.append(f"- batch_id: `{batch.batch_id}`")
    sections.append(f"- generated_at: {batch.generated_at}")
    sections.append("")

    sections.append("## Top repositories by category")
    if batch.top_by_category:
        rows = [[category, ", ".join(repos)] for category, repos in sorted(batch.top_by_category.items())]
        sections.append(_md_table(["leverage_category", "repositories"], rows))
    else:
        sections.append("(none ranked)")
    sections.append("")

    sections.append("## Immediate adapter candidates")
    adapter_rows = [
        [e["repo_full_name"], e["leverage_category"], e["recommended_action"], e["total_score"]]
        for e in batch.opportunities_ranked
        if e["recommended_action"] in ("integrate_as_optional_adapter", "integrate_as_external_tool_record")
    ]
    sections.append(
        _md_table(["repo", "leverage_category", "recommended_action", "total_score"], adapter_rows)
        if adapter_rows else "(none)"
    )
    sections.append("")

    sections.append("## Architecture emulation candidates")
    emulation_rows = [
        [e["repo_full_name"], e["leverage_category"], e["total_score"]]
        for e in batch.opportunities_ranked if e["recommended_action"] == "emulate_architecture_pattern"
    ]
    sections.append(_md_table(["repo", "leverage_category", "total_score"], emulation_rows) if emulation_rows else "(none)")
    sections.append("")

    sections.append("## Documentation references")
    docs_rows = [
        [e["repo_full_name"], e["leverage_category"]]
        for e in batch.opportunities_ranked if e["recommended_action"] in ("create_docs_reference", "create_future_task")
    ]
    sections.append(_md_table(["repo", "leverage_category"], docs_rows) if docs_rows else "(none)")
    sections.append("")

    sections.append("## License risk table")
    license_rows = [
        [
            e["repo_full_name"],
            (e.get("license_review") or {}).get("license_spdx", "unknown"),
            (e.get("license_review") or {}).get("license_risk", "unknown"),
            (e.get("license_review") or {}).get("commercial_core_policy", "blocked_pending_review"),
        ]
        for e in batch.opportunities_ranked
    ]
    sections.append(
        _md_table(["repo", "license_spdx", "license_risk", "commercial_core_policy"], license_rows)
        if license_rows else "(none)"
    )
    sections.append("")

    sections.append("## Security risk table")
    security_rows = [
        [e["repo_full_name"], e["security_risk"], e["dependency_weight"]]
        for e in batch.opportunities_ranked if e["security_risk"] != "low"
    ]
    sections.append(_md_table(["repo", "security_risk", "dependency_weight"], security_rows) if security_rows else "(no elevated security risk recorded)")
    sections.append("")

    sections.append("## Rejected / deferred repositories")
    rejection_rows = [[r["repo_full_name"], r["reason"]] for r in batch.opportunities_rejected]
    if plan is not None:
        rejection_rows += [[d["repo_full_name"], "deferred"] for d in plan.deferred_candidates]
    sections.append(_md_table(["repo", "reason"], rejection_rows) if rejection_rows else "(none)")
    sections.append("")

    sections.append("## Proposed next PRs")
    if plan and plan.proposed_next_prs:
        for pr_name in plan.proposed_next_prs:
            sections.append(f"- {pr_name}")
    else:
        sections.append("(none proposed)")
    sections.append("")

    sections.append("## Blocked actions")
    blocked = sorted({a for e in batch.opportunities_ranked for a in (e.get("blocked_actions") or [])})
    for a in blocked:
        sections.append(f"- {a}")
    sections.append("")

    sections.append("## Limitations")
    for line in batch.limitations:
        sections.append(f"- {line}")
    if plan:
        for line in plan.limitations:
            sections.append(f"- {line}")
    sections.append("")

    sections.append("## Reproducibility")
    for cmd in (reproducibility_commands or []):
        sections.append(f"- `{cmd}`")
    sections.append("")

    text = "\n".join(sections) + "\n"
    hits = scan_text_for_banned_phrases(text)
    if hits:
        raise OssOpportunityStoreError(f"rendered OSS opportunity summary contains banned phrase(s): {hits}")
    return text


def render_oss_opportunity_summary_html(
    batch: OpenSourceLeverageBatchV1,
    plan: Optional[OpenSourceIntegrationPlanV1] = None,
) -> str:
    """Minimal, dependency-free static HTML mirror of the Markdown report --
    no external CSS/JS/CDN, no `<script>` tag, every value `html.escape`-d."""
    batch_errs = batch.validate()
    if batch_errs:
        raise OssOpportunityStoreError(f"batch failed validation: {'; '.join(batch_errs)}")
    if plan is not None:
        plan_errs = plan.validate()
        if plan_errs:
            raise OssOpportunityStoreError(f"plan failed validation: {'; '.join(plan_errs)}")

    def esc(value: object) -> str:
        return _html.escape(str(value))

    rows = "".join(
        f"<tr><td>{esc(e['repo_full_name'])}</td><td>{esc(e['leverage_category'])}</td>"
        f"<td>{esc(e['recommended_action'])}</td><td>{esc(e['total_score'])}</td></tr>"
        for e in batch.opportunities_ranked
    )
    pr_items = "".join(f"<li>{esc(pr)}</li>" for pr in (plan.proposed_next_prs if plan else []))

    html_doc = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Open-Source Leverage Scouting Report</title>
<style>
body {{ font-family: -apple-system, Segoe UI, Helvetica, Arial, sans-serif; max-width: 960px; margin: 0 auto; padding: 1.5rem; }}
table {{ border-collapse: collapse; width: 100%; margin: 0.5rem 0 1rem; }}
th, td {{ border: 1px solid #8884; padding: 0.35rem 0.6rem; text-align: left; }}
.disclaimer {{ background: #fff3cd; color: #664d03; border: 1px solid #ffe69c; border-radius: 6px; padding: 0.75rem 1rem; margin: 1rem 0; }}
</style>
</head>
<body>
<h1>Open-Source Leverage Scouting Report</h1>
<p class="disclaimer">{esc(_DISCLAIMER)}</p>
<h2>Sources scanned</h2>
<p>{esc(", ".join(batch.sources_scanned))} -- candidates_seen: {esc(batch.candidates_seen)}, batch_id: {esc(batch.batch_id)}</p>
<h2>Ranked opportunities</h2>
<table><tr><th>repo</th><th>leverage_category</th><th>recommended_action</th><th>total_score</th></tr>{rows}</table>
<h2>Proposed next PRs</h2>
<ul>{pr_items or "<li>(none proposed)</li>"}</ul>
</body>
</html>
"""
    hits = scan_text_for_banned_phrases(html_doc)
    if hits:
        raise OssOpportunityStoreError(f"rendered OSS opportunity HTML summary contains banned phrase(s): {hits}")
    return html_doc


def write_oss_opportunity_summary(
    batch: OpenSourceLeverageBatchV1,
    plan: Optional[OpenSourceIntegrationPlanV1],
    out_dir: Union[str, Path],
    *,
    write_html: bool = True,
    **kwargs,
) -> dict[str, Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}

    md_text = render_oss_opportunity_summary(batch, plan, **kwargs)
    md_path = out_dir / "summary.md"
    md_path.write_text(md_text, encoding="utf-8")
    written["markdown"] = md_path

    if write_html:
        html_text = render_oss_opportunity_summary_html(batch, plan)
        html_path = out_dir / "summary.html"
        html_path.write_text(html_text, encoding="utf-8")
        written["html"] = html_path

    return written
