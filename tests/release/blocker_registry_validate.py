"""Fail-closed validators for the release blocker registry.

QA-owned importable surface. Release may later wrap these helpers in
``scripts/validate_release_blockers.py``. This module is not compiled
scientific evidence and never emits PASS from synthetic, proxy, billing,
or unsupported rows.

Success is an empty error list. There is no warnings-as-success channel.
"""

from __future__ import annotations

import ast
import copy
import math
import re
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = REPO_ROOT / "configs" / "release" / "blocker_registry.yaml"

REQUIRED_ENVELOPE_FIELDS: tuple[str, ...] = (
    "kind",
    "allowed_categories",
    "blockers",
    "current_integration",
    "empirical_pass_from_this_pack",
    "inventory_is_not_evidence",
)
REQUIRED_BLOCKER_FIELDS: tuple[str, ...] = (
    "id",
    "category",
    "severity",
    "status",
    "affected_pr_or_branch",
    "exact_evidence",
    "reproducibility",
    "owner_role",
    "recommended_action",
    "scientific_impact",
    "release_impact",
)
REQUIRED_CURRENT_INTEGRATION_FIELDS: tuple[str, ...] = (
    "head_ref_oid",
    "expected_head_from_work_order",
    "current_head_mismatch",
    "merged",
    "state",
)
SCIENTIFIC_CATEGORIES = frozenset({"SCIENTIFIC_REVIEW", "PROVENANCE_INCOMPLETE"})
PASS_STRINGS = frozenset(
    {"pass", "scientific_pass", "verified_pass", "empirical_pass", "passed"}
)
MEMORY_KIND_ALLOWED = frozenset({"unavailable", "rss", "tracemalloc"})
BILLING_VS_TRUE_CI_ALLOWED = frozenset(
    {
        "billing_not_started",
        "true_ci_unread",
        "true_ci",
        "true_workflow_defect",
        "historical_only",
        "not_applicable",
    }
)
EMPTY_STEP_TOKENS = (
    "steps=[]",
    "empty step",
    "empty-step",
    "empty_step",
    "unstarted",
    "blobnotfound",
    "jobs never run",
    "job was not started",
)
TEST_EVIDENCE_TOKENS = (
    "isolated run",
    "isolated-run",
    "test files",
    "timed out",
    "batch_summary",
)
NETWORK_IMPORT_DENYLIST = frozenset(
    {
        "requests",
        "urllib",
        "urllib2",
        "urllib3",
        "httpx",
        "aiohttp",
        "httplib",
        "http.client",
        "github",
        "ghapi",
        "socket",
        "http.server",
    }
)
MARKETOS_IMPORT_DENYLIST = frozenset({"marketos", "MarketOS"})
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
        ".nan",
        ".inf",
        "-.inf",
        "+.inf",
    }
)
_SECRET_SPECS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("openai_or_anthropic_key", re.compile(r"\bsk-(?:proj-|ant-)?[A-Za-z0-9_-]{12,}\b")),
    ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("github_pat", re.compile(r"\bghp_[A-Za-z0-9]{36}\b")),
    ("github_fine_grained_pat", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b")),
    ("slack_token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    ("private_key", re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----")),
    ("google_api_key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
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


class BlockerRegistryValidationError(Exception):
    """Raised when validate(..., raise_on_error=True) sees one or more errors."""

    def __init__(self, errors: Sequence[str]) -> None:
        self.errors = list(errors)
        super().__init__(list(self.errors))


def load_yaml(path: str | Path) -> Any:
    text = Path(path).read_text(encoding="utf-8")
    return yaml.safe_load(text)


def load_registry(path: str | Path | None = None) -> dict[str, Any]:
    doc = load_yaml(path or REGISTRY_PATH)
    if not isinstance(doc, dict):
        raise BlockerRegistryValidationError(["registry:not_a_mapping"])
    return doc


def clone_doc(doc: Mapping[str, Any]) -> dict[str, Any]:
    """Deep-copy a document so fixture mutations stay isolated."""
    return copy.deepcopy(dict(doc))


def validate(
    doc_or_path: Any,
    *,
    raise_on_error: bool = False,
) -> list[str]:
    """Return a deterministic error list. Empty list is the only success."""
    if isinstance(doc_or_path, (str, Path)):
        doc = load_yaml(doc_or_path)
    else:
        doc = doc_or_path
    if not isinstance(doc, Mapping):
        errors = ["document:not_a_mapping"]
        return _finish(errors, raise_on_error)

    errors: list[str] = []
    _check_secrets(doc, errors)
    _check_numbers(doc, errors)
    _validate_registry(doc, errors)
    return _finish(errors, raise_on_error)


def validate_blocker_registry(
    doc_or_path: Any,
    *,
    raise_on_error: bool = False,
) -> list[str]:
    return validate(doc_or_path, raise_on_error=raise_on_error)


def collect_forbidden_imports(source_path: str | Path) -> list[str]:
    """AST denylist: network clients and MarketOS must not be imported."""
    path = Path(source_path)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return [f"{path.as_posix()}: cannot read source: {exc}"]
    try:
        tree = ast.parse(text, filename=str(path))
    except SyntaxError as exc:
        return [f"{path.as_posix()}: cannot parse source: {exc}"]
    errors: list[str] = []
    for module in _iter_imported_modules(tree):
        root = module.split(".", 1)[0]
        if module in NETWORK_IMPORT_DENYLIST or root in NETWORK_IMPORT_DENYLIST:
            errors.append(f"{path.as_posix()}: forbidden network import {module!r}")
        if module in MARKETOS_IMPORT_DENYLIST or root in MARKETOS_IMPORT_DENYLIST:
            errors.append(f"{path.as_posix()}: forbidden MarketOS import {module!r}")
    return errors


def _iter_imported_modules(tree: ast.AST) -> Iterable[str]:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom) and node.module:
            yield node.module


