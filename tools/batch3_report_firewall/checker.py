"""Deterministic, advisory checks for explicitly selected Markdown/JSON reports.

This module reports possible language/status mismatches for human review. It
does not validate evidence, promote claims, rewrite reports, or execute content.
"""
from __future__ import annotations

import json
import re
from pathlib import Path, PureWindowsPath
from typing import Any, Iterable, Mapping

from shared.research_claims import language_rules as claim_language_rules

SCHEMA_VERSION = "Batch3ReportLanguageFindings.v1"
MAX_SELECTED_FILES = 100
MAX_FILE_BYTES = 2_000_000
MAX_TOTAL_BYTES = 10_000_000
MAX_JSON_DEPTH = 64

_SYNTHETIC_TERMS = r"synthetic|fixture|mock|surrogate|simulat(?:ed|ion)|dry[- ]run|performance[- ]only"
_EMPIRICAL_TERMS = r"empirical|real[- ]world|real data|actual data|biological|biology|clinical|in vivo|participant|cohort"
_ASSERTION_VERBS = r"is|are|was|were|as|presented as|labelled as|labeled as|reported as|shows?|demonstrates?|confirms?|proves?|validates?|establishes?|supports?"
_SYNTHETIC_ASSERTION = re.compile(
    rf"\b(?:{_SYNTHETIC_TERMS})\b.{{0,100}}\b(?:{_ASSERTION_VERBS})\b.{{0,80}}\b(?:{_EMPIRICAL_TERMS})\b"
    rf"|\b(?:{_EMPIRICAL_TERMS})\b.{{0,80}}\b(?:{_ASSERTION_VERBS})\b.{{0,100}}\b(?:{_SYNTHETIC_TERMS})\b",
    re.IGNORECASE,
)
_PROMOTION_ASSERTION = re.compile(
    rf"\b(?:is|are|was|were|classified as|presented as|labelled as|labeled as|reported as|"
    rf"proves?|confirms?|validates?|establishes?|demonstrates?|shows?|supports?)\b"
    rf".{{0,70}}\b(?:{_EMPIRICAL_TERMS}|mechanis\w*|causal\w*)\b",
    re.IGNORECASE,
)
_ENGINEERING_TERMS = r"software|engineering|static checks?|unit tests?|conformance|compilation|ci checks?|schema checks?|code tests?"
_BIOLOGICAL_TERMS = r"biology|biological|in vivo|clinical|participant|mechanis\w*|causal\w*"
_ENGINEERING_PROMOTION = re.compile(
    rf"\b(?:{_ENGINEERING_TERMS})\b.{{0,80}}\b(?:{_ASSERTION_VERBS}|certifies?|validates?)\b.{{0,80}}\b(?:{_BIOLOGICAL_TERMS})\b"
    rf"|\b(?:{_BIOLOGICAL_TERMS})\b.{{0,80}}\b(?:{_ASSERTION_VERBS}|certifies?)\b.{{0,80}}\b(?:{_ENGINEERING_TERMS})\b",
    re.IGNORECASE,
)
_CAUSAL_ASSERTION = re.compile(
    r"\b(?:causes?|caused|causing|drives?|driven|produces?|produced)\b"
    r"|\b(?:proves?|confirms?|demonstrates?|establishes?)\b.{0,60}\b(?:causal(?:ity| effect)?|mechanis\w*)\b"
    r"|\b(?:the|this|a)\s+(?:biological\s+)?mechanis\w*\s+(?:is|was|has been|drives?|causes?)\b",
    re.IGNORECASE,
)
_REPLICATION_ASSERTION = re.compile(
    r"\b(?:replicat(?:ed|es|ing|ion)|reproduc(?:ed|es|ing|tion))\b",
    re.IGNORECASE,
)
_CAUTIOUS_WORDING = re.compile(
    r"\b(?:hypothes\w*|may|might|could|potential(?:ly)?|candidate|proposed|suggests?|"
    r"associated with|correlated with|consistent with|appears?|seems?|planned|future|awaiting)\b",
    re.IGNORECASE,
)
_NEGATED_ASSERTION = re.compile(
    r"\b(?:not|never|cannot|can't|doesn't|don't|didn't|does not|do not|did not|"
    r"isn't|aren't|wasn't|weren't|is not|are not|was not|were not|without|no)\b"
    r".{0,100}\b(?:empirical|real[- ]world|biolog\w*|clinical|in vivo|participant|cohort|"
    r"caus\w*|mechanis\w*|replicat\w*|reproduc\w*|validat\w*|confirm\w*|proven|proof)\b",
    re.IGNORECASE,
)
_ABSENT_EVIDENCE = re.compile(
    r"\b(?:empirical|independent|causal|mechanistic|biological|replication|evidence)\b"
    r".{0,50}\b(?:absent|missing|lacking|unavailable|not provided|not available)\b",
    re.IGNORECASE,
)
_INDEPENDENT_EVIDENCE = re.compile(
    r"\b(?:independent(?:ly)?\s+(?:cohort|site|study|replication|replicated|lab|sample)|"
    r"separate\s+(?:cohort|site|study|lab)|external\s+replication)\b",
    re.IGNORECASE,
)
_REFERENCE = re.compile(
    r"\bdoi\s*:\s*10\.\d{4,9}/\S+|https?://\S+|"
    r"\[[A-Za-z0-9][A-Za-z0-9_.:-]{0,40}\](?:\(https?://[^)]+\))?|"
    r"\bevidence[_ -]?(?:id|ref(?:erence)?)\s*[:=]\s*\S+",
    re.IGNORECASE,
)
_AMBIGUOUS_STATUS_TEXT = re.compile(
    r"\b(?:status|scientific status|promotion state|result state)\s*[:=\-–—]\s*\*{0,2}\s*[`\"']*"
    r"(?:validated|scientifically validated|biologically validated|empirically validated)\b",
    re.IGNORECASE,
)
_STATUS_KEYS = {
    "status", "validation_status", "promotion_state", "scientific_status", "result_state",
    "evidence_state", "evidence_status", "evidence_decision", "promotion_decision",
}
_EVIDENCE_KEYS = {
    "data_mode", "evidence_class", "empirical_synthetic_status", "synthetic", "is_synthetic",
    "claim_category", "claim_class", "claim_status", "evidence_type",
}
_CONTEXT_OVERRIDE_KEYS = {
    "data_mode", "evidence_class", "empirical_synthetic_status", "synthetic", "is_synthetic", "evidence_type",
}
_EMPIRICAL_CLASSES = {"empirical", "empirical_observation", "descriptive_empirical", "formal_statistical_evidence"}
_SYNTHETIC_CLASSES = {
    "synthetic", "synthetic_demo", "synthetic_demo_only", "synthetic_demonstration", "synthetic_only",
    "hold_synthetic_only", "fixture", "fixture_only", "mock", "mock_only", "surrogate", "dry_run", "performance_only",
}
_REFERENCE_KEYS = {
    "evidence_reference", "evidence_references", "evidence_ref", "evidence_refs", "evidence_id", "evidence_ids",
    "source_reference", "source_references", "source_id", "source_ids", "source_uri", "source_url", "citation",
    "citations", "doi", "provenance_reference",
}
_NON_ASSERTION_KEYS = {
    "quote", "quoted_text", "quotation", "source_quote", "verbatim", "verbatim_quote", "fixture", "fixtures",
    "test_fixture", "test_fixtures", "examples", "example_output", "known_bad_examples",
    "forbidden_phrases", "banned_phrases", "limitations",
    "limitation", "caveats", "guardrails",
}
_METADATA_TEXT_KEYS = _STATUS_KEYS | _EVIDENCE_KEYS | {"scientific_pass", "formal_bayes_factor"}
_NEGATION_CLAUSE_SPLIT = re.compile(
    r"(?<=[.!?;])\s+|,\s+(?=(?:the|this|these|those|it|they|we|results?|findings?|analysis|"
    r"intervention|model|data|output|evidence|claim|report)\b)|"
    r"\s+\b(?:and|but|or|nor|yet|whereas|while|although|though)\b\s+",
    re.IGNORECASE,
)
_MARKDOWN_LIMITATION_HEADINGS = {"limitations", "caveats", "guardrails", "what this does not claim", "what cannot be claimed"}
_FIXTURE_HEADINGS = {"test fixture", "test fixtures", "fixtures", "examples", "quoted examples", "forbidden examples"}
_TOP_LEVEL_CONTEXT = re.compile(r"^(?:synthetic|empirical|biological|engineering|software|causal|replication)\b", re.IGNORECASE)
_RECOMMENDATIONS = {
    "PROJECT_CLAIM_CEILING": "Have a reviewer confirm the statement is an assertion and check it against the established claim ceiling; this finding is not a scientific assessment.",
    "SYNTHETIC_TO_EMPIRICAL_ASSERTION": "Review the evidence class and wording together; synthetic or fixture output must not be presented as empirical evidence.",
    "ENGINEERING_TO_BIOLOGICAL_VALIDATION": "Review whether software conformance is being described as biological or empirical validation; static success does not promote scientific evidence.",
    "UNSUPPORTED_CAUSAL_OR_MECHANISTIC_CLAIM": "Have a domain reviewer inspect the claim and its evidence; this checker cannot establish or rule out causality or mechanism.",
    "REPLICATION_WITHOUT_INDEPENDENT_EVIDENCE": "Verify an independently sourced cohort/site and evidence reference before presenting replication as established.",
    "AMBIGUOUS_VALIDATION_STATUS": "Name what was validated and whether the scope is engineering, data, or scientific; do not infer a scientific conclusion from this label.",
    "STRUCTURED_EVIDENCE_STATUS_MISMATCH": "Review the structured evidence and claim fields for a scope mismatch; this advisory check does not alter either field.",
    "SCIENTIFIC_PASS_FIELD_TRUE": "Have a reviewer inspect this declaration against the evidence gate; this checker does not grant or validate a scientific pass.",
    "MISSING_EVIDENCE_REFERENCE": "Add or verify a traceable evidence reference, or qualify the statement; reference presence alone is not evidence validation.",
    "REPORT_NOT_PARSEABLE": "Review the selected report format; content-level checks were not performed for this file.",
    "REPORT_STRUCTURE_TOO_DEEP": "Review or simplify this JSON structure; deeper content was not inspected.",
}


