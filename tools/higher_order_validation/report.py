"""Report writers for adversarial validation suites."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from tools.higher_order_validation.schema import ValidationCaseResult, json_safe

PathLike = Union[str, Path]


def dumps(obj: Any, *, indent: Optional[int] = 2) -> str:
    return json.dumps(json_safe(obj), indent=indent, sort_keys=True, allow_nan=False)


def suite_to_dict(results: List[ValidationCaseResult], *, meta: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    counts: Dict[str, int] = {}
    for r in results:
        counts[r.outcome.value] = counts.get(r.outcome.value, 0) + 1
    return json_safe(
        {
            "schema_version": "1.0",
            "evidence_class": "engineering_adversarial_synthetic",
            "synthetic": True,
            "scientific_pass_emitted": False,
            "formal_bayes_factor_emitted": False,
            "counts": counts,
            "n_cases": len(results),
            "meta": meta or {},
            "results": [r.to_dict() for r in results],
            "limitations": [
                "Adversarial synthetic validation is engineering evidence, not empirical neuroscience.",
                "Never interpret these outcomes as a scientific PASS or formal Bayes factor.",
            ],
        }
    )


def render_markdown(payload: Dict[str, Any]) -> str:
    lines = [
        "# Higher-Order Adversarial Validation Report",
        "",
        f"- evidence_class: `{payload.get('evidence_class')}`",
        f"- synthetic: `{payload.get('synthetic')}`",
        f"- scientific_pass_emitted: `{payload.get('scientific_pass_emitted')}`",
        f"- formal_bayes_factor_emitted: `{payload.get('formal_bayes_factor_emitted')}`",
        f"- n_cases: `{payload.get('n_cases')}`",
        "",
        "## Counts",
        "",
    ]
    for k in sorted((payload.get("counts") or {}).keys()):
        lines.append(f"- `{k}`: `{payload['counts'][k]}`")
    lines.extend(["", "## Cases", ""])
    lines.append("| case_id | dgp | expected | observed | outcome |")
    lines.append("| --- | --- | --- | --- | --- |")
    for r in payload.get("results") or []:
        lines.append(
            f"| `{r['case_id']}` | `{r['data_generating_process']}` | "
            f"`{r['expected_result']}` | `{r['observed_result']}` | `{r['outcome']}` |"
        )
    lines.extend(["", "## Limitations", ""])
    for lim in payload.get("limitations") or []:
        lines.append(f"- {lim}")
    lines.append("")
    return "\n".join(lines)


def write_reports(payload: Dict[str, Any], output_dir: PathLike) -> Dict[str, str]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    jp = out / "higher_order_validation.json"
    mp = out / "higher_order_validation.md"
    jp.write_text(dumps(payload) + "\n", encoding="utf-8")
    mp.write_text(render_markdown(payload), encoding="utf-8")
    return {"json": str(jp), "markdown": str(mp)}
