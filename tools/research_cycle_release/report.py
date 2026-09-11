"""Finite JSON / Markdown writers."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional, Union

from tools.research_cycle_release.schema import ReleaseEvidenceReport, json_safe

PathLike = Union[str, Path]


def dumps(obj: Any, *, indent: Optional[int] = 2) -> str:
    return json.dumps(json_safe(obj), indent=indent, sort_keys=True, allow_nan=False)


def render_markdown(report: ReleaseEvidenceReport) -> str:
    data = report.to_dict()
    lines = [
        "# Research-Cycle Release Evidence Report",
        "",
        f"- schema_version: `{data.get('schema_version')}`",
        f"- decision: `{data.get('decision')}`",
        f"- cycle_id: `{data.get('cycle_id')}`",
        f"- evidence_class: `{data.get('evidence_class')}`",
        f"- scientific_pass_emitted: `{data.get('scientific_pass_emitted')}`",
        f"- bayes_factor_emitted: `{data.get('bayes_factor_emitted')}`",
        f"- causal_promotion_emitted: `{data.get('causal_promotion_emitted')}`",
        f"- source_adapter: `{data.get('source_adapter')}`",
        "",
        "## Reasons",
        "",
    ]
    for reason in data.get("reasons") or []:
        lines.append(f"- {reason}")
    lines.extend(["", "## Reason codes", ""])
    for code in data.get("reason_codes") or []:
        lines.append(f"- `{code}`")
    lines.extend(["", "## Checks", "", "| check_id | passed | detail |", "| --- | --- | --- |"])
    for check in data.get("checks") or []:
        lines.append(
            f"| `{check.get('check_id')}` | `{check.get('passed')}` | {check.get('detail') or ''} |"
        )
    lines.extend(["", "## Limitations", ""])
    for lim in data.get("limitations") or []:
        lines.append(f"- {lim}")
    lines.append("")
    return "\n".join(lines)


def write_reports(
    report: ReleaseEvidenceReport,
    output_dir: PathLike,
    *,
    basename: str = "research_cycle_release_evidence",
) -> Dict[str, str]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    payload = report.to_dict()
    jp = out / f"{basename}.json"
    mp = out / f"{basename}.md"
    jp.write_text(dumps(payload) + "\n", encoding="utf-8")
    mp.write_text(render_markdown(report), encoding="utf-8")
    return {"json": str(jp), "markdown": str(mp)}
