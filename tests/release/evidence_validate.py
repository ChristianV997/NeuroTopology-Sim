"""Fail-closed validators for the release evidence-bundle contract.

This module is the QA-owned importable surface. Release may later copy or
import it. It is not compiled scientific evidence and never emits PASS
from synthetic, proxy, or unsupported rows.

Success is an empty error list. There is no warnings-as-success channel.
"""

from __future__ import annotations

import copy
import math
import re
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = REPO_ROOT / "configs" / "release" / "evidence_schema.yaml"
MATRIX_PATH = REPO_ROOT / "docs" / "release" / "agent_contribution_matrix.yaml"

WATCHED_PRS = (210, 211, 212)
NON_EMPIRICAL_CLAIM_CLASSES = frozenset(
    {"synthetic", "proxy", "unsupported", "unavailable"}
)
PASS_STRINGS = frozenset({"pass", "scientific_pass"})
SYNTHETIC_LABELS = frozenset({"synthetic"})
OPEN_STATUS_CATEGORIES = frozenset({"OPEN_REVIEW", "DRAFT_REVIEW"})
BILLING_PASS_AUTHOR_RESULTS = frozenset({"verified_pass", "pass"})
BILLING_POSITIVE_TOKENS = (
    "billing_blocked",
    "billing_not_started",
    "payments failed",
    "payment have failed",
    "account payments have failed",
    "spending limit",
    "job was not started",
    "jobs were not started",
    "jobs never run",
    "jobs_never_run",
    "billing failure",
)
MEMORY_NUMBER_KEYS = frozenset(
    {
        "memory_mb",
        "memory",
        "rss",
        "rss_mb",
        "rss_delta",
        "peak_rss",
        "peak_rss_lifetime",
        "tracemalloc",
        "tracemalloc_peak",
        "peak_memory",
        "rss_bytes",
        "peak",
    }
)
ADAPTER_NEGATION_TOKENS = (
    "not supported",
    "≠ supported",
    "!= supported",
    "not-supported",
    "unsupported",
    "are not",
    "is not",
    "cannot be described as supported",
    "missing adapters",
    "unmerged adapters",
    "≠supported",
    "not adapter support",
)

_NON_FINITE_STRINGS = frozenset(
    {
        "nan",
        "+nan",
        "-nan",
        "inf",
        "+inf",
        "-inf",
        "infinity",
        "+infinity",
        "-infinity",
    }
)

# Fake-shape credential detectors. Tests use synthetic tokens only.
_SECRET_SPECS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("openai_or_anthropic_key", re.compile(r"\bsk-(?:proj-|ant-)?[A-Za-z0-9_-]{12,}\b")),
    ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("github_pat", re.compile(r"\bghp_[A-Za-z0-9]{36}\b")),
    ("github_fine_grained_pat", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b")),
    ("slack_token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    ("private_key", re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----")),
    ("google_api_key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
)


class EvidenceValidationError(Exception):
    """Raised when validate(..., raise_on_error=True) sees one or more errors."""

    def __init__(self, errors: Sequence[str]) -> None:
        self.errors = list(errors)
        super().__init__(list(self.errors))


def load_yaml(path: str | Path) -> Any:
    text = Path(path).read_text(encoding="utf-8")
    return yaml.safe_load(text)


def load_schema(path: str | Path | None = None) -> dict[str, Any]:
    doc = load_yaml(path or SCHEMA_PATH)
    if not isinstance(doc, dict):
        raise EvidenceValidationError(["schema:not_a_mapping"])
    return doc


def load_inventory(path: str | Path | None = None) -> dict[str, Any]:
    doc = load_yaml(path or MATRIX_PATH)
    if not isinstance(doc, dict):
        raise EvidenceValidationError(["inventory:not_a_mapping"])
    return doc


def detect_kind(doc: Mapping[str, Any]) -> str:
    kind = doc.get("kind")
    if kind in {"compiled_report", "inventory", "evidence_bundle_contract"}:
        return str(kind)
    if doc.get("release_recommendation") is not None:
        return "compiled_report"
    if "contributions" in doc:
        return "inventory"
    return "unknown"