def _finish(errors: list[str], raise_on_error: bool) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for item in errors:
        if item not in seen:
            seen.add(item)
            unique.append(item)
    unique.sort()
    if raise_on_error and unique:
        raise BlockerRegistryValidationError(unique)
    return unique


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


def _require_keys(
    mapping: Mapping[str, Any] | None,
    keys: Iterable[str],
    prefix: str,
    errors: list[str],
) -> None:
    if not isinstance(mapping, Mapping):
        errors.append(f"{prefix}:not_a_mapping" if prefix else "document:not_a_mapping")
        return
    for key in keys:
        if key not in mapping or mapping.get(key) is None:
            errors.append(
                f"missing_field:{prefix}.{key}" if prefix else f"missing_field:{key}"
            )


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


def _check_numbers(doc: Any, errors: list[str]) -> None:
    for path, value in _walk(doc):
        if _is_non_finite_number(value):
            errors.append(f"non_finite_number:{path}")
            continue
        if _looks_like_non_finite_string(value):
            errors.append(f"non_finite_number:{path}")


def _is_pass_value(value: Any) -> bool:
    if value is True:
        return True
    if isinstance(value, str) and value.strip().lower() in PASS_STRINGS:
        return True
    return False


def _classification(row: Mapping[str, Any]) -> Mapping[str, Any]:
    raw = row.get("research_classification")
    return raw if isinstance(raw, Mapping) else {}


def _blockers(doc: Mapping[str, Any]) -> list[Any]:
    raw = doc.get("blockers")
    if raw is None:
        return []
    if not isinstance(raw, list):
        return [{"__invalid_blockers__": True}]
    return raw


def _blob(row: Mapping[str, Any]) -> str:
    parts: list[str] = []
    evidence = row.get("exact_evidence")
    if isinstance(evidence, list):
        parts.extend(_as_str(item) for item in evidence)
    elif evidence is not None:
        parts.append(_as_str(evidence))
    for key in ("notes", "recommended_action", "affected_pr_or_branch"):
        value = row.get(key)
        if value is not None:
            parts.append(_as_str(value))
    classified = _classification(row)
    notes = classified.get("research_notes")
    if notes is not None:
        parts.append(_as_str(notes))
    extra = classified.get("methodological_limitations")
    if isinstance(extra, list):
        parts.extend(_as_str(item) for item in extra)
    elif extra is not None:
        parts.append(_as_str(extra))
    return "\n".join(parts)


