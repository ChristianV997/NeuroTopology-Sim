"""Deterministic JSON/Markdown audit report helpers."""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, Optional


def json_safe(value: Any) -> Any:
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    return value


def dumps(obj: Any, *, indent: Optional[int] = 2) -> str:
    return json.dumps(json_safe(obj), indent=indent, allow_nan=False, sort_keys=True)


def write_json(path: str | Path, payload: Dict[str, Any]) -> str:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(dumps(payload) + "\n", encoding="utf-8")
    return str(p)


def write_markdown(path: str | Path, payload: Dict[str, Any]) -> str:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Hodge Decomposition Numerical Audit",
        "",
        f"- schema_version: `{payload.get('schema_version')}`",
        f"- evidence_class: `{payload.get('evidence_class')}`",
        f"- audit_status: `{payload.get('audit_status')}`",
        f"- proposal_claimed_passed: `{payload.get('proposal_claimed_passed')}`",
        f"- scientific_validated_claimed: `{payload.get('scientific_validated_claimed')}`",
        "",
        "## Algebraic identities",
        "",
    ]
    for item in payload.get("algebraic_identities") or []:
        lines.append(f"- {item}")
    lines.extend(["", "## Numerical tolerance dependencies", ""])
    for item in payload.get("numerical_tolerance_dependencies") or []:
        lines.append(f"- {item}")
    lines.extend(["", "## Fixture summaries", ""])
    for row in payload.get("fixtures") or []:
        lines.append(
            f"- `{row.get('name')}` ({row.get('boundary_class')}): "
            f"incidence_ok={row.get('incidence_ok')} "
            f"decomp_verdict={row.get('decomp_verdict')} "
            f"cond_L0={row.get('cond_L0')} "
            f"harmonic_energy={row.get('energy_harmonic')}"
        )
    lines.extend(
        [
            "",
            "## Limitations",
            "",
            "- Synthetic fixtures only; HOLD / SYNTHETIC_ONLY.",
            "- Proposed engine in open PR #385 was not imported; this audit does not claim that proposal passed.",
            "- Mesh/Delaunay/finite-jitter validity is out of scope.",
            "",
        ]
    )
    p.write_text("\n".join(lines), encoding="utf-8")
    return str(p)
