"""Finite JSON / Markdown writers for smoke reports."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional, Union

from tools.release_readiness.research_cycle_smoke.schema import json_safe

PathLike = Union[str, Path]


def dumps(obj: Any, *, indent: Optional[int] = 2) -> str:
    return json.dumps(json_safe(obj), indent=indent, sort_keys=True, allow_nan=False)


def render_markdown(payload: Dict[str, Any]) -> str:
    lines = [
        "# Research-Cycle Smoke Report",
        "",
        f"- schema_version: `{payload.get('schema_version')}`",
        f"- evidence_class: `{payload.get('evidence_class')}`",
        f"- synthetic: `{payload.get('synthetic')}`",
        f"- scientific_pass_emitted: `{payload.get('scientific_pass_emitted')}`",
        f"- bayes_factor_emitted: `{payload.get('bayes_factor_emitted')}`",
        f"- network_accessed: `{payload.get('network_accessed')}`",
        f"- n_scenarios: `{payload.get('n_scenarios')}`",
        f"- all_decisions_match: `{payload.get('all_decisions_match')}`",
        f"- all_guards_pass: `{payload.get('all_guards_pass')}`",
        f"- deterministic: `{payload.get('deterministic')}`",
        "",
        "## Decision matrix",
        "",
        "| scenario | expected | observed | match |",
        "| --- | --- | --- | --- |",
    ]
    for row in payload.get("decision_matrix") or []:
        lines.append(
            f"| `{row.get('scenario_id')}` | `{row.get('expected')}` | "
            f"`{row.get('observed')}` | `{row.get('match')}` |"
        )
    lines.extend(["", "## Limitations", ""])
    for lim in payload.get("limitations") or []:
        lines.append(f"- {lim}")
    lines.append("")
    return "\n".join(lines)


def write_reports(payload: Dict[str, Any], output_dir: PathLike) -> Dict[str, str]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    jp = out / "research_cycle_smoke.json"
    mp = out / "research_cycle_smoke.md"
    jp.write_text(dumps(payload) + "\n", encoding="utf-8")
    mp.write_text(render_markdown(payload), encoding="utf-8")
    return {"json": str(jp), "markdown": str(mp)}