def _validate_registry(doc: Mapping[str, Any], errors: list[str]) -> None:
    _require_keys(doc, REQUIRED_ENVELOPE_FIELDS, "", errors)
    if "kind" in doc and doc.get("kind") != "blocker_registry":
        errors.append(f"unexpected_kind:{doc.get('kind')}")

    if doc.get("inventory_is_not_evidence") is not True:
        if "inventory_is_not_evidence" in doc:
            errors.append("inventory_is_not_evidence_must_be_true")

    if doc.get("empirical_pass_from_this_pack") is True:
        errors.append("empirical_pass_from_this_pack_must_be_false")
    elif (
        "empirical_pass_from_this_pack" in doc
        and doc.get("empirical_pass_from_this_pack") is not False
    ):
        errors.append("empirical_pass_from_this_pack_must_be_false")

    if _is_pass_value(doc.get("scientific_pass_from_this_pack")):
        errors.append("invented_scientific_pass:pack")

    allowed = doc.get("allowed_categories")
    if allowed is not None and not isinstance(allowed, list):
        errors.append("allowed_categories:not_a_list")
        allowed_set: set[Any] = set()
    else:
        allowed_set = set(allowed or [])

    current = doc.get("current_integration")
    if "current_integration" in doc:
        _require_keys(
            current if isinstance(current, Mapping) else None,
            REQUIRED_CURRENT_INTEGRATION_FIELDS,
            "current_integration",
            errors,
        )
        if isinstance(current, Mapping):
            _check_status_contradictions(current, "current_integration", errors)

    research = doc.get("research_phase")
    if research is not None:
        if not isinstance(research, Mapping):
            errors.append("research_phase:not_a_mapping")
        else:
            if research.get("inventory_is_not_evidence") is False:
                errors.append("research_phase.inventory_is_not_evidence_must_be_true")
            if research.get("empirical_pass_from_this_pack") is True:
                errors.append("research_phase.empirical_pass_from_this_pack_must_be_false")
            if _is_pass_value(research.get("scientific_pass_from_this_pack")):
                errors.append("invented_scientific_pass:research_phase")
            if "synthetic_status" in research:
                status = _as_str(research.get("synthetic_status")).strip().upper()
                if status != "NOT_SUPPORTED":
                    errors.append("synthetic_status_must_be_NOT_SUPPORTED")
            _check_treats_unsupported(research, "research_phase", errors)

    isolated = doc.get("author_claimed_isolated_run")
    isolated_verified = None
    if isolated is not None:
        if not isinstance(isolated, Mapping):
            errors.append("author_claimed_isolated_run:not_a_mapping")
        else:
            isolated_verified = isolated.get("independently_verified")
            if _is_pass_value(isolated.get("verified_pass")) or _is_pass_value(
                isolated.get("test_results")
            ):
                errors.append("unverified_isolated_counts_as_verified_pass:envelope")
            if isolated_verified is False and isolated.get("treat_as_verified_pass") is True:
                errors.append("unverified_isolated_counts_as_verified_pass:envelope")

    _check_head_mismatch(doc, errors)
    _check_treats_unsupported(doc, "", errors)

    rows = _blockers(doc)
    if doc.get("blockers") is not None and not isinstance(doc.get("blockers"), list):
        errors.append("blockers:not_a_list")
        return

    seen_ids: dict[str, str] = {}
    for index, raw in enumerate(rows):
        prefix = f"blockers[{index}]"
        if not isinstance(raw, Mapping):
            errors.append(f"{prefix}:not_a_mapping")
            continue
        _require_keys(raw, REQUIRED_BLOCKER_FIELDS, prefix, errors)
        ident = raw.get("id")
        if isinstance(ident, str) and ident:
            if ident in seen_ids:
                errors.append(f"duplicate_id:{ident}")
            else:
                seen_ids[ident] = prefix
        _check_category(raw, prefix, allowed_set, errors)
        _check_exact_evidence(raw, prefix, errors)
        _check_treats_unsupported(raw, prefix, errors)
        classified = _classification(raw)
        if "research_classification" in raw:
            if not isinstance(raw.get("research_classification"), Mapping):
                errors.append(f"{prefix}.research_classification:not_a_mapping")
            else:
                if "treats_unsupported_claim_as_evidence" not in classified:
                    errors.append(
                        f"missing_field:{prefix}.research_classification."
                        "treats_unsupported_claim_as_evidence"
                    )
                elif classified.get("treats_unsupported_claim_as_evidence") is not False:
                    errors.append(
                        f"treats_unsupported_claim_as_evidence_must_be_false:{prefix}"
                    )
                billing = classified.get("billing_vs_true_ci")
                if billing is not None and billing not in BILLING_VS_TRUE_CI_ALLOWED:
                    errors.append(
                        f"invalid_enum:{prefix}.research_classification.billing_vs_true_ci:{billing}"
                    )
        _check_scientific_row(raw, prefix, errors)
        _check_billing_vs_ci(raw, prefix, errors)
        _check_isolated_counts(raw, prefix, isolated_verified, errors)
        _check_dashboard(raw, prefix, errors)
        _check_memory(raw, prefix, errors)
        _check_empty_step_as_test_failure(raw, prefix, errors)


