"""Read-only license evidence reconciliation.

This module records what each source says. It never selects a license and never claims a
conflict is resolved. Unknown text, missing fields, and contradictory tokens all leave the
state open. Agreement between sources is recorded, but it is not a legal adjudication.
"""
from __future__ import annotations

import re
from typing import Any, Iterable, Mapping, Optional

from .findings import make_finding

# Closed set of license tokens. Anything not matched here is unrecognized, and it is
# never mapped to the nearest known token.
_TOKEN_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bCC[-\s]?BY[-\s]?SA[-\s]?4\.0\b", re.IGNORECASE), "CC-BY-SA-4.0"),
    (re.compile(r"\bCC[-\s]?BY[-\s]?4\.0\b", re.IGNORECASE), "CC-BY-4.0"),
    (re.compile(r"\bCC0(?:[-\s]?1\.0)?\b", re.IGNORECASE), "CC0-1.0"),
)
_LICENSE_WORD = re.compile(r"licen[cs]", re.IGNORECASE)
LICENSE_FIELD_NAMES: tuple[str, ...] = ("License", "license", "Licence", "licence")


def tokens_in(text: str) -> set[str]:
    return {token for pattern, token in _TOKEN_PATTERNS if pattern.search(text)}


def readme_evidence(text: Optional[str]) -> dict[str, Any]:
    """Tokens from lines that mention a license. Other lines are ignored, so a stray CC0 elsewhere cannot count."""
    if text is None:
        return {"source": "readme", "status": "NOT_PROVIDED", "tokens": []}
    if not isinstance(text, str):
        return {"source": "readme", "status": "NOT_TEXT", "tokens": []}
    statement_lines = [line for line in text.splitlines() if _LICENSE_WORD.search(line)]
    if not statement_lines:
        return {"source": "readme", "status": "NO_LICENSE_STATEMENT", "tokens": []}
    tokens: set[str] = set()
    for line in statement_lines:
        tokens |= tokens_in(line)
    if not tokens:
        return {"source": "readme", "status": "UNRECOGNIZED_LICENSE_TEXT", "tokens": []}
    if len(tokens) > 1:
        return {"source": "readme", "status": "CONFLICT_WITHIN_SOURCE", "tokens": sorted(tokens)}
    return {"source": "readme", "status": "RECOGNIZED", "tokens": sorted(tokens)}


def metadata_evidence(metadata: Optional[Mapping[str, Any]], source: str = "metadata") -> dict[str, Any]:
    """Tokens from a metadata mapping's license field. Unknown field names are not guessed.

    ``source`` names the record the mapping came from, so a disagreement can be traced back to it.
    """
    if metadata is None:
        return {"source": source, "status": "NOT_PROVIDED", "tokens": []}
    if not isinstance(metadata, Mapping):
        return {"source": source, "status": "NOT_TEXT", "tokens": []}
    present = [name for name in LICENSE_FIELD_NAMES if name in metadata]
    if not present:
        return {"source": source, "status": "NO_LICENSE_FIELD", "tokens": []}
    if not all(isinstance(metadata[name], str) for name in present):
        return {"source": source, "status": "NOT_TEXT", "tokens": []}
    tokens: set[str] = set()
    for name in present:
        tokens |= tokens_in(metadata[name])
    if not tokens:
        return {"source": source, "status": "UNRECOGNIZED_LICENSE_TEXT", "tokens": []}
    if len(tokens) > 1:
        return {"source": source, "status": "CONFLICT_WITHIN_SOURCE", "tokens": sorted(tokens)}
    return {"source": source, "status": "RECOGNIZED", "tokens": sorted(tokens)}


def reconcile_license(evidence: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Summarize source evidence without choosing between sources."""
    sources = list(evidence)
    provided = [item for item in sources if item["status"] != "NOT_PROVIDED"]
    all_tokens = sorted({token for item in provided for token in item["tokens"]})
    unresolved = [item for item in provided if item["status"] != "RECOGNIZED"]
    recognized = [item for item in provided if item["status"] == "RECOGNIZED"]

    if not provided:
        state = "UNKNOWN"
    elif len(all_tokens) > 1:
        state = "CONFLICT_UNRESOLVED"
    elif unresolved:
        state = "UNRESOLVED"
    elif len(recognized) == 1:
        state = "SINGLE_SOURCE_NOT_ADJUDICATED"
    elif recognized:
        state = "AGREEMENT_NOT_ADJUDICATED"
    else:
        state = "UNKNOWN"

    findings = []
    if state == "CONFLICT_UNRESOLVED":
        findings.append(make_finding(
            "LICENSE_CONFLICT_UNRESOLVED", "error",
            f"sources name different license tokens {all_tokens}; no source is preferred"))
    elif state == "UNRESOLVED":
        findings.append(make_finding(
            "LICENSE_UNRESOLVED", "warning",
            "at least one source has no recognized license statement"))
    elif state == "UNKNOWN":
        findings.append(make_finding("LICENSE_UNKNOWN", "warning", "no license evidence was provided"))
    else:
        findings.append(make_finding(
            "LICENSE_NOT_ADJUDICATED", "info",
            "sources are consistent, but no legal adjudication was performed"))

    # Which sources name each token. A disagreement is kept in this map, not collapsed into a choice.
    sources_by_token = {
        token: sorted(item["source"] for item in provided if token in item["tokens"]) for token in all_tokens
    }

    return {
        "state": state,
        "tokens": all_tokens,
        "sources_by_token": sources_by_token,
        "sources": sources,
        "resolved": False,
        "adjudicated": False,
        "selected_license": None,
        "legal_adjudication": "NOT_PERFORMED",
        "findings": findings,
    }


def license_report(
    readme_text: Optional[str],
    nemar_metadata: Optional[Mapping[str, Any]],
    *,
    dataset_description: Optional[Mapping[str, Any]] = None,
    catalog_metadata: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    """Reconcile four license sources. Every source is recorded and none is preferred."""
    return reconcile_license([
        readme_evidence(readme_text),
        metadata_evidence(nemar_metadata, "nemar_metadata"),
        metadata_evidence(dataset_description, "dataset_description"),
        metadata_evidence(catalog_metadata, "catalog_metadata"),
    ])