class InputSelectionError(ValueError):
    """Raised when selected report paths are outside the safe bounded input set."""


def _normal(value: Any) -> str:
    return str(value).strip().lower().replace("-", "_").replace(" ", "_") if value is not None else ""


def _nonempty(value: Any) -> bool:
    if value is None or value is False:
        return False
    if isinstance(value, str):
        return value.strip().lower() not in {"", "none", "null", "n/a", "unknown", "missing"}
    if isinstance(value, (list, tuple, dict, set)):
        return len(value) > 0
    return True


def _json_location(pointer: str, key: str | int | None = None) -> str:
    if key is None:
        return pointer or "$"
    if isinstance(key, int):
        return f"{pointer}[{key}]"
    escaped = str(key).replace("~", "~0").replace("/", "~1")
    return f"{pointer}/{escaped}" if pointer else f"$/{escaped}"


def _finding(file: str, location: str, rule: str, *, certainty: str = "uncertain", evidence_reference_detected: bool | None = None) -> dict[str, Any]:
    item: dict[str, Any] = {
        "file": file,
        "location": location,
        "rule": rule,
        "severity": "warning",
        "certainty": certainty,
        "recommendation": _RECOMMENDATIONS[rule],
    }
    if evidence_reference_detected is not None:
        item["evidence_reference_detected"] = evidence_reference_detected
    return item


