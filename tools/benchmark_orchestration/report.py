"""JSON and Markdown report writers for benchmark campaigns."""
from __future__ import annotations

from pathlib import Path
from typing import Union

from tools.benchmark_orchestration.json_util import dumps
from tools.benchmark_orchestration.schema import CampaignReport

PathLike = Union[str, Path]


def dumps_json(report: CampaignReport) -> str:
    """Finite, sorted-key JSON for ``report``."""
    return dumps(report.to_dict())


def render_markdown(report: CampaignReport) -> str:
    """Deterministic Markdown summary (stable section order)."""
    d = report.to_dict()
    lines = [
        "# Benchmark Orchestration Report",
        "",
        f"- schema_version: `{d['schema_version']}`",
        f"- matrix_schema_version: `{d['matrix_schema_version']}`",
        f"- provenance_label: `{d['provenance_label']}`",
        f"- dry_run: `{d['dry_run']}`",
        f"- resumed_from: `{d['resumed_from']}`",
        "",
        "## Campaign limits",
        "",
    ]
    for key in sorted(d["campaign"].keys()):
        lines.append(f"- {key}: `{d['campaign'][key]}`")
    lines.extend(["", "## Summary", ""])
    summary = d["summary"]
    lines.append(f"- total_cases: `{summary['total_cases']}`")
    lines.append(f"- recorded_results: `{summary['recorded_results']}`")
    lines.append(f"- duration_s: `{summary['duration_s']}`")
    lines.append(f"- any_timeout: `{summary['any_timeout']}`")
    lines.append(f"- any_failure: `{summary['any_failure']}`")
    lines.append("- counts:")
    for status in sorted(summary["counts"].keys()):
        lines.append(f"  - {status}: `{summary['counts'][status]}`")
    lines.extend(["", "## Ordering", ""])
    for case_id in d["ordering"]:
        lines.append(f"1. `{case_id}`")
    lines.extend(["", "## Results", ""])
    lines.append("| case_id | status | exit_code | timed_out | duration_s | attempts | checksum |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- |")
    # Results already follow ordering in CampaignReport.
    for r in d["results"]:
        ck = r["checksum"]
        ck_short = (ck[:12] + "…") if isinstance(ck, str) and len(ck) > 12 else ck
        lines.append(
            f"| `{r['case_id']}` | `{r['status']}` | `{r['exit_code']}` | "
            f"`{r['timed_out']}` | `{r['duration_s']}` | `{r['attempts']}` | `{ck_short}` |"
        )
    lines.append("")
    return "\n".join(lines)


def write_reports(report: CampaignReport, output_dir: PathLike) -> dict:
    """Write ``report.json`` and ``report.md`` under ``output_dir``."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    json_path = out / "report.json"
    md_path = out / "report.md"
    json_path.write_text(dumps_json(report) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    return {"json": str(json_path), "markdown": str(md_path)}