def validate(
    doc_or_path: Any,
    *,
    kind: str | None = None,
    schema: Mapping[str, Any] | None = None,
    raise_on_error: bool = False,
) -> list[str]:
    """Return a deterministic error list. Empty list is the only success."""
    if isinstance(doc_or_path, (str, Path)):
        doc = load_yaml(doc_or_path)
    else:
        doc = doc_or_path
    if not isinstance(doc, Mapping):
        errors = ["document:not_a_mapping"]
        if raise_on_error:
            raise EvidenceValidationError(errors)
        return errors

    schema_doc = dict(schema) if schema is not None else load_schema()
    resolved_kind = kind or detect_kind(doc)
    errors: list[str] = []

    if resolved_kind == "unknown":
        errors.append("document:unknown_kind")
        return _finish(errors, raise_on_error)

    _check_secrets(doc, errors)
    _check_numbers(doc, errors, schema_doc)

    if resolved_kind == "inventory":
        _validate_inventory(doc, schema_doc, errors)
    elif resolved_kind == "compiled_report":
        _validate_compiled_report(doc, schema_doc, errors)
    else:
        errors.append(f"document:unsupported_kind:{resolved_kind}")

    return _finish(errors, raise_on_error)


def validate_inventory(
    doc_or_path: Any,
    *,
    schema: Mapping[str, Any] | None = None,
    raise_on_error: bool = False,
) -> list[str]:
    return validate(
        doc_or_path, kind="inventory", schema=schema, raise_on_error=raise_on_error
    )


def validate_compiled_report(
    doc_or_path: Any,
    *,
    schema: Mapping[str, Any] | None = None,
    raise_on_error: bool = False,
) -> list[str]:
    return validate(
        doc_or_path,
        kind="compiled_report",
        schema=schema,
        raise_on_error=raise_on_error,
    )


def _finish(errors: list[str], raise_on_error: bool) -> list[str]:
    # Deterministic: stable insertion order, then a stable sort so reruns match.
    unique: list[str] = []
    seen: set[str] = set()
    for item in errors:
        if item not in seen:
            seen.add(item)
            unique.append(item)
    unique.sort()
    if raise_on_error and unique:
        raise EvidenceValidationError(unique)
    return unique


def _contributions(doc: Mapping[str, Any]) -> list[Any]:
    raw = doc.get("contributions", doc.get("records"))
    if raw is None:
        return []
    if not isinstance(raw, list):
        return [{"__invalid_contributions__": True}]
    return raw


def _require_keys(
    mapping: Mapping[str, Any] | None,
    keys: Iterable[str],
    prefix: str,
    errors: list[str],
) -> None:
    if not isinstance(mapping, Mapping):
        errors.append(f"{prefix}:not_a_mapping")
        return
    for key in keys:
        if key not in mapping:
            errors.append(f"missing_field:{prefix}.{key}" if prefix else f"missing_field:{key}")


def _enum_ok(value: Any, allowed: Sequence[Any]) -> bool:
    return value in allowed


def _as_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _walk(obj: Any, path: str = "") -> Iterable[tuple[str, Any]]:
    if isinstance(obj, Mapping):
        for key, value in obj.items():
            child = f"{path}.{key}" if path else str(key)
            yield from _walk(value, child)
    elif isinstance(obj, list):
        for index, value in enumerate(obj):
            yield from _walk(value, f"{path}[{index}]")
    else:
        yield path, obj


def _check_secrets(doc: Any, errors: list[str]) -> None:
    for path, value in _walk(doc):
        if not isinstance(value, str):
            continue
        for spec_id, pattern in _SECRET_SPECS:
            if pattern.search(value):
                errors.append(f"secret:{spec_id}:{path}")