def _finding_sort_key(finding: Mapping[str, Any]) -> tuple[str, tuple[int, int | str], str]:
    location = str(finding["location"])
    line = re.fullmatch(r"L(\d+)", location)
    location_key: tuple[int, int | str] = (0, int(line.group(1))) if line else (1, location)
    return str(finding["file"]), location_key, str(finding["rule"])


def _quote_spans(text: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    pairs = (("\"", "\""), ("“", "”"), ("‘", "’"), ("`", "`"))
    for opening, closing in pairs:
        start = 0
        while True:
            left = text.find(opening, start)
            if left < 0:
                break
            right = text.find(closing, left + len(opening))
            if right < 0:
                break
            spans.append((left, right + len(closing)))
            start = right + len(closing)
    # Pair straight single quotes with a linear scan; apostrophes between word
    # characters (for example, in contractions) are content, not delimiters.
    opening: int | None = None
    for index, char in enumerate(text):
        if char != "'":
            continue
        previous_is_word = index > 0 and (text[index - 1].isalnum() or text[index - 1] == "_")
        next_is_word = index + 1 < len(text) and (text[index + 1].isalnum() or text[index + 1] == "_")
        next_is_space = index + 1 < len(text) and text[index + 1].isspace()
        if opening is None:
            if not previous_is_word and next_is_word:
                opening = index
        elif previous_is_word and next_is_word:
            continue
        elif not next_is_word:
            spans.append((opening, index + 1))
            opening = None
        elif not previous_is_word and not next_is_space:
            # Treat a fresh quote before a word as a new candidate if the
            # previous candidate was unmatched; unmatched text is not hidden.
            opening = index

    merged: list[tuple[int, int]] = []
    for left, right in sorted(spans):
        if merged and left <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], right))
        else:
            merged.append((left, right))
    return merged


