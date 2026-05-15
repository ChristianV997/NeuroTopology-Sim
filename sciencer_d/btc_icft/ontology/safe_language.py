"""
Safe language firewall (O1).

Scans generated ontology text and structures for forbidden overclaim
substrings. Operates case-insensitively on normalized whitespace.
"""
from __future__ import annotations

import re
from typing import Any


FORBIDDEN_ONTOLOGY_PHRASES: list[str] = [
    "proves consciousness",
    "consciousness proven",
    "soul proven",
    "afterlife proven",
    "liberation detected",
    "ontology solved",
    "ultimate reality",
    "q equals self",
    "q equals soul",
    "q_abs equals suffering",
    "f_dress equals karma",
    "sedated implies no_experience",
    "unresponsive implies unconscious",
    "topology proves liberation",
    "eeg proves consciousness",
]


ALLOWED_SAFE_PHRASES: list[str] = [
    "engineering runtime validation",
    "reviewed-label benchmark",
    "marker association",
    "topology telemetry",
    "residual predictive value",
    "bridge hypothesis",
    "mechanism candidate",
    "theory consistency",
    "ontology candidate remains quarantined",
    "blocked pending controls",
    "blocked pending real execution",
    "blocked pending human review",
]


_WHITESPACE = re.compile(r"\s+")


def normalize_text(text: str) -> str:
    return _WHITESPACE.sub(" ", text or "").strip().lower()


def find_forbidden_phrases(text: str) -> list[str]:
    if not text:
        return []
    norm = normalize_text(text)
    found: list[str] = []
    for phrase in FORBIDDEN_ONTOLOGY_PHRASES:
        if phrase in norm:
            found.append(phrase)
    return found


def validate_safe_text(text: str) -> list[str]:
    """Return list of forbidden phrase hits found in text. Empty = safe."""
    return find_forbidden_phrases(text)


def validate_json_safe_text(obj: Any) -> list[str]:
    """Recursively scan a JSON-like structure and return all forbidden hits."""
    hits: list[str] = []
    if isinstance(obj, str):
        hits.extend(find_forbidden_phrases(obj))
    elif isinstance(obj, dict):
        for k, v in obj.items():
            hits.extend(find_forbidden_phrases(str(k)))
            hits.extend(validate_json_safe_text(v))
    elif isinstance(obj, (list, tuple)):
        for item in obj:
            hits.extend(validate_json_safe_text(item))
    return hits
