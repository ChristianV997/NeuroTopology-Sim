"""Strict finite JSON and Markdown reports for EvidencePromotionGate.v1."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from tools.evidence_promotion_gate.evaluator import evaluate_path
from tools.evidence_promotion_gate.schema import SCHEMA_VERSION, PromotionResult


class NonFiniteValueError(ValueError):
    """Raised when a payload contains NaN or Infinity."""


def _check_finite(obj: Any, path: str = "$") -> None:
    if isinstance(obj, float):
        if not math.isfinite(obj):
            raise NonFiniteValueError(f"non-finite float at {path}: {obj!r}")
        return
    if isinstance(obj, Mapping):
        for key, value in obj.items():
            _check_finite(value, f"{path}.{key}")
        return
    if isinstance(obj, (list, tuple)):
        for index, value in enumerate(obj):
            _check_finite(value, f"{path}[{index}]")


def json_safe(value: Any) -> Any:
    _check_finite(value)
    return value


def serialize_json(payload: Any, *, indent: int | None = 2) -> str:
    _check_finite(payload)
    return json.dumps(payload, allow_nan=False, sort_keys=True, indent=indent) + "\n"


def results_payload(results: Sequence[PromotionResult]) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "scientific_pass": False,
        "case_count": len(results),
        "results": [result.to_dict() for result in results],
    }


def render_markdown(payload: Mapping[str, Any]) -> str:
    lines = [
        "# Evidence promotion gate report",
        "",
        "This is a reporting/promotion gate, not scientific confirmation.",
        "Synthetic, proxy, and literature-hypothesis records stay non-empirical.",
        "`scientific_pass` is always false. Missing metrics are JSON null.",
        "",
        f"- schema: `{payload.get('schema_version')}`",
        f"- cases: `{payload.get('case_count')}`",
        f"- scientific_pass: `{payload.get('scientific_pass')}`",
        "",
        "| Case | Decision | Declared class | Allowed class | Synthetic | Reasons |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for result in payload.get("results", []):
        reasons = ", ".join(result.get("reason_codes") or [])
        lines.append(
            "| {case} | `{decision}` | `{declared}` | `{allowed}` | `{synthetic}` | {reasons} |".format(
                case=result.get("case_id"),
                decision=result.get("promotion_decision"),
                declared=result.get("declared_evidence_class"),
                allowed=result.get("allowed_evidence_class"),
                synthetic=result.get("synthetic_demo"),
                reasons=reasons,
            )
        )
    lines.extend(["", "No Q/Qabs/fdress proof, TOE, clinical, or consciousness claim is made.", ""])
    return "\n".join(lines)


def evaluate_and_report(input_path: Path) -> dict[str, Any]:
    results = evaluate_path(input_path)
    return results_payload(results)


def write_report(payload: Mapping[str, Any], output: Path) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    text = serialize_json(payload)
    output.write_text(text, encoding="utf-8")
    return output


def write_markdown(payload: Mapping[str, Any], output: Path) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_markdown(payload), encoding="utf-8")
    return output


def blocking_exit_code(payload: Mapping[str, Any]) -> int:
    results: Iterable[Mapping[str, Any]] = payload.get("results") or []
    if not results:
        return 2
    if any(item.get("promotion_decision") == "BLOCK_PROMOTION" for item in results):
        return 1
    return 0