def _inside_quote(text: str, start: int, end: int) -> bool:
    return any(start >= left and end <= right for left, right in _quote_spans(text))


def _split_assertion_clauses(text: str) -> list[str]:
    """Split on simple clause boundaries, but never inside a quoted span."""
    clauses: list[str] = []
    start = 0
    quote_spans = _quote_spans(text)
    quote_index = 0
    for separator in _NEGATION_CLAUSE_SPLIT.finditer(text):
        while quote_index < len(quote_spans) and quote_spans[quote_index][1] <= separator.start():
            quote_index += 1
        if (
            quote_index < len(quote_spans)
            and quote_spans[quote_index][0] < separator.end()
            and separator.start() < quote_spans[quote_index][1]
        ):
            continue
        clauses.append(text[start:separator.start()])
        start = separator.end()
    clauses.append(text[start:])
    return clauses


def _has_unquoted_match(pattern: re.Pattern[str], text: str) -> bool:
    quote_spans = _quote_spans(text)
    quote_index = 0
    for match in pattern.finditer(text):
        while quote_index < len(quote_spans) and quote_spans[quote_index][1] <= match.start():
            quote_index += 1
        if (
            quote_index < len(quote_spans)
            and quote_spans[quote_index][0] < match.end()
            and match.start() < quote_spans[quote_index][1]
        ):
            continue
        return True
    return False


def _is_negated_or_limited(text: str) -> bool:
    return _has_unquoted_match(_NEGATED_ASSERTION, text) or _has_unquoted_match(_ABSENT_EVIDENCE, text)


def _is_cautious(text: str) -> bool:
    return _has_unquoted_match(_CAUTIOUS_WORDING, text)


def _has_unqualified_statement(text: str) -> bool:
    clauses = [part.strip() for part in _split_assertion_clauses(text) if part.strip()]
    return any(not _is_negated_or_limited(part) and not _is_cautious(part) for part in clauses)