def _check_category(
    row: Mapping[str, Any],
    prefix: str,
    allowed: set[Any],
    errors: list[str],
) -> None:
    category = row.get("category")
    if category is None:
        return
    if allowed and category not in allowed:
        errors.append(f"invalid_category:{prefix}:{category}")


def _check_exact_evidence(
    row: Mapping[str, Any], prefix: str, errors: list[str]
) -> None:
    evidence = row.get("exact_evidence")
    if "exact_evidence" not in row:
        return
    if not isinstance(evidence, list):
        errors.append(f"exact_evidence:not_a_list:{prefix}")
        return
    items = [item for item in evidence if isinstance(item, str) and item.strip()]
    if not items:
        errors.append(f"empty_exact_evidence:{prefix}")


def _check_treats_unsupported(
    obj: Mapping[str, Any], prefix: str, errors: list[str]
) -> None:
    for path, value in _walk(obj):
        leaf = path.rsplit(".", 1)[-1]
        if leaf != "treats_unsupported_claim_as_evidence":
            continue
        if value is not False:
            loc = f"{prefix}.{path}" if prefix else path
            errors.append(f"treats_unsupported_claim_as_evidence_must_be_false:{loc}")


def _heads_locked_equal(doc: Mapping[str, Any]) -> bool:
    current = doc.get("current_integration")
    if not isinstance(current, Mapping):
        return False
    head = _as_str(current.get("head_ref_oid")).strip().lower()
    expected = _as_str(current.get("expected_head_from_work_order")).strip().lower()
    return bool(head) and bool(expected) and head == expected


def _check_head_mismatch(doc: Mapping[str, Any], errors: list[str]) -> None:
    if not _heads_locked_equal(doc):
        return
    current = doc.get("current_integration")
    locations: list[tuple[str, Any]] = []
    if isinstance(current, Mapping):
        locations.append(
            ("current_integration.current_head_mismatch", current.get("current_head_mismatch"))
        )
    if "current_head_mismatch" in doc:
        locations.append(("current_head_mismatch", doc.get("current_head_mismatch")))
    research = doc.get("research_phase")
    if isinstance(research, Mapping) and "current_head_mismatch" in research:
        locations.append(
            ("research_phase.current_head_mismatch", research.get("current_head_mismatch"))
        )
    for loc, value in locations:
        if value is True:
            errors.append(f"invented_current_head_mismatch:{loc}")
    for index, raw in enumerate(_blockers(doc)):
        if not isinstance(raw, Mapping):
            continue
        if raw.get("category") == "CURRENT_HEAD_MISMATCH":
            ident = raw.get("id") or f"blockers[{index}]"
            errors.append(f"invented_current_head_mismatch:{ident}")


def _check_status_contradictions(
    current: Mapping[str, Any], prefix: str, errors: list[str]
) -> None:
    merged = current.get("merged")
    state = _as_str(current.get("state")).strip().upper()
    draft = current.get("draft")
    if merged is True and state in {"OPEN", "DRAFT"}:
        errors.append(f"contradiction:{prefix}:merged_and_state_{state.lower()}")
    if merged is True and draft is True:
        errors.append(f"contradiction:{prefix}:merged_and_draft")
    if merged is False and state in {"MERGED", "CLOSED"}:
        errors.append(f"contradiction:{prefix}:not_merged_and_state_{state.lower()}")
    if draft is True and state == "MERGED":
        errors.append(f"contradiction:{prefix}:draft_and_merged_state")


