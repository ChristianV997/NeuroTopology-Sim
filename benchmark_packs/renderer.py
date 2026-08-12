"""Deterministic, stdlib-only static HTML renderer for `BenchmarkPackV1`
-- a single aggregate index page over the report packs/HTML packs a
`job_runner.batch` run produced, separate from each individual
`HtmlReportPackV1` page (see `workflows.html_renderer`).

No LLM call, no randomness, no wall-clock-dependent formatting beyond
already-fixed `created_at` fields -- rendering the same `BenchmarkPackV1`
twice produces byte-identical HTML. Every piece of source-derived text is
passed through `html.escape`. No external CSS/JS/CDN -- a single inline
`<style>` block, no `<script>` tag at all. Links only to already-existing
pack/report/HTML artifact paths already present on `pack` -- never to a
raw data file, and never fabricated for a missing artifact.
"""
from __future__ import annotations

import html as _html
from pathlib import Path
from typing import Any, Union

from benchmark_packs.pack_manifest import BenchmarkPackIndexV1, BenchmarkPackV1
from benchmark_packs.validation import BenchmarkPackStoreError, scan_text_for_banned_phrases

_REPO_ROOT = Path(__file__).resolve().parents[1]

INDEX_FILENAME = "index.html"

_DISCLAIMER = (
    "Research-use / exploratory artifact. This page is a deterministic, static index over "
    "already-governed report-pack output -- it is not clinical evidence, does not represent a "
    "validated consciousness biomarker, and does not support a diagnostic, treatment, or "
    "spiritual-attainment claim. See Limitations and Blocked interpretations below."
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
.badge { display: inline-block; padding: 0.15rem 0.55rem; border-radius: 999px; font-size: 0.8rem; font-weight: 600; }
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


def _list_or_none(items: list) -> str:
    if not items:
        return "<p class=\"meta\">None.</p>"
    return "<ul>\n" + "\n".join(f"<li>{_esc(item)}</li>" for item in items) + "\n</ul>\n"


def _kv_table(rows: dict) -> str:
    if not rows:
        return "<p class=\"meta\">None.</p>"
    body = "\n".join(f"<tr><th>{_esc(k)}</th><td>{_esc(v)}</td></tr>" for k, v in rows.items())
    return f"<table>\n{body}\n</table>\n"


def render_index_html(pack: BenchmarkPackV1) -> tuple[str, list[str]]:
    """Pure function: `pack` in, `(html_text, sections_rendered)` out. No
    filesystem access, no banned-phrase scan (that happens at write time
    in `render_benchmark_pack_index`, mirroring `workflows.html_report_pack`'s
    own render-then-scan-then-write discipline)."""
    sections_rendered: list[str] = []

    def add(title: str, body: str) -> str:
        sections_rendered.append(title)
        return _section(title, body)

    header = (
        f"<h1>{_esc(pack.pack_name or pack.benchmark_pack_id)}</h1>\n"
        f"<p class=\"meta\">pack_kind: <span class=\"badge badge-muted\">{_esc(pack.pack_kind)}</span> "
        f"&middot; benchmark_pack_id: <code>{_esc(pack.benchmark_pack_id)}</code> "
        f"&middot; generated: {_esc(pack.created_at)}</p>\n"
        f"<div class=\"disclaimer\">{_esc(_DISCLAIMER)}</div>\n"
    )

    purpose_text = _esc(pack.pack_purpose) or "<span class=\"meta\">Not specified.</span>"
    purpose = add("Purpose", f"<p>{purpose_text}</p>\n")

    execution = add("Execution summary", _kv_table(pack.execution_summary))

    coverage_rows = {
        "datasets": ", ".join(sorted(pack.dataset_ids)) or "none",
        "modalities": ", ".join(sorted(pack.modalities)) or "none",
        "input_modes": ", ".join(sorted(pack.input_modes)) or "none",
    }
    coverage_included = add("Datasets / modalities / input modes included", _kv_table(coverage_rows))

    if pack.report_pack_ids:
        paths = pack.generated_report_pack_paths or [None] * len(pack.report_pack_ids)
        row_cells = []
        for rp_id, path in zip(pack.report_pack_ids, paths):
            path_cell = _esc(path) if path else "<span class=\"meta\">unavailable</span>"
            row_cells.append(f"<tr><td><code>{_esc(rp_id)}</code></td><td>{path_cell}</td></tr>")
        rows = "\n".join(row_cells)
        report_table = f"<table>\n<tr><th>report_pack_id</th><th>path</th></tr>\n{rows}\n</table>\n"
    else:
        report_table = "<p class=\"meta\">No report packs were generated.</p>\n"
    report_packs = add("Report packs", report_table)

    if pack.html_pack_ids and pack.generated_html_paths:
        links = "\n".join(f"<li><a href=\"{_esc(path)}\">{_esc(path)}</a></li>" for path in pack.generated_html_paths)
        html_links = f"<ul>\n{links}\n</ul>\n"
    else:
        html_links = "<p class=\"meta\">No HTML report packs were generated.</p>\n"
    html_report_links = add("HTML report links", html_links)

    coverage_summary = add("Coverage summary", _kv_table(pack.coverage_summary))

    limitations = add("Limitations", _list_or_none(pack.limitations))
    blocked = add("Blocked interpretations", _list_or_none(pack.blocked_interpretations))
    repro = add("Reproducibility commands", (
        "<pre>" + _esc("\n".join(pack.reproducibility_commands)) + "</pre>\n"
        if pack.reproducibility_commands else "<p class=\"meta\">None recorded.</p>\n"
    ))

    manifest_rows = {
        "job_ids": len(pack.job_ids), "pipeline_ids": len(pack.pipeline_ids),
        "report_pack_ids": len(pack.report_pack_ids), "html_pack_ids": len(pack.html_pack_ids),
        "generated_report_pack_paths": len(pack.generated_report_pack_paths),
        "generated_html_paths": len(pack.generated_html_paths),
    }
    manifest = add("Generated artifact manifest", _kv_table(manifest_rows))

    future_work = add("Future work", _list_or_none([
        "Authenticated API for building/serving benchmark packs.",
        "Scheduled benchmark-pack regeneration.",
        "Signed benchmark-pack archives.",
        "PDF export of a benchmark pack.",
        "Richer cross-report comparison views.",
    ]))

    body = "\n".join([
        header, purpose, execution, coverage_included, report_packs, html_report_links,
        coverage_summary, limitations, blocked, repro, manifest, future_work,
    ])

    html_text = (
        "<!doctype html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n"
        f"<title>{_esc(pack.pack_name or pack.benchmark_pack_id)} -- Benchmark Pack</title>\n"
        f"<style>{_CSS}</style>\n</head>\n<body>\n{body}\n"
        f"<footer>repo_commit: {_esc(pack.repo_commit)} &middot; schema_version: {_esc(pack.schema_version)}</footer>\n"
        "</body>\n</html>\n"
    )
    return html_text, sections_rendered


def render_benchmark_pack_index(pack: BenchmarkPackV1, out_dir: Union[str, Path]) -> BenchmarkPackIndexV1:
    """Renders `pack`'s static index to `out_dir/index.html`, scans it for
    banned phrases before writing (refuses to write if any are found),
    and returns the resulting `BenchmarkPackIndexV1`."""
    resolved_out = Path(out_dir)
    if not resolved_out.is_absolute():
        resolved_out = _REPO_ROOT / resolved_out
    resolved_out.mkdir(parents=True, exist_ok=True)

    html_text, sections_rendered = render_index_html(pack)

    banned_hits = scan_text_for_banned_phrases(html_text)
    if banned_hits:
        raise BenchmarkPackStoreError(f"rendered benchmark-pack index contains banned phrase(s), refusing to write: {banned_hits}")

    index_path = resolved_out / INDEX_FILENAME
    index_path.write_text(html_text, encoding="utf-8")

    try:
        relative_index_path = str(index_path.resolve().relative_to(_REPO_ROOT))
    except ValueError:
        relative_index_path = str(index_path)

    index = BenchmarkPackIndexV1.make(
        benchmark_pack_id=pack.benchmark_pack_id, linked_html_packs=list(pack.generated_html_paths),
        title=pack.pack_name or pack.benchmark_pack_id, output_root=str(out_dir),
        index_html_path=relative_index_path, linked_report_packs=list(pack.generated_report_pack_paths),
        sections_rendered=sections_rendered, limitations=list(pack.limitations),
        blocked_interpretations=list(pack.blocked_interpretations),
    )
    index.validate_or_raise()
    return index