def _has_reference(text: str, inherited: Mapping[str, Any] | None = None) -> bool:
    if _REFERENCE.search(text):
        return True
    return bool(inherited and any(_nonempty(value) for key, value in inherited.items() if key in _REFERENCE_KEYS))


def _metadata_value(metadata: Mapping[str, Any], keys: Iterable[str]) -> list[str]:
    return [_normal(metadata[key]) for key in keys if key in metadata and _nonempty(metadata[key])]


def _is_synthetic_metadata(metadata: Mapping[str, Any]) -> bool:
    for key in ("synthetic", "is_synthetic"):
        if metadata.get(key) is True:
            return True
        if _normal(metadata.get(key)) in {"true", "yes", "1"}:
            return True
    values = _metadata_value(metadata, ("data_mode", "evidence_class", "empirical_synthetic_status", "evidence_type", *_STATUS_KEYS))
    return any(value in _SYNTHETIC_CLASSES for value in values)


def _is_empirical_metadata(metadata: Mapping[str, Any]) -> bool:
    values = _metadata_value(metadata, ("data_mode", "evidence_class", "empirical_synthetic_status", "claim_category", "claim_class", "claim_status", "evidence_type", *_STATUS_KEYS))
    return any(value in _EMPIRICAL_CLASSES for value in values)


def _reference_fields_present(metadata: Mapping[str, Any]) -> bool:
    return any(key in metadata and _nonempty(metadata[key]) for key in _REFERENCE_KEYS)


def _reference_from_tree(node: Any) -> bool:
    if isinstance(node, Mapping):
        for key, value in node.items():
            name = str(key).lower()
            if name in _REFERENCE_KEYS and _nonempty(value):
                return True
            if name in {"provenance", "sources", "references", "evidence"} and _reference_from_tree(value):
                return True
        return False
    if isinstance(node, list):
        return any(_reference_from_tree(item) for item in node)
    return False


def _check_status_object(
    node: Mapping[str, Any],
    file: str,
    pointer: str,
    findings: list[dict[str, Any]],
    inherited: Mapping[str, Any],
    *,
    depth: int = 0,
) -> None:
    if depth > MAX_JSON_DEPTH:
        findings.append(_finding(file, pointer or "$", "REPORT_STRUCTURE_TOO_DEEP"))
        return
    if node.get("is_fixture") is True or node.get("test_fixture") is True or node.get("fixture") is True:
        return
    local = {str(key).lower(): value for key, value in node.items()}
    effective = dict(inherited)
    if any(key in local for key in _CONTEXT_OVERRIDE_KEYS):
        effective = {key: value for key, value in effective.items() if key not in _CONTEXT_OVERRIDE_KEYS}
    effective.update(local)

    if _is_synthetic_metadata(effective) and _is_empirical_metadata(effective):
        findings.append(_finding(file, pointer or "$", "STRUCTURED_EVIDENCE_STATUS_MISMATCH", certainty="likely"))
    if local.get("scientific_pass") is True:
        findings.append(_finding(file, _json_location(pointer, "scientific_pass"), "SCIENTIFIC_PASS_FIELD_TRUE", certainty="likely"))

    for key in _STATUS_KEYS:
        value = local.get(key)
        if isinstance(value, str) and _normal(value) in {"validated", "scientifically_validated", "biologically_validated", "empirically_validated"}:
            findings.append(_finding(file, _json_location(pointer, key), "AMBIGUOUS_VALIDATION_STATUS"))

    claim_fields = ("claim", "text", "statement", "summary", "conclusion", "result")
    claim_texts = [local[key] for key in claim_fields if isinstance(local.get(key), str) and local[key].strip()]
    declared_empirical = _is_empirical_metadata(effective)
    has_unqualified_text = any(_has_unqualified_statement(value) for value in claim_texts)
    if has_unqualified_text and declared_empirical and not _reference_fields_present(local) and not _reference_from_tree(node):
        findings.append(_finding(file, pointer or "$", "MISSING_EVIDENCE_REFERENCE"))

    child_context = effective
    for key, value in node.items():
        name = str(key).lower()
        if name in _NON_ASSERTION_KEYS:
            continue
        child_pointer = _json_location(pointer, str(key))
        if isinstance(value, Mapping):
            if value.get("is_fixture") is True or value.get("test_fixture") is True or value.get("fixture") is True:
                continue
            _check_status_object(value, file, child_pointer, findings, child_context, depth=depth + 1)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                item_pointer = _json_location(child_pointer, index)
                if isinstance(item, Mapping):
                    if item.get("is_fixture") is True or item.get("test_fixture") is True or item.get("fixture") is True:
                        continue
                    _check_status_object(item, file, item_pointer, findings, child_context, depth=depth + 1)
                elif isinstance(item, str) and name not in _METADATA_TEXT_KEYS:
                    _scan_text(item, file, item_pointer, findings, child_context)
        elif isinstance(value, str) and name not in _METADATA_TEXT_KEYS and name not in _REFERENCE_KEYS:
            _scan_text(value, file, child_pointer, findings, child_context)


