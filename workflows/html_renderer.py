"""Deterministic, stdlib-only static HTML renderer for `HtmlReportPackV1`.

No LLM call, no randomness, no wall-clock-dependent formatting beyond
already-fixed `created_at` fields -- rendering the same inputs twice
produces byte-identical HTML (mirrors `reports.renderer.render_markdown`'s
own determinism guarantee). Every piece of source-derived text is passed
through `html.escape`; Markdown report text is embedded as escaped
preformatted text, never executed as raw HTML. No external CSS/JS/CDN --
all styling is a single inline `<style>` block, and no `<script>` tag is
emitted at all.
"""
from __future__ import annotations

import html as _html
from typing import Any, Optional

_DISCLAIMER = (
    "Research-use / exploratory artifact. This page is a deterministic, static "
    "rendering of already-governed pipeline output -- it is not clinical "
    "evidence, does not represent a validated consciousness biomarker, and "
    "does not support a diagnostic, treatment, or spiritual-attainment "
    "claim. See Limitations and Blocked interpretations below."
)

_CSS = """
:root { color-scheme: light dark; }
body { font-family: -apple-system, Segoe UI, Helvetica, Arial, sans-serif; max-width: 960px;
       margin: 0 auto; padding: 1.5rem 1.25rem 3rem; line-height: 1.5; }
h1 { font-size: 1.6rem; margin-bottom: 0.25rem; }
h2 { font-size: 1.15rem; margin-top: 2rem; border-bottom: 1px solid #8884; padding-bottom: 0.25rem; }
.disclaimer { background: #fff3cd; color: #664d03; border: 1px solid #ffe69c; border-radius: 6px;
              padding: 0.75rem 1rem; margin: 1rem 0; font-size: 0.92rem; }
table { border-collapse: collapse; width: 100%; margin: 0.5rem 0 1rem; }
th, td { border: 1px solid #8884; padding: 0.35rem 0.6rem; text-align: left; font-size: 0.92rem; vertical-align: top; }
th { background: #80808014; }
ul { margin: 0.25rem 0 1rem; padding-left: 1.4rem; }
li { margin-bottom: 0.2rem; }
pre { background: #80808014; border: 1px solid #8884; border-radius: 6px; padding: 0.75rem;
      overflow-x: auto; white-space: pre-wrap; word-break: break-word; font-size: 0.85rem; }
code { font-family: ui-monospace, SFMono-Regular, Consolas, monospace; }
.badge { display: inline-block; padding: 0.15rem 0.55rem; border-radius: 999px; font-size: 0.8rem;
         font-weight: 600; }
.badge-ok { background: #d1e7dd; color: #0a3622; }
.badge-warn { background: #fff3cd; color: #664d03; }
.badge-muted { background: #80808022; color: inherit; }
.meta { color: #666; font-size: 0.88rem; }
footer { margin-top: 3rem; font-size: 0.82rem; color: #777; border-top: 1px solid #8884; padding-top: 1rem; }
"""


def _esc(value: Any) -> str:
    if value is None:
        return ""
    return _html.escape(str(value))


def _section(title: str, body: str) -> str:
    return f"<section>\n<h2>{_esc(title)}</h2>\n{body}\n</section>\n"


def _bullet_list(items: list[Any]) -> str:
    if not items:
        return "<p><em>None recorded.</em></p>\n"
    inner = "\n".join(f"  <li>{_esc(item)}</li>" for item in items)
    return f"<ul>\n{inner}\n</ul>\n"


def _kv_table(rows: list[tuple[str, Any]]) -> str:
    if not rows:
        return "<p><em>None recorded.</em></p>\n"
    inner = "\n".join(f"  <tr><th>{_esc(k)}</th><td>{_esc(v)}</td></tr>" for k, v in rows)
    return f"<table>\n{inner}\n</table>\n"


def _dict_table(d: Optional[dict[str, Any]]) -> str:
    if not d:
        return "<p><em>None recorded.</em></p>\n"
    rows: list[tuple[str, Any]] = []
    for key in sorted(d.keys()):
        value = d[key]
        if isinstance(value, (dict, list)):
            value = _esc_repr(value)
        rows.append((key, value))
    return _kv_table(rows)


def _esc_repr(value: Any) -> str:
    # A deterministic, compact, already-escaped-on-render string form for
    # a nested dict/list value shown inside a table cell.
    import json as _json

    try:
        return _json.dumps(value, sort_keys=True, default=str)
    except TypeError:
        return str(value)


def _badge(label: str, kind: str = "muted") -> str:
    return f'<span class="badge badge-{_esc(kind)}">{_esc(label)}</span>'


