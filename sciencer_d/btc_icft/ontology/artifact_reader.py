"""
Ontology artifact reader (O4 / P24.1).

Loads ontology evaluation outputs and provides safe summaries for downstream
publication tools. Returns a "not_available" placeholder if outputs are absent
so callers degrade gracefully.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional, Union


_NOT_AVAILABLE: dict = {
    "ontology_available": False,
    "max_claim_scope": "engineering_runtime",
    "promotion_state": "engineering_validated",
    "ontology_claim_status": "ontology_quarantined",
    "ontology_promotion": False,
    "empirical_marker_promotion": False,
    "empirical_topology_promotion": False,
    "mechanism_promotion": False,
    "metaphysical_promotion": False,
    "bridge_status_counts": {},
    "blocked_claims": [],
    "safe_claim": (
        "Ontology evaluation not yet available. "
        "Engineering runtime validation only."
    ),
    "required_next_evidence": [
        "run_ds005620_ontology_eval_mock",
    ],
}


def _resolve_eval_path(root_or_path: Union[str, Path]) -> Optional[Path]:
    """Resolve to the ontology_claim_evaluation.json path, or None."""
    p = Path(root_or_path)
    if p.is_file() and p.name == "ontology_claim_evaluation.json":
        return p
    candidate = p / "ontology_claim_evaluation.json"
    if candidate.exists():
        return candidate
    return None


def _load_json_safe(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def load_ontology_evaluation(root_or_path: Union[str, Path]) -> dict:
    """Load ontology_claim_evaluation.json. Returns {} if missing."""
    p = _resolve_eval_path(root_or_path)
    if p is None:
        return {}
    return _load_json_safe(p)


def load_ontology_promotion_decision(root_or_path: Union[str, Path]) -> dict:
    """Load ontology_promotion_decision.json. Returns {} if missing."""
    p = Path(root_or_path)
    if p.is_file():
        p = p.parent
    candidate = p / "ontology_promotion_decision.json"
    return _load_json_safe(candidate)


def load_claim_scope_matrix(root_or_path: Union[str, Path]) -> dict:
    """Load claim_scope_matrix.json. Returns {} if missing."""
    p = Path(root_or_path)
    if p.is_file():
        p = p.parent
    candidate = p / "claim_scope_matrix.json"
    return _load_json_safe(candidate)


def load_bridge_claim_status(root_or_path: Union[str, Path]) -> dict:
    """Load bridge_claim_status.json. Returns {} if missing."""
    p = Path(root_or_path)
    if p.is_file():
        p = p.parent
    candidate = p / "bridge_claim_status.json"
    return _load_json_safe(candidate)


def summarize_ontology_for_packet(root_or_path: Union[str, Path]) -> dict:
    """Return a JSON-serializable ontology summary for the evidence packet.

    Returns a safe "not_available" dict if ontology outputs are absent.
    """
    eval_path = _resolve_eval_path(root_or_path)
    if eval_path is None:
        return dict(_NOT_AVAILABLE)

    ev = _load_json_safe(eval_path)
    if not ev:
        return dict(_NOT_AVAILABLE)

    root = eval_path.parent
    promotion = _load_json_safe(root / "ontology_promotion_decision.json")
    bridge_status = _load_json_safe(root / "bridge_claim_status.json")

    bridge_statuses: list[dict] = bridge_status.get("bridge_statuses", [])
    status_counts: dict[str, int] = {}
    for bs in bridge_statuses:
        s = bs.get("status", "unknown")
        status_counts[s] = status_counts.get(s, 0) + 1

    blocked_claims: list[str] = [
        c["claim_id"]
        for c in ev.get("claims", [])
        if not c.get("allowed", True)
    ]

    required_next: list[str] = list(ev.get("blockers", []))

    return {
        "ontology_available": True,
        "max_claim_scope": ev.get("max_claim_scope", "engineering_runtime"),
        "promotion_state": ev.get("promotion_state", "engineering_validated"),
        "ontology_claim_status": ev.get("ontology_claim_status", "ontology_quarantined"),
        "ontology_promotion": bool(promotion.get("ontology_promotion", False)),
        "empirical_marker_promotion": bool(promotion.get("empirical_marker_promotion", False)),
        "empirical_topology_promotion": bool(promotion.get("empirical_topology_promotion", False)),
        "mechanism_promotion": bool(promotion.get("mechanism_promotion", False)),
        "metaphysical_promotion": bool(promotion.get("metaphysical_promotion", False)),
        "bridge_status_counts": status_counts,
        "blocked_claims": blocked_claims,
        "safe_claim": ev.get("safe_claim", _NOT_AVAILABLE["safe_claim"]),
        "required_next_evidence": required_next,
    }


def summarize_ontology_for_markdown(root_or_path: Union[str, Path]) -> str:
    """Return a Markdown section summarizing the ontology evaluation status."""
    summary = summarize_ontology_for_packet(root_or_path)

    if not summary["ontology_available"]:
        return (
            "## Ontology Claim Scope\n\n"
            "Ontology evaluation output not yet available.\n\n"
            "- Run `make ds005620-ontology-eval-mock` to generate.\n"
            "- Until then, claim scope is capped at `engineering_runtime`.\n"
        )

    lines = [
        "## Ontology Claim Scope",
        "",
        f"- **Max claim scope:** `{summary['max_claim_scope']}`",
        f"- **Promotion state:** `{summary['promotion_state']}`",
        f"- **Ontology claim status:** `{summary['ontology_claim_status']}`",
        "",
        "### Promotion Flags (all must be false for engineering-only run)",
        "",
        f"- `ontology_promotion`: {summary['ontology_promotion']}",
        f"- `empirical_marker_promotion`: {summary['empirical_marker_promotion']}",
        f"- `empirical_topology_promotion`: {summary['empirical_topology_promotion']}",
        f"- `mechanism_promotion`: {summary['mechanism_promotion']}",
        f"- `metaphysical_promotion`: {summary['metaphysical_promotion']}",
        "",
        "### Bridge Status Summary",
        "",
    ]
    if summary["bridge_status_counts"]:
        for status, count in sorted(summary["bridge_status_counts"].items()):
            lines.append(f"- `{status}`: {count} bridge(s)")
    else:
        lines.append("- (no bridge statuses available)")

    lines += [
        "",
        "### Blocked Claims",
        "",
    ]
    if summary["blocked_claims"]:
        for c in summary["blocked_claims"]:
            lines.append(f"- `{c}`")
    else:
        lines.append("- (none blocked)")

    lines += [
        "",
        "### Required Next Evidence",
        "",
    ]
    if summary["required_next_evidence"]:
        for e in summary["required_next_evidence"]:
            lines.append(f"- {e}")
    else:
        lines.append("- (no additional evidence required at current scope)")

    lines += [
        "",
        "### Safe Claim",
        "",
        summary["safe_claim"],
        "",
    ]

    return "\n".join(lines)