def _scan_text(text: str, file: str, location: str, findings: list[dict[str, Any]], metadata: Mapping[str, Any] | None = None, *, heading: str = "") -> None:
    meta = metadata or {}
    inherited_synthetic = _is_synthetic_metadata(meta)
    for clause in _split_assertion_clauses(text):
        clause = clause.strip()
        if not clause or _is_negated_or_limited(clause) or _is_cautious(clause):
            continue
        context = f"{heading} {clause}".strip()
        reference_present = _has_reference(clause, meta)

        ceiling_hits = claim_language_rules.scan_text(clause)
        ceiling_phrases = sorted({phrase for values in ceiling_hits.values() for phrase in values})
        for phrase in ceiling_phrases:
            offset = clause.lower().find(phrase.lower())
            if offset >= 0 and not _inside_quote(clause, offset, offset + len(phrase)):
                findings.append(_finding(file, location, "PROJECT_CLAIM_CEILING", certainty="likely"))
                break

        synth_match = _SYNTHETIC_ASSERTION.search(context)
        contextual_match = inherited_synthetic and _PROMOTION_ASSERTION.search(clause)
        if synth_match or contextual_match:
            if not synth_match or not _inside_quote(context, synth_match.start(), synth_match.end()):
                findings.append(_finding(file, location, "SYNTHETIC_TO_EMPIRICAL_ASSERTION", certainty="likely"))

        engineering_match = _ENGINEERING_PROMOTION.search(clause)
        if engineering_match and not _inside_quote(clause, engineering_match.start(), engineering_match.end()):
            findings.append(_finding(file, location, "ENGINEERING_TO_BIOLOGICAL_VALIDATION", certainty="likely"))

        causal_match = _CAUSAL_ASSERTION.search(clause)
        if causal_match and not _inside_quote(clause, causal_match.start(), causal_match.end()):
            findings.append(_finding(file, location, "UNSUPPORTED_CAUSAL_OR_MECHANISTIC_CLAIM", evidence_reference_detected=reference_present))
            if not reference_present:
                findings.append(_finding(file, location, "MISSING_EVIDENCE_REFERENCE"))

        replication_match = _REPLICATION_ASSERTION.search(clause)
        if replication_match and not _inside_quote(clause, replication_match.start(), replication_match.end()):
            independent = bool(_INDEPENDENT_EVIDENCE.search(clause))
            if not reference_present or not independent:
                findings.append(_finding(file, location, "REPLICATION_WITHOUT_INDEPENDENT_EVIDENCE", evidence_reference_detected=reference_present))
                if not reference_present:
                    findings.append(_finding(file, location, "MISSING_EVIDENCE_REFERENCE"))

    status_match = _AMBIGUOUS_STATUS_TEXT.search(text)
    if status_match and not _inside_quote(text, status_match.start(), status_match.end()):
        findings.append(_finding(file, location, "AMBIGUOUS_VALIDATION_STATUS"))