def _links_section(
    *, copied_artifact_paths: list[str], source_evidence_report_paths: list[str],
    source_evidence_bundle_paths: list[str], source_report_pack_path: str,
) -> str:
    parts: list[str] = []
    if copied_artifact_paths:
        parts.append("<p>Artifacts copied alongside this page (<code>artifacts/</code>):</p>")
        items = []
        for rel in copied_artifact_paths:
            name = rel.rsplit("/", 1)[-1]
            items.append(f'<a href="artifacts/{_esc(name)}">{_esc(name)}</a>')
        parts.append("<ul>\n" + "\n".join(f"  <li>{i}</li>" for i in items) + "\n</ul>\n")
    else:
        parts.append("<p>Artifacts were not copied alongside this page. Original repository-relative paths:</p>")
        all_paths = [p for p in (source_report_pack_path, *source_evidence_report_paths, *source_evidence_bundle_paths) if p]
        if all_paths:
            items = [f"<code>{_esc(p)}</code>" for p in all_paths]
            parts.append("<ul>\n" + "\n".join(f"  <li>{i}</li>" for i in items) + "\n</ul>\n")
        else:
            parts.append("<p><em>None recorded.</em></p>\n")
    return "\n".join(parts)


_FUTURE_WORK_ITEMS = [
    "PDF export of this report pack (not implemented -- see docs/html_report_pack_renderer.md#future-work).",
    "Holo-Atlas evidence viewer consumption of ReportPackV1/EvidenceBundleV1 output (not implemented, no design commitment).",
    "Hosted SaaS preview / signed report archives (not implemented).",
    "Multi-report comparison dashboards across pipeline runs (not implemented).",
    "Richer QC and topology backends surface automatically here once the underlying recipes/adapters gain them -- this "
    "renderer never duplicates their logic, so no change to this page would be required.",
]


