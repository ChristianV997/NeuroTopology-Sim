"""Evaluator-input surface: loading and canonicalising research-plan records.

The only thing this module produces for the rubric is a
:class:`tools.research_plan_quality.models.ResearchPlan`. Label-like keys are
rejected, and the label file is never opened here.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import math
import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Mapping

from tools.research_plan_quality.models import EVIDENCE_CLASSES, ResearchPlan

from .errors import MalformedRecordError

FORBIDDEN_LABEL_KEYS: frozenset[str] = frozenset({
    "expected_overall_status",
    "expected_non_passing_dimensions",
    "expected_criteria",
    "adjudication",
    "adjudicator",
    "target_score",
    "target_scores",
    "answer_key",
    "gold_label",
    "criterion_labels",
    "overall_status",
    "overall_score",
})

TEXT_FIELDS: tuple[str, ...] = (
    "research_question",
    "falsifiability_criteria",
    "primary_endpoint",
    "claim_language",
)

NORMALIZATION_VERSION = "nfkc-casefold-word-chars-ws-v1"


@dataclass(frozen=True)
class PlanRecord:
    fixture_id: str
    group_id: str
    split: str
    plan: ResearchPlan


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False)


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _reject_non_finite(token: str) -> None:
    raise MalformedRecordError(f"non-finite JSON constant {token!r} is not allowed")


def parse_json_bytes(raw: bytes, source: str) -> Any:
    try:
        return json.loads(raw.decode("utf-8"), parse_constant=_reject_non_finite)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MalformedRecordError(f"{source}: not valid UTF-8 JSON ({exc})") from exc


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


_KIND_TEXT: dict[str, str] = {
    "str": "a string",
    "number": "a finite number",
    "int": "an integer",
    "bool": "a boolean",
    "str_list": "a list of strings",
}

# Declared kind of each optional nested field (see tools/research_plan_quality/models.py).
_NESTED_FIELDS: dict[str, dict[str, str]] = {
    "power_analysis": {"method": "str", "target_power": "number", "effect_size": "number", "alpha": "number"},
    "null_model": {"method": "str", "description": "str"},
    "split_strategy": {"unit": "str", "method": "str"},
    "compute_budget": {"estimated_hours": "number", "hardware": "str"},
    "reproducibility": {"seed": "int", "code_version": "str", "environment_pinned": "bool"},
    "ethics_privacy": {"irb_status": "str", "privacy_measures": "str_list"},
}
_SOURCE_FIELDS: dict[str, str] = {"title": "str", "identifier": "str", "verification_status": "str"}


def _matches(value: Any, kind: str) -> bool:
    if kind == "str":
        return isinstance(value, str)
    if kind == "number":
        return _is_number(value)
    if kind == "int":
        return isinstance(value, int) and not isinstance(value, bool)
    if kind == "bool":
        return isinstance(value, bool)
    if kind == "str_list":
        return isinstance(value, list) and all(isinstance(v, str) for v in value)
    raise ValueError(f"unknown kind {kind!r}")


def _type_errors(data: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []

    def expect(name: str, ok: bool, what: str) -> None:
        if not ok:
            errors.append(f"{name} must be {what}")

    for name in ("plan_id", "research_question", "falsifiability_criteria", "primary_endpoint", "claim_language"):
        if name in data:
            expect(name, isinstance(data[name], str), "a string")
    for name in ("secondary_endpoints", "alternative_explanations", "condition_labels",
                 "leakage_controls", "known_leakage_risks", "preprocessing_steps", "measurement_limitations"):
        if name in data and data[name] is not None:
            value = data[name]
            expect(name, isinstance(value, list) and all(isinstance(v, str) for v in value), "a list of strings")
    for name in ("sample_size", "minimum_required_sample_size", "number_of_planned_tests"):
        if name in data and data[name] is not None:
            expect(name, isinstance(data[name], int) and not isinstance(data[name], bool), "an integer")
    for name in ("dataset_id", "dataset_checksum", "pairing_strategy", "multiplicity_correction", "replication_plan"):
        if name in data and data[name] is not None:
            expect(name, isinstance(data[name], str), "a string")
    if data.get("preprocessing_locked_before_analysis") is not None:
        expect("preprocessing_locked_before_analysis",
               isinstance(data["preprocessing_locked_before_analysis"], bool), "a boolean")
    definitions = data.get("condition_label_definitions")
    if definitions is not None:
        if isinstance(definitions, dict) and all(isinstance(v, str) for v in definitions.values()):
            declared = data.get("condition_labels") or []
            undeclared = sorted(k for k in definitions if k not in declared)
            if undeclared:
                errors.append(f"condition_label_definitions names undeclared conditions: {undeclared}")
        else:
            errors.append("condition_label_definitions must map condition names to strings")
    if data.get("evidence_class_declared") not in (None, *sorted(EVIDENCE_CLASSES)):
        errors.append(f"evidence_class_declared must be one of {sorted(EVIDENCE_CLASSES)} or null")
    if "sources" in data:
        sources = data["sources"]
        if not (isinstance(sources, list) and all(isinstance(s, dict) for s in sources)):
            errors.append("sources must be a list of objects")
        else:
            for index, source in enumerate(sources):
                for key, kind in _SOURCE_FIELDS.items():
                    if source.get(key) is not None:
                        expect(f"sources[{index}].{key}", _matches(source[key], kind), _KIND_TEXT[kind])
    for name, fields in _NESTED_FIELDS.items():
        value = data.get(name)
        if value is None:
            continue
        if not isinstance(value, dict):
            errors.append(f"{name} must be an object or null")
            continue
        for key, kind in fields.items():
            if value.get(key) is not None:
                expect(f"{name}.{key}", _matches(value[key], kind), _KIND_TEXT[kind])
    return errors


def _label_key_paths(obj: Any, path: str = "$") -> list[str]:
    found: list[str] = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            here = f"{path}.{key}"
            if key in FORBIDDEN_LABEL_KEYS:
                found.append(here)
            found.extend(_label_key_paths(value, here))
    elif isinstance(obj, list):
        for index, value in enumerate(obj):
            found.extend(_label_key_paths(value, f"{path}[{index}]"))
    return found


def plan_from_dict(data: Any, source: str) -> ResearchPlan:
    if not isinstance(data, dict):
        raise MalformedRecordError(f"{source}: plan record must be a JSON object")
    forbidden = _label_key_paths(data)
    if forbidden:
        raise MalformedRecordError(f"{source}: label-like keys are not allowed in plan records: {forbidden}")
    errors = _type_errors(data)
    if errors:
        raise MalformedRecordError(f"{source}: " + "; ".join(errors))
    try:
        return ResearchPlan.from_dict(data)
    except (TypeError, ValueError) as exc:
        raise MalformedRecordError(f"{source}: {exc}") from exc


def canonical_content(plan: ResearchPlan) -> dict[str, Any]:
    """Everything except the identifier, so relabelled copies still match."""
    content = dataclasses.asdict(plan)
    content.pop("plan_id", None)
    return content


def exact_fingerprint(plan: ResearchPlan) -> str:
    return sha256_hex(canonical_json(canonical_content(plan)).encode("utf-8"))


def normalize_text(text: str) -> str:
    folded = unicodedata.normalize("NFKC", text).casefold()
    words = re.sub(r"[\W_]+", " ", folded)
    return " ".join(words.split())


def normalized_fingerprint(plan: ResearchPlan) -> str:
    joined = "\x1f".join(normalize_text(getattr(plan, name) or "") for name in TEXT_FIELDS)
    return sha256_hex(joined.encode("utf-8"))


def shingles(plan: ResearchPlan, size: int) -> frozenset[str]:
    tokens = normalize_text(f"{plan.research_question} {plan.primary_endpoint}").split()
    if not tokens:
        return frozenset()
    if len(tokens) < size:
        return frozenset({" ".join(tokens)})
    return frozenset(" ".join(tokens[i:i + size]) for i in range(len(tokens) - size + 1))


def jaccard(left: frozenset[str], right: frozenset[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)