def _markdown_paragraphs(text: str) -> list[tuple[int, str, str, bool]]:
    paragraphs: list[tuple[int, str, str, bool]] = []
    heading_stack: list[tuple[int, str]] = []
    current: list[str] = []
    current_start = 1
    fenced = False
    fence_marker = ""
    def flush() -> None:
        nonlocal current
        if current:
            body = " ".join(line.strip() for line in current).strip()
            relevant_headings = [
                title for level, title in heading_stack
                if level > 1 or _TOP_LEVEL_CONTEXT.search(title.strip())
            ]
            heading = " > ".join(relevant_headings)
            excluded_section = any(_heading_is_excluded(title) for _, title in heading_stack)
            paragraphs.append((current_start, body, heading, excluded_section))
            current = []

    for line_no, raw in enumerate(text.splitlines(), start=1):
        stripped = raw.strip()
        leading_whitespace = raw[: len(raw) - len(raw.lstrip(" \t"))]
        indented_code = "\t" in leading_whitespace or len(leading_whitespace) >= 4
        fence = re.match(r"^(```+|~~~+)", stripped)
        if fence:
            flush()
            marker = fence.group(1)[0]
            if not fenced:
                fenced = True
                fence_marker = marker
            elif marker == fence_marker:
                fenced = False
                fence_marker = ""
            continue
        if fenced or not stripped or stripped.startswith(">") or indented_code:
            flush()
            continue
        heading = re.match(r"^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$", raw)
        if heading:
            flush()
            level = len(heading.group(1))
            title = heading.group(2).strip()
            while heading_stack and heading_stack[-1][0] >= level:
                heading_stack.pop()
            heading_stack.append((level, title))
            continue
        if not current:
            current_start = line_no
        current.append(raw)
    flush()
    return paragraphs


def _heading_is_excluded(title: str) -> bool:
    lowered = title.lower().strip(" `*_:")
    return any(
        lowered == value or lowered.startswith(value + " ")
        for value in _MARKDOWN_LIMITATION_HEADINGS | _FIXTURE_HEADINGS
    )


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant: {value}")


def _reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _inspect_content(file: str, suffix: str, content: str) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    if suffix == ".md":
        for line, paragraph, heading, excluded in _markdown_paragraphs(content):
            if excluded:
                continue
            for sentence in _split_assertion_clauses(paragraph):
                _scan_text(sentence, file, f"L{line}", findings, heading=heading)
    else:
        try:
            payload = json.loads(
                content,
                parse_constant=_reject_json_constant,
                object_pairs_hook=_reject_duplicate_json_keys,
            )
        except (json.JSONDecodeError, ValueError, RecursionError) as exc:
            return [_finding(file, "$", "REPORT_NOT_PARSEABLE") | {"detail": f"JSON could not be parsed ({type(exc).__name__}); no content-level checks were run."}]
        if isinstance(payload, Mapping):
            _check_status_object(payload, file, "$", findings, {})
        elif isinstance(payload, list):
            for index, item in enumerate(payload):
                if isinstance(item, Mapping):
                    _check_status_object(item, file, f"$[{index}]", findings, {})
                elif isinstance(item, str):
                    _scan_text(item, file, f"$[{index}]", findings)
        elif isinstance(payload, str):
            _scan_text(payload, file, "$", findings)
    return findings