def render_index_html(
    *,
    html_pack: Any,
    report_pack: Any,
    pipeline_manifest: Optional[dict[str, Any]],
    evidence_report_docs: list[dict[str, Any]],
    evidence_bundle_docs: list[dict[str, Any]],
    evidence_report_md_texts: list[str],
    copied_artifact_paths: list[str],
    source_evidence_report_paths: list[str],
    source_evidence_bundle_paths: list[str],
) -> tuple[str, list[str]]:
    """Returns `(html_text, rendered_section_names)`. Pure function: same
    inputs always produce the same output string."""
    sections: list[str] = []
    rendered: list[str] = []

    evidence_report = evidence_report_docs[0] if evidence_report_docs else None
    evidence_bundle = evidence_bundle_docs[0] if evidence_bundle_docs else None
    summary = report_pack.summary or {}

    # 1. Header / title / status
    status = "completed"
    if pipeline_manifest is not None:
        status = pipeline_manifest.get("execution_status", status)
    status_kind = "ok" if status in ("completed",) else ("warn" if status == "completed_with_warnings" else "muted")
    header = (
        f'<p class="meta">Dataset: <code>{_esc(html_pack.dataset_id)}</code> &middot; '
        f'Input mode: <code>{_esc(html_pack.input_mode)}</code> &middot; '
        f'Status: {_badge(status, status_kind)}</p>\n'
        f'<p class="meta">Report pack ID: <code>{_esc(report_pack.report_pack_id)}</code> &middot; '
        f'Generated: {_esc(html_pack.created_at)} &middot; '
        f'Repo commit: <code>{_esc(html_pack.repo_commit or "unknown")}</code></p>\n'
        f'<div class="disclaimer">{_esc(_DISCLAIMER)}</div>\n'
    )
    sections.append(f'<h1>{_esc(html_pack.title)}</h1>\n{header}')
    rendered.append("header")

    # 2. Executive summary
    n_tx = summary.get("n_transition_records")
    n_ps = summary.get("n_phase_space_coordinates")
    exec_lines = [
        f"This page presents a report pack generated for dataset "
        f"<code>{_esc(report_pack.dataset_id)}</code> via input mode "
        f"<code>{_esc(report_pack.input_mode)}</code>."
    ]
    if n_tx is not None:
        exec_lines.append(f"It references {_esc(n_tx)} transition record(s)" + (f" and {_esc(n_ps)} phase-space coordinate(s)." if n_ps is not None else "."))
    exec_lines.append(
        "Every value shown on this page was already computed by this repository's governed adapter/"
        "evidence/report modules before this page was rendered -- no new computation happens here."
    )
    sections.append(_section("Executive summary", "\n".join(f"<p>{line}</p>" for line in exec_lines)))
    rendered.append("executive_summary")

    # 3. Evidence chain
    chain_rows = [
        ("Input mode", report_pack.input_mode),
        ("Dataset ID", report_pack.dataset_id),
        ("Modality", report_pack.modality or "(unspecified)"),
        ("Pipeline run ID", report_pack.pipeline_run_id or "(none)"),
        ("Report pack ID", report_pack.report_pack_id),
    ]
    sections.append(_section("Evidence chain", _kv_table(chain_rows)))
    rendered.append("evidence_chain")

    # 4. Registry / authorization summary
    registry_summary = (evidence_report or {}).get("registry_summary")
    sections.append(_section(
        "Registry / authorization summary",
        _dict_table(registry_summary) if registry_summary is not None else "<p><em>No linked EvidenceReport -- registry authorization detail is not available on this page.</em></p>\n",
    ))
    rendered.append("registry_summary")

    # 5. Transition summary
    transition_summary = (evidence_report or {}).get("transition_summary")
    if transition_summary is None and n_tx is not None:
        transition_summary = {"n_transition_records": n_tx}
    sections.append(_section("Transition summary", _dict_table(transition_summary)))
    rendered.append("transition_summary")

    # 6. Phase-space summary
    phase_space_summary = (evidence_report or {}).get("phase_space_summary")
    if phase_space_summary is None and n_ps is not None:
        phase_space_summary = {"n_phase_space_coordinates": n_ps}
    sections.append(_section("Phase-space summary", _dict_table(phase_space_summary)))
    rendered.append("phase_space_summary")

    # 7. Null-control summary
    null_control_summary = (evidence_report or {}).get("null_control_summary")
    if null_control_summary is None:
        status_value = summary.get("null_control_status")
        null_control_summary = {"status": status_value} if status_value is not None else None
    sections.append(_section("Null-control summary", _dict_table(null_control_summary)))
    rendered.append("null_control_summary")

    # 8. Claim / evidence ceiling summary
    claim_rows: list[tuple[str, Any]] = []
    for key, label in (
        ("claim_scope_ceiling", "Claim scope ceiling"),
        ("evidence_level_ceiling", "Evidence level ceiling"),
        ("generated_claim_scope", "Generated claim scope"),
    ):
        if key in summary:
            claim_rows.append((label, summary[key]))
    if evidence_report is not None:
        css = evidence_report.get("claim_scope_summary")
        ess = evidence_report.get("evidence_level_summary")
        if css:
            claim_rows.append(("Claim scope summary (EvidenceReport)", _esc_repr(css)))
        if ess:
            claim_rows.append(("Evidence level summary (EvidenceReport)", _esc_repr(ess)))
    sections.append(_section(
        "Claim / evidence ceiling summary",
        _kv_table(claim_rows) if claim_rows else "<p><em>Not available for this report pack.</em></p>\n",
    ))
    rendered.append("claim_evidence_summary")

    # 9. Validation summary
    validation_rows: list[tuple[str, Any]] = list((html_pack.validation_summary or {}).items())
    if evidence_bundle is not None:
        vs = evidence_bundle.get("validation_summary")
        if vs:
            validation_rows.append(("source_evidence_bundle.validation_summary", _esc_repr(vs)))
    sections.append(_section("Validation summary", _kv_table(validation_rows)))
    rendered.append("validation_summary")

    # 10. Limitations
    sections.append(_section("Limitations", _bullet_list(html_pack.limitations)))
    rendered.append("limitations")

    # 11. Blocked interpretations
    sections.append(_section("Blocked interpretations", _bullet_list(html_pack.blocked_interpretations)))
    rendered.append("blocked_interpretations")

    # 12. Reproducibility commands
    if html_pack.reproducibility_commands:
        cmds = "\n".join(f"<pre><code>{_esc(cmd)}</code></pre>" for cmd in html_pack.reproducibility_commands)
    else:
        cmds = "<p><em>None recorded.</em></p>\n"
    sections.append(_section("Reproducibility commands", cmds))
    rendered.append("reproducibility_commands")

    # 13. Generated artifact manifest
    manifest_body = _dict_table(report_pack.artifact_manifest)
    if pipeline_manifest is not None:
        steps_rows = [
            ("steps_completed", ", ".join(pipeline_manifest.get("steps_completed") or []) or "(none)"),
            ("steps_skipped", ", ".join(pipeline_manifest.get("steps_skipped") or []) or "(none)"),
        ]
        manifest_body += _kv_table(steps_rows)
    sections.append(_section("Generated artifact manifest", manifest_body))
    rendered.append("artifact_manifest")

    # 14. Download / view links
    links_body = _links_section(
        copied_artifact_paths=copied_artifact_paths,
        source_evidence_report_paths=source_evidence_report_paths,
        source_evidence_bundle_paths=source_evidence_bundle_paths,
        source_report_pack_path=html_pack.source_report_pack_path,
    )
    if evidence_report_md_texts:
        links_body += "<p>Full evidence report text (Markdown source, shown verbatim as escaped text):</p>\n"
        for text in evidence_report_md_texts:
            links_body += f"<pre>{_esc(text)}</pre>\n"
    sections.append(_section("Download / view artifacts", links_body))
    rendered.append("artifact_links")

    # 15. Future work / next validation
    sections.append(_section("Future work / next validation", _bullet_list(_FUTURE_WORK_ITEMS)))
    rendered.append("future_work")

    footer = (
        f'<footer>Generated by workflows.html_report_pack (template '
        f'{_esc("workflows.html_renderer v1")}). {_esc(_DISCLAIMER)}</footer>\n'
    )

    body = "\n".join(sections) + footer
    html_text = (
        f'<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        f'<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f'<title>{_esc(html_pack.title)}</title>\n<style>{_CSS}</style>\n</head>\n<body>\n{body}\n</body>\n</html>\n'
    )
    return html_text, rendered