def _is_scientific_row(row: Mapping[str, Any]) -> bool:
    if row.get("category") in SCIENTIFIC_CATEGORIES:
        return True
    classified = _classification(row)
    if _as_str(classified.get("class")).strip().lower() == "scientific":
        return True
    classes = classified.get("classes")
    if isinstance(classes, list) and "scientific" in classes:
        return True
    impact = _as_str(row.get("scientific_impact")).strip().upper()
    if impact == "NOT_SUPPORTED":
        return True
    return False


def _check_scientific_row(
    row: Mapping[str, Any], prefix: str, errors: list[str]
) -> None:
    classified = _classification(row)
    claim = classified.get("scientific_claim_status")
    impact = row.get("scientific_impact")
    if _is_pass_value(claim):
        errors.append(f"invented_scientific_pass:{prefix}")
    if _is_pass_value(impact):
        errors.append(f"invented_scientific_pass:{prefix}.scientific_impact")
    if _is_scientific_row(row):
        claim_token = _as_str(claim).strip().upper()
        if classified and claim_token != "NOT_SUPPORTED":
            errors.append(f"scientific_claim_status_must_be_NOT_SUPPORTED:{prefix}")
        impact_token = _as_str(impact).strip().upper()
        if impact is not None and impact_token not in {"NOT_SUPPORTED", ""}:
            if _is_pass_value(impact) or impact_token in {"PASS", "SUPPORTED"}:
                errors.append(f"invented_scientific_pass:{prefix}.scientific_impact")


def _check_billing_vs_ci(
    row: Mapping[str, Any], prefix: str, errors: list[str]
) -> None:
    category = row.get("category")
    classified = _classification(row)
    billing = classified.get("billing_vs_true_ci")
    if category == "BILLING_OR_RUNNER_BLOCK":
        if classified and billing != "billing_not_started":
            errors.append(
                f"billing_vs_true_ci_inconsistent:{prefix}:{billing}"
            )
        if billing == "billing_not_started" or category == "BILLING_OR_RUNNER_BLOCK":
            _refuse_billing_as_pass(row, prefix, errors)
    if category == "TEST_FAILURE" and billing == "billing_not_started":
        errors.append(f"billing_as_test_failure:{prefix}")
    if category == "CI_WORKFLOW_FAILURE" and billing == "billing_not_started":
        errors.append(f"billing_vs_true_ci_inconsistent:{prefix}:{billing}")


def _refuse_billing_as_pass(
    row: Mapping[str, Any], prefix: str, errors: list[str]
) -> None:
    classified = _classification(row)
    if _is_pass_value(classified.get("scientific_claim_status")):
        errors.append(f"billing_not_started_as_pytest_pass:{prefix}")
    if _is_pass_value(row.get("test_results")) or _is_pass_value(row.get("pytest_result")):
        errors.append(f"billing_not_started_as_pytest_pass:{prefix}")
    if row.get("pytest_pass") is True:
        errors.append(f"billing_not_started_as_pytest_pass:{prefix}")
    status = row.get("verification_status")
    if isinstance(status, Mapping):
        if _is_pass_value(status.get("author_test_results")):
            errors.append(f"billing_not_started_as_pytest_pass:{prefix}")
        if _is_pass_value(status.get("scientific_pass")):
            errors.append(f"billing_not_started_as_pytest_pass:{prefix}")
    if _as_str(classified.get("author_claim_independently_verified")).strip().lower() in {
        "pass",
        "verified_pass",
    }:
        errors.append(f"billing_not_started_as_pytest_pass:{prefix}")


def _check_empty_step_as_test_failure(
    row: Mapping[str, Any], prefix: str, errors: list[str]
) -> None:
    if row.get("category") != "TEST_FAILURE":
        return
    blob = _blob(row).lower()
    has_empty = any(token in blob for token in EMPTY_STEP_TOKENS)
    has_test = any(token in blob for token in TEST_EVIDENCE_TOKENS)
    # A negated "pytest-node" mention on an empty-step CI log is not test evidence.
    if has_empty and not has_test:
        errors.append(f"empty_step_failure_as_test_failure:{prefix}")