def _select_files(root: Path, paths: Iterable[str | Path]) -> list[tuple[str, Path]]:
    root_input = Path(root)
    if root_input.is_symlink():
        raise InputSelectionError("the bounded root must not be a symlink")
    try:
        bounded_root = root_input.resolve(strict=True)
    except OSError as exc:
        raise InputSelectionError(f"bounded root is unavailable: {exc}") from exc
    if not bounded_root.is_dir():
        raise InputSelectionError("bounded root must be an existing directory")

    selected: dict[str, Path] = {}
    total = 0
    for raw in paths:
        value = str(raw)
        relative = Path(value)
        windows_path = PureWindowsPath(value)
        if relative.is_absolute() or windows_path.is_absolute() or windows_path.drive or any(part == ".." for part in relative.parts) or ".." in windows_path.parts:
            raise InputSelectionError(f"selected path must be relative and must not traverse: {value}")
        if not value or relative == Path("."):
            raise InputSelectionError("select explicit report files; directories are not scanned")
        candidate = bounded_root / relative
        current = bounded_root
        for part in relative.parts:
            if part in {"", "."}:
                continue
            current = current / part
            if current.is_symlink():
                raise InputSelectionError(f"symlink report paths are not accepted: {value}")
        try:
            resolved = candidate.resolve(strict=True)
        except OSError as exc:
            raise InputSelectionError(f"selected report is unavailable ({value}): {exc}") from exc
        try:
            resolved.relative_to(bounded_root)
        except ValueError as exc:
            raise InputSelectionError(f"selected report escapes the bounded root: {value}") from exc
        if not resolved.is_file():
            raise InputSelectionError(f"selected path is not a regular file: {value}")
        if resolved.suffix.lower() not in {".md", ".json"}:
            raise InputSelectionError(f"only explicitly selected Markdown/JSON reports are accepted: {value}")
        rel = resolved.relative_to(bounded_root).as_posix()
        if rel in selected:
            continue
        try:
            size = resolved.stat().st_size
        except OSError as exc:
            raise InputSelectionError(f"selected report is unavailable ({value}): {exc}") from exc
        if size > MAX_FILE_BYTES:
            raise InputSelectionError(f"selected report exceeds the per-file size limit: {value}")
        total += size
        if total > MAX_TOTAL_BYTES:
            raise InputSelectionError("selected reports exceed the total size limit")
        selected[rel] = resolved
        if len(selected) > MAX_SELECTED_FILES:
            raise InputSelectionError(f"no more than {MAX_SELECTED_FILES} report files may be selected")
    if not selected:
        raise InputSelectionError("select at least one report file")
    return sorted(selected.items())


def inspect_reports(root: str | Path, paths: Iterable[str | Path]) -> dict[str, Any]:
    """Inspect only the explicitly named Markdown/JSON files below ``root``.

    Findings are advisory warnings with human-review recommendations. Invalid
    path selections raise :class:`InputSelectionError`; malformed JSON produces
    a file-level review finding without scanning its contents.
    """
    selected = _select_files(Path(root), paths)
    findings: list[dict[str, Any]] = []
    total_bytes_read = 0
    for relative, path in selected:
        try:
            data = path.read_bytes()
        except OSError as exc:
            raise InputSelectionError(f"selected report became unreadable ({relative}): {exc}") from exc
        if len(data) > MAX_FILE_BYTES:
            raise InputSelectionError(f"selected report grew beyond the per-file size limit: {relative}")
        total_bytes_read += len(data)
        if total_bytes_read > MAX_TOTAL_BYTES:
            raise InputSelectionError("selected reports grew beyond the total size limit")
        try:
            content = data.decode("utf-8")
        except UnicodeDecodeError:
            findings.append(_finding(relative, "$", "REPORT_NOT_PARSEABLE") | {"detail": "Input is not valid UTF-8; no content-level checks were run."})
            continue
        findings.extend(_inspect_content(relative, path.suffix.lower(), content))

    unique: dict[tuple[str, str, str], dict[str, Any]] = {}
    for finding in findings:
        key = (finding["file"], finding["location"], finding["rule"])
        existing = unique.get(key)
        if existing is None:
            unique[key] = finding
        elif finding.get("evidence_reference_detected") is False:
            existing["evidence_reference_detected"] = False
    ordered = sorted(unique.values(), key=_finding_sort_key)
    return {
        "schema_version": SCHEMA_VERSION,
        "advisory_only": True,
        "review_recommended": bool(ordered),
        "findings": ordered,
    }