def _is_non_finite_number(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return False
    if isinstance(value, float):
        return not math.isfinite(value)
    return False


def _looks_like_non_finite_string(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    return value.strip().lower() in _NON_FINITE_STRINGS


def _check_numbers(
    doc: Any, errors: list[str], schema: Mapping[str, Any]
) -> None:
    named = set(
        ((schema.get("numeric_rules") or {}).get("named_numeric_fields") or [])
    )
    for path, value in _walk(doc):
        leaf = path.rsplit(".", 1)[-1]
        if _is_non_finite_number(value):
            errors.append(f"non_finite_number:{path}")
            continue
        if leaf in named and _looks_like_non_finite_string(value):
            errors.append(f"non_finite_number:{path}")


def _field_present(row: Mapping[str, Any], names: Sequence[str]) -> bool:
    return any(name in row and row.get(name) is not None for name in names)


def _first_present(row: Mapping[str, Any], names: Sequence[str]) -> Any:
    for name in names:
        if name in row:
            return row.get(name)
    return None


def _classification(row: Mapping[str, Any]) -> Mapping[str, Any]:
    raw = row.get("research_classification")
    return raw if isinstance(raw, Mapping) else {}


def _claim_class(row: Mapping[str, Any]) -> Any:
    classified = _classification(row)
    if "claim_class" in classified:
        return classified.get("claim_class")
    return row.get("claim_class")


def _data_mode(row: Mapping[str, Any]) -> Any:
    classified = _classification(row)
    if "data_mode" in classified:
        return classified.get("data_mode")
    return row.get("data_mode")


def _empirical_pass_allowed(row: Mapping[str, Any]) -> Any:
    classified = _classification(row)
    if "empirical_pass_allowed" in classified:
        return classified.get("empirical_pass_allowed")
    return row.get("empirical_pass_allowed")


def _is_synthetic_row(row: Mapping[str, Any]) -> bool:
    claim = _as_str(_claim_class(row)).strip().lower()
    mode = _as_str(_data_mode(row)).strip().lower()
    return claim in SYNTHETIC_LABELS or mode in SYNTHETIC_LABELS


def _is_weak_claim(row: Mapping[str, Any]) -> bool:
    claim = _as_str(_claim_class(row)).strip().lower()
    return claim in NON_EMPIRICAL_CLAIM_CLASSES or _is_synthetic_row(row)


def _is_pass_value(value: Any) -> bool:
    if value is True:
        return True
    if isinstance(value, str) and value.strip().lower() in PASS_STRINGS:
        return True
    return False


def _scientific_pass_value(row: Mapping[str, Any]) -> Any:
    status = row.get("verification_status")
    if isinstance(status, Mapping) and "scientific_pass" in status:
        return status.get("scientific_pass")
    return row.get("scientific_pass")


def _author_test_results(row: Mapping[str, Any]) -> Any:
    status = row.get("verification_status")
    if isinstance(status, Mapping) and "author_test_results" in status:
        return status.get("author_test_results")
    return row.get("author_test_results")


def _test_results_value(row: Mapping[str, Any]) -> Any:
    if "test_results" in row:
        return row.get("test_results")
    return None


def _pr_number(row: Mapping[str, Any]) -> int | None:
    raw = row.get("pr_number", row.get("pr"))
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str) and raw.isdigit():
        return int(raw)
    if isinstance(raw, Mapping) and isinstance(raw.get("number"), int):
        return raw["number"]
    return None


def _independently_verified_merged(row: Mapping[str, Any]) -> bool:
    if row.get("merge_status") != "merged":
        return False
    if row.get("is_draft") is True:
        return False
    if row.get("evidence_source") != "github_api":
        return False
    merged_at = row.get("merged_at")
    return isinstance(merged_at, str) and bool(merged_at.strip())


def _warning_blobs(doc: Mapping[str, Any]) -> str:
    parts: list[str] = []
    for key in ("required_warnings",):
        value = doc.get(key)
        if isinstance(value, list):
            parts.extend(_as_str(item) for item in value)
        elif value is not None:
            parts.append(_as_str(value))
    research = doc.get("research_phase")
    if isinstance(research, Mapping):
        extra = research.get("required_warnings")
        if isinstance(extra, list):
            parts.extend(_as_str(item) for item in extra)
    return "\n".join(parts)


def _has_210_211_212_not_merged_warning(text: str) -> bool:
    lowered = text.lower()
    mentions = all(str(pr) in text for pr in WATCHED_PRS)
    not_merged = any(
        token in lowered
        for token in ("not merged", "not-merged", "remain unmerged")
    )
    return mentions and not_merged


def _is_leftover_or_blocked(row: Mapping[str, Any]) -> bool:
    section = _as_str(row.get("section")).upper()
    ident = _as_str(row.get("id")).lower()
    return section == "BLOCKED" or "leftover" in ident or row.get("leftover") is True


def _validate_enums_for_row(
    row: Mapping[str, Any],
    prefix: str,
    schema: Mapping[str, Any],
    errors: list[str],
) -> None:
    enums = schema.get("enums") or {}
    merge_status = row.get("merge_status")
    allowed_merge = enums.get("merge_status") or []
    if merge_status is not None and not _enum_ok(merge_status, allowed_merge):
        errors.append(f"invalid_enum:{prefix}.merge_status:{merge_status}")

    status = row.get("verification_status")
    if isinstance(status, Mapping):
        _check_status_enums(status, f"{prefix}.verification_status", enums, errors)

    classified = _classification(row)
    if classified:
        claim = classified.get("claim_class")
        if claim is not None and not _enum_ok(claim, enums.get("claim_class") or []):
            errors.append(f"invalid_enum:{prefix}.research_classification.claim_class:{claim}")
        value_class = classified.get("value_class")
        if value_class is not None and not _enum_ok(
            value_class, enums.get("value_class") or []
        ):
            errors.append(
                f"invalid_enum:{prefix}.research_classification.value_class:{value_class}"
            )
        data_mode = classified.get("data_mode")
        if data_mode is not None and not _enum_ok(data_mode, enums.get("data_mode") or []):
            errors.append(
                f"invalid_enum:{prefix}.research_classification.data_mode:{data_mode}"
            )

    allowed_status = enums.get("status_category") or []
    for item in _status_values(row):
        if allowed_status and not _enum_ok(item, allowed_status):
            errors.append(f"invalid_enum:{prefix}.status:{item}")


def _check_status_enums(
    status: Mapping[str, Any],
    prefix: str,
    enums: Mapping[str, Any],
    errors: list[str],
) -> None:
    pairs = (
        ("existence", "verification_existence"),
        ("merge_status", "verification_merge_status"),
        ("scientific_pass", "scientific_pass"),
        ("author_test_results", "author_test_results"),
        ("implementation_report", "implementation_report"),
    )
    for field, enum_name in pairs:
        value = status.get(field)
        allowed = enums.get(enum_name) or []
        if value is not None and allowed and not _enum_ok(value, allowed):
            errors.append(f"invalid_enum:{prefix}.{field}:{value}")


def _check_row_hard_rules(row: Mapping[str, Any], prefix: str, errors: list[str]) -> None:
    merge_status = row.get("merge_status")
    is_draft = row.get("is_draft")
    pr_state = _as_str(row.get("pr_state")).strip().lower()

    if merge_status == "merged" and is_draft is True:
        errors.append(f"contradiction:{prefix}:merged_and_is_draft")
    if merge_status == "merged" and pr_state in {"open", "draft"}:
        errors.append(f"contradiction:{prefix}:merged_and_pr_state_{pr_state}")
    if merge_status == "merged" and row.get("section") in {"OPEN/DRAFT", "OPEN", "DRAFT"}:
        errors.append(f"contradiction:{prefix}:merged_and_open_section")

    status_cats = set(_status_values(row))
    if merge_status == "merged" and status_cats & OPEN_STATUS_CATEGORIES:
        errors.append(f"contradiction:{prefix}:merged_and_open_status_category")
    if "VERIFIED_MERGED" in status_cats and merge_status in {
        "open",
        "draft",
        "branch_only",
    }:
        errors.append(f"contradiction:{prefix}:verified_merged_status_but_not_merged")
    if "BRANCH_ONLY" in status_cats and merge_status == "merged":
        errors.append(f"contradiction:{prefix}:branch_only_status_and_merged")

    scientific_pass = _scientific_pass_value(row)
    empirical_allowed = _empirical_pass_allowed(row)
    author_tests = _author_test_results(row)
    test_results = _test_results_value(row)
    compiled_flag = row.get("compiled_from_author_test_results")
    tests_as_evidence = row.get("tests_used_as_compiled_evidence")

    if _is_synthetic_row(row):
        if _is_pass_value(scientific_pass):
            errors.append(f"synthetic_scientific_pass:{prefix}")
        if empirical_allowed is True:
            errors.append(f"synthetic_empirical_pass_allowed:{prefix}")
        if _is_pass_value(test_results):
            errors.append(f"synthetic_test_results_pass:{prefix}")
        if scientific_pass == "claimed":
            errors.append(f"synthetic_scientific_pass_claimed:{prefix}")

    if _is_weak_claim(row) and empirical_allowed is True:
        errors.append(f"empirical_pass_allowed_for_non_empirical:{prefix}")

    if _as_str(author_tests).strip().lower() == "unverified":
        if _is_pass_value(scientific_pass):
            errors.append(f"unverified_author_tests_as_scientific_pass:{prefix}")
        if _is_pass_value(test_results):
            errors.append(f"unverified_author_tests_as_test_results_pass:{prefix}")
        if compiled_flag is True or tests_as_evidence is True:
            errors.append(f"unverified_author_tests_as_compiled_evidence:{prefix}")

    assertions = row.get("scientific_assertions")
    if isinstance(assertions, list):
        for index, item in enumerate(assertions):
            if _is_pass_value(item):
                if _is_synthetic_row(row) or _is_weak_claim(row):
                    errors.append(f"unsupported_scientific_assertion_pass:{prefix}[{index}]")
                if _as_str(author_tests).strip().lower() == "unverified":
                    errors.append(
                        f"unverified_author_tests_as_scientific_assertion:{prefix}[{index}]"
                    )
            if isinstance(item, Mapping) and _is_pass_value(
                item.get("verdict", item.get("status"))
            ):
                if _is_synthetic_row(row) or _is_weak_claim(row):
                    errors.append(f"unsupported_scientific_assertion_pass:{prefix}[{index}]")

    _check_billing_not_pass(row, prefix, errors)
    _check_memory_metrics(row, prefix, errors)
    _check_adapters_supported_claim(row, prefix, errors)
    if _is_stacked_row(row) and _parent_pr_id(row) is None:
        errors.append(f"stacked_parent_missing:{prefix}")


def _status_values(row: Mapping[str, Any]) -> list[str]:
    raw = row.get("status")
    if isinstance(raw, str) and raw.strip():
        return [raw.strip()]
    if isinstance(raw, list):
        return [item.strip() for item in raw if isinstance(item, str) and item.strip()]
    return []


def _parent_pr_id(row: Mapping[str, Any]) -> int | None:
    locations: list[Any] = [
        row.get("stacked_base"),
        row.get("stacked_on"),
        _classification(row).get("stacked_on"),
        row,
    ]
    for loc in locations:
        if isinstance(loc, bool):
            continue
        if isinstance(loc, int):
            return loc
        if isinstance(loc, str) and loc.isdigit():
            return int(loc)
        if not isinstance(loc, Mapping):
            continue
        for key in ("parent_pr", "base_pr", "parent_id"):
            value = loc.get(key)
            parsed = _coerce_pr_id(value)
            if parsed is not None:
                return parsed
            if isinstance(value, Mapping):
                nested = _coerce_pr_id(
                    value.get("parent_pr", value.get("base_pr", value.get("number")))
                )
                if nested is not None:
                    return nested
    return None


def _coerce_pr_id(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _is_stacked_row(row: Mapping[str, Any]) -> bool:
    if _as_str(row.get("section")).upper() == "STACKED":
        return True
    if "STACKED" in {item.upper() for item in _status_values(row)}:
        return True
    if row.get("base_pr") is not None:
        return True
    stacked_on = row.get("stacked_on")
    if stacked_on not in (None, False, {}):
        return True
    classified = _classification(row)
    if classified.get("stacked_on") not in (None, False, {}):
        return True
    stacked_base = row.get("stacked_base")
    if stacked_base is True:
        return True
    if isinstance(stacked_base, Mapping):
        rel = _as_str(stacked_base.get("relationship")).upper()
        if rel == "STACKED":
            return True
        if any(
            stacked_base.get(key) is not None
            for key in ("parent_pr", "base_pr", "parent_id")
        ):
            return True
    return False


def _parent_is_open(parent: Mapping[str, Any]) -> bool:
    merge_status = parent.get("merge_status")
    if merge_status in {"open", "draft"}:
        return True
    if parent.get("is_draft") is True:
        return True
    if _as_str(parent.get("pr_state")).strip().lower() in {"open", "draft"}:
        return True
    if set(_status_values(parent)) & OPEN_STATUS_CATEGORIES:
        return True
    if parent.get("section") in {"OPEN/DRAFT", "OPEN", "DRAFT"}:
        return True
    return False


def _check_stacked_pack(rows: Sequence[Any], errors: list[str]) -> None:
    by_pr: dict[int, Mapping[str, Any]] = {}
    for raw in rows:
        if not isinstance(raw, Mapping):
            continue
        prn = _pr_number(raw)
        if prn is not None:
            by_pr[prn] = raw
    for index, raw in enumerate(rows):
        if not isinstance(raw, Mapping) or not _is_stacked_row(raw):
            continue
        prefix = f"contributions[{index}]"
        parent_id = _parent_pr_id(raw)
        if parent_id is None:
            continue
        parent = by_pr.get(parent_id)
        if parent is None:
            continue
        if raw.get("merge_status") == "merged" and _parent_is_open(parent):
            errors.append(
                f"stacked_merged_while_parent_open:{prefix}:parent_pr:{parent_id}"
            )


def _github_checks_mapping(row: Mapping[str, Any]) -> Mapping[str, Any]:
    checks = row.get("github_checks")
    return checks if isinstance(checks, Mapping) else {}


def _checks_text_blob(checks: Mapping[str, Any]) -> str:
    parts: list[str] = []
    for value in checks.values():
        if isinstance(value, (str, int, float)):
            parts.append(_as_str(value))
    return " ".join(parts)


def _billing_not_started(row: Mapping[str, Any]) -> bool:
    if "BILLING_BLOCKED" in _status_values(row):
        return True
    checks = _github_checks_mapping(row)
    if checks.get("billing_not_started") is True:
        return True
    if checks.get("jobs_never_run") is True:
        return True
    if checks.get("jobs_started") is False:
        return True
    if _as_str(checks.get("status_category")).upper() == "BILLING_BLOCKED":
        return True
    blob = _checks_text_blob(checks).lower()
    if not blob:
        return False
    if re.search(r"\bnot billing\b", blob):
        if not any(
            token in blob
            for token in (
                "billing_blocked",
                "payments failed",
                "spending limit",
                "job was not started",
            )
        ):
            return False
    return any(token in blob for token in BILLING_POSITIVE_TOKENS)


def _check_billing_not_pass(
    row: Mapping[str, Any], prefix: str, errors: list[str]
) -> None:
    if not _billing_not_started(row):
        return
    author = _as_str(_author_test_results(row)).strip().lower()
    if author in BILLING_PASS_AUTHOR_RESULTS:
        errors.append(f"billing_not_started_as_verified_pass:{prefix}")
    if _is_pass_value(_test_results_value(row)):
        errors.append(f"billing_not_started_as_test_results_pass:{prefix}")
    if _is_pass_value(_scientific_pass_value(row)):
        errors.append(f"billing_not_started_as_scientific_pass:{prefix}")
    if author == "verified" and _is_pass_value(_test_results_value(row)):
        errors.append(f"billing_not_started_as_verified_pass:{prefix}")


def _memory_objects(row: Mapping[str, Any]) -> list[Any]:
    blobs: list[Any] = []
    for key in ("process_memory", "memory_metrics"):
        if key in row and row.get(key) is not None:
            blobs.append(row.get(key))
    classified = _classification(row)
    if classified.get("memory_measurement") is not None:
        blobs.append(classified.get("memory_measurement"))
    return blobs


def _memory_marked_unavailable(blob: Any) -> bool:
    if isinstance(blob, Mapping):
        for key in (
            "independently_verified",
            "availability",
            "verified",
            "author_table",
        ):
            token = _as_str(blob.get(key)).strip().lower()
            if token in {"unavailable", "unverified", "false", "none"}:
                return True
        if blob.get("author_claimed_unverified") is True:
            return True
        if blob.get("independently_verified") is False:
            return True
    text = _as_str(blob).lower()
    return "unavailable" in text or "unverified" in text


def _memory_has_kind(blob: Any) -> bool:
    if isinstance(blob, Mapping):
        kind = _as_str(
            blob.get("kind") or blob.get("unit") or blob.get("memory_kind")
        ).strip().lower()
        if kind in {"rss", "tracemalloc"}:
            return True
        walked = " ".join(_as_str(value) for _, value in _walk(blob)).lower()
        return "rss" in walked or "tracemalloc" in walked
    text = _as_str(blob).lower()
    return "rss" in text or "tracemalloc" in text


def _memory_has_numbers(blob: Any) -> bool:
    if isinstance(blob, Mapping):
        for path, value in _walk(blob):
            leaf = path.rsplit(".", 1)[-1]
            if leaf in MEMORY_NUMBER_KEYS:
                return True
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                if "memory" in path.lower() or leaf in MEMORY_NUMBER_KEYS:
                    return True
        return False
    return bool(re.search(r"\d", _as_str(blob)))


def _memory_marked_verified(blob: Any) -> bool:
    if not isinstance(blob, Mapping):
        return False
    if blob.get("independently_verified") is True:
        return True
    token = _as_str(blob.get("independently_verified") or blob.get("verified")).lower()
    return token in {"verified", "true"}


def _check_memory_metrics(
    row: Mapping[str, Any], prefix: str, errors: list[str]
) -> None:
    for blob in _memory_objects(row):
        has_numbers = _memory_has_numbers(blob)
        if not has_numbers:
            continue
        unavailable = _memory_marked_unavailable(blob)
        has_kind = _memory_has_kind(blob)
        verified = _memory_marked_verified(blob)
        if verified and not has_kind:
            errors.append(f"unlabeled_memory_as_verified:{prefix}")
        if not has_kind and not unavailable:
            errors.append(f"memory_kind_or_unavailable_required:{prefix}")


def _adapters_supported_flag(row: Mapping[str, Any]) -> Any:
    if "adapters_supported" in row:
        return row.get("adapters_supported")
    return _classification(row).get("adapters_supported")


def _explicit_adapters_supported_claim(row: Mapping[str, Any]) -> bool:
    locations = (row, _classification(row))
    for loc in locations:
        if not isinstance(loc, Mapping):
            continue
        if loc.get("adapters_described_as_supported") is True:
            return True
        for key in ("adapters_claim", "adapters_status"):
            token = _as_str(loc.get(key)).strip().lower()
            if token in {"supported", "yes", "true"}:
                return True
    return False


def _row_text_blobs(row: Mapping[str, Any]) -> list[str]:
    texts: list[str] = []
    for key in (
        "research_notes",
        "limitations",
        "scientific_assertions",
        "next_action",
        "notes",
        "open_questions",
    ):
        value = row.get(key)
        if isinstance(value, list):
            texts.extend(_as_str(item) for item in value)
        elif value is not None:
            texts.append(_as_str(value))
    classified = _classification(row)
    notes = classified.get("research_notes")
    if notes is not None:
        texts.append(_as_str(notes))
    extra = classified.get("methodological_limitations")
    if isinstance(extra, list):
        texts.extend(_as_str(item) for item in extra)
    return texts


def _unnegated_adapter_supported_text(row: Mapping[str, Any]) -> bool:
    for text in _row_text_blobs(row):
        lowered = text.lower()
        if "adapter" not in lowered or "supported" not in lowered:
            continue
        if any(token in lowered for token in ADAPTER_NEGATION_TOKENS):
            continue
        if re.search(r"\badapters?\b.{0,60}\bsupported\b", lowered):
            return True
    return False


def _check_adapters_supported_claim(
    row: Mapping[str, Any], prefix: str, errors: list[str]
) -> None:
    if _adapters_supported_flag(row) is not False:
        return
    if _explicit_adapters_supported_claim(row) or _unnegated_adapter_supported_text(row):
        errors.append(f"adapters_supported_false_described_as_supported:{prefix}")


def _check_uniques(
    rows: Sequence[Any],
    *,
    check_branches: bool,
    errors: list[str],
) -> None:
    seen_ids: dict[str, str] = {}
    seen_work_orders: dict[str, str] = {}
    seen_branches: dict[str, str] = {}
    for index, raw in enumerate(rows):
        prefix = f"contributions[{index}]"
        if not isinstance(raw, Mapping):
            errors.append(f"{prefix}:not_a_mapping")
            continue
        ident = raw.get("id")
        if isinstance(ident, str) and ident:
            if ident in seen_ids:
                errors.append(f"duplicate_id:{ident}")
            else:
                seen_ids[ident] = prefix
        work_order = raw.get("work_order")
        if isinstance(work_order, str) and work_order.strip():
            if work_order in seen_work_orders:
                errors.append(f"duplicate_work_order:{work_order}")
            else:
                seen_work_orders[work_order] = prefix
        if check_branches and not _is_leftover_or_blocked(raw):
            branch = raw.get("branch")
            if isinstance(branch, str) and branch.strip():
                if branch in seen_branches:
                    errors.append(f"duplicate_branch:{branch}")
                else:
                    seen_branches[branch] = prefix


def _check_watched_prs(doc: Mapping[str, Any], rows: Sequence[Any], errors: list[str]) -> None:
    warning_text = _warning_blobs(doc)
    unverified: list[int] = []
    for prn in WATCHED_PRS:
        row = next(
            (
                item
                for item in rows
                if isinstance(item, Mapping) and _pr_number(item) == prn
            ),
            None,
        )
        if row is None:
            unverified.append(prn)
            continue
        if row.get("merge_status") == "merged" and not _independently_verified_merged(row):
            errors.append(f"watched_pr_merged_without_independent_verification:{prn}")
        if not _independently_verified_merged(row):
            unverified.append(prn)
            if row.get("merge_status") == "merged":
                errors.append(f"watched_pr_recorded_as_merged:{prn}")
    if unverified and not _has_210_211_212_not_merged_warning(warning_text):
        errors.append("required_warning_missing:prs_210_211_212_not_merged")


def _check_pack_flags(doc: Mapping[str, Any], rows: Sequence[Any], errors: list[str]) -> None:
    if "inventory_is_not_evidence" not in doc:
        errors.append("missing_field:inventory_is_not_evidence")
    elif doc.get("inventory_is_not_evidence") is not True:
        errors.append("inventory_is_not_evidence_must_be_true")

    pack_empirical = doc.get("empirical_pass_from_this_pack")
    pack_allowed = doc.get("empirical_pass_allowed")
    weak_present = any(isinstance(row, Mapping) and _is_weak_claim(row) for row in rows)
    synthetic_present = any(
        isinstance(row, Mapping) and _is_synthetic_row(row) for row in rows
    )
    if (weak_present or synthetic_present) and pack_empirical is True:
        errors.append("empirical_pass_from_this_pack_must_be_false")
    if (weak_present or synthetic_present) and pack_allowed is True:
        errors.append("pack_empirical_pass_allowed_must_be_false")

    research = doc.get("research_phase")
    if isinstance(research, Mapping):
        if research.get("inventory_is_not_evidence") is False:
            errors.append("research_phase.inventory_is_not_evidence_must_be_true")
        if research.get("empirical_pass_from_this_pack") is True:
            errors.append("research_phase.empirical_pass_from_this_pack_must_be_false")


def _validate_inventory(
    doc: Mapping[str, Any],
    schema: Mapping[str, Any],
    errors: list[str],
) -> None:
    spec = schema.get("inventory") or {}
    _require_keys(doc, spec.get("required_envelope_keys") or [], "", errors)
    rows = _contributions(doc)
    if doc.get("contributions") is not None and not isinstance(doc.get("contributions"), list):
        errors.append("contributions:not_a_list")
        return

    research = doc.get("research_phase")
    if research is not None:
        _require_keys(
            research if isinstance(research, Mapping) else None,
            spec.get("research_phase_required_keys") or [],
            "research_phase",
            errors,
        )

    required_row = spec.get("required_contribution_fields") or []
    status_required = (schema.get("verification_status") or {}).get("required_fields") or []
    class_required = (schema.get("research_classification") or {}).get("required_fields") or []

    for index, raw in enumerate(rows):
        prefix = f"contributions[{index}]"
        if not isinstance(raw, Mapping):
            errors.append(f"{prefix}:not_a_mapping")
            continue
        _require_keys(raw, required_row, prefix, errors)
        status = raw.get("verification_status")
        if "verification_status" in raw:
            _require_keys(
                status if isinstance(status, Mapping) else None,
                status_required,
                f"{prefix}.verification_status",
                errors,
            )
        classified = raw.get("research_classification")
        if "research_classification" in raw:
            _require_keys(
                classified if isinstance(classified, Mapping) else None,
                class_required,
                f"{prefix}.research_classification",
                errors,
            )
        _validate_enums_for_row(raw, prefix, schema, errors)
        _check_row_hard_rules(raw, prefix, errors)

    _check_uniques(rows, check_branches=False, errors=errors)
    _check_pack_flags(doc, rows, errors)
    _check_watched_prs(doc, rows, errors)
    _check_stacked_pack(rows, errors)


def _compiled_field_names(spec: Mapping[str, Any], field: str) -> list[str]:
    aliases = (spec.get("contribution_field_aliases") or {}).get(field)
    if aliases:
        return list(aliases)
    return [field]


def _validate_compiled_report(
    doc: Mapping[str, Any],
    schema: Mapping[str, Any],
    errors: list[str],
) -> None:
    spec = schema.get("compiled_report") or {}
    _require_keys(doc, spec.get("required_envelope_keys") or [], "", errors)
    if doc.get("kind") not in {None, "compiled_report"}:
        errors.append(f"compiled_report:unexpected_kind:{doc.get('kind')}")

    recommendation = doc.get("release_recommendation")
    allowed_rec = (schema.get("enums") or {}).get("release_recommendation") or []
    if recommendation is not None and not _enum_ok(recommendation, allowed_rec):
        errors.append(f"invalid_enum:release_recommendation:{recommendation}")

    rows = _contributions(doc)
    if doc.get("contributions") is not None and not isinstance(doc.get("contributions"), list):
        errors.append("contributions:not_a_list")
        return

    required_row = spec.get("required_contribution_fields") or []
    status_required = (schema.get("verification_status") or {}).get("required_fields") or []

    for index, raw in enumerate(rows):
        prefix = f"contributions[{index}]"
        if not isinstance(raw, Mapping):
            errors.append(f"{prefix}:not_a_mapping")
            continue
        for field in required_row:
            names = _compiled_field_names(spec, field)
            if field == "verification_status":
                if "verification_status" not in raw:
                    errors.append(f"missing_field:{prefix}.verification_status")
                continue
            if field in {
                "pr",
                "changed_files",
                "test_results",
            }:
                if not any(name in raw for name in names):
                    errors.append(f"missing_field:{prefix}.{field}")
                continue
            if field not in raw:
                errors.append(f"missing_field:{prefix}.{field}")
        status = raw.get("verification_status")
        if isinstance(status, Mapping):
            _require_keys(status, status_required, f"{prefix}.verification_status", errors)
        elif "verification_status" in raw:
            errors.append(f"{prefix}.verification_status:not_a_mapping")
        _validate_enums_for_row(raw, prefix, schema, errors)
        _check_row_hard_rules(raw, prefix, errors)

    _check_uniques(rows, check_branches=True, errors=errors)
    _check_pack_flags(doc, rows, errors)
    _check_watched_prs(doc, rows, errors)
    _check_stacked_pack(rows, errors)


def clone_doc(doc: Mapping[str, Any]) -> dict[str, Any]:
    """Deep-copy a document so fixture mutations stay isolated."""
    return copy.deepcopy(dict(doc))