def _check_isolated_counts(
    row: Mapping[str, Any],
    prefix: str,
    isolated_verified: Any,
    errors: list[str],
) -> None:
    if isolated_verified is not False:
        return
    classified = _classification(row)
    category = row.get("category")
    author_verified = classified.get("author_claim_independently_verified")
    if category in {"TEST_FAILURE", "TIMEOUT"} and author_verified is True:
        errors.append(f"unverified_isolated_counts_as_verified_pass:{prefix}")
    if isolated_verified is False and _is_pass_value(row.get("test_results")):
        errors.append(f"unverified_isolated_counts_as_verified_pass:{prefix}")
    if isolated_verified is False and _is_pass_value(
        classified.get("scientific_claim_status")
    ):
        errors.append(f"unverified_isolated_counts_as_verified_pass:{prefix}")
    if row.get("independently_verified") is True and category in {
        "TEST_FAILURE",
        "TIMEOUT",
    }:
        errors.append(f"unverified_isolated_counts_as_verified_pass:{prefix}")


def _check_dashboard(
    row: Mapping[str, Any], prefix: str, errors: list[str]
) -> None:
    if row.get("category") != "DASHBOARD_ISOLATION":
        return
    verified = row.get("independently_verified")
    classified = _classification(row)
    author_verified = classified.get("author_claim_independently_verified")
    lead = _as_str(row.get("lead_verification_status")).strip().lower()
    if verified is True and lead in {"unavailable", "unverified", ""}:
        errors.append(f"invented_dashboard_independently_verified:{prefix}")
    if verified is True and author_verified is False:
        errors.append(f"invented_dashboard_independently_verified:{prefix}")
    if author_verified is True and lead in {"unavailable", "unverified", ""}:
        errors.append(f"invented_dashboard_independently_verified:{prefix}")
    if _is_pass_value(row.get("lead_verification_status")) and verified is not True:
        errors.append(f"invented_dashboard_independently_verified:{prefix}")


def _memory_kind_token(row: Mapping[str, Any]) -> str:
    classified = _classification(row)
    kind = row.get("memory_kind")
    if kind is None:
        kind = classified.get("memory_kind")
    return _as_str(kind).strip().lower()


def _memory_has_numbers(row: Mapping[str, Any]) -> bool:
    for path, value in _walk(row):
        leaf = path.rsplit(".", 1)[-1]
        if leaf in MEMORY_NUMBER_KEYS:
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                return True
            if isinstance(value, str) and any(ch.isdigit() for ch in value):
                return True
    return False


def _memory_verified(row: Mapping[str, Any]) -> bool:
    if row.get("independently_verified") is True:
        return True
    classified = _classification(row)
    if classified.get("independently_verified") is True:
        return True
    token = _as_str(
        row.get("independently_verified") or classified.get("independently_verified")
    ).strip().lower()
    return token in {"verified", "true"}


def _kind_is_labeled(kind: str) -> bool:
    if not kind:
        return False
    if kind in MEMORY_KIND_ALLOWED:
        return True
    return "rss" in kind or "tracemalloc" in kind


def _check_memory(row: Mapping[str, Any], prefix: str, errors: list[str]) -> None:
    category = row.get("category")
    kind = _memory_kind_token(row)
    has_kind_field = "memory_kind" in row or "memory_kind" in _classification(row)
    has_numbers = _memory_has_numbers(row)
    verified = _memory_verified(row)
    relevant = category == "MEMORY_EVIDENCE" or has_kind_field or has_numbers or verified
    if not relevant:
        return
    labeled = _kind_is_labeled(kind)
    unavailable = kind == "unavailable"
    if verified and not labeled:
        errors.append(f"unlabeled_memory_as_verified:{prefix}")
    if verified and unavailable:
        errors.append(f"unlabeled_memory_as_verified:{prefix}")
    if has_numbers and not labeled and not unavailable:
        errors.append(f"memory_kind_or_unavailable_required:{prefix}")
    if category == "MEMORY_EVIDENCE" and not has_kind_field and not unavailable:
        if verified or has_numbers:
            errors.append(f"memory_kind_or_unavailable_required:{prefix}")
