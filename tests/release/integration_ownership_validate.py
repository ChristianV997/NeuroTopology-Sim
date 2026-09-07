"""Fail-closed validators for the integration ownership inventory.

QA-owned importable surface. Release may later wrap these helpers in
``scripts/validate_integration_ownership.py``. Do not invent that script here.

This module is not compiled scientific evidence and never emits PASS from
synthetic, proxy, billing, empty-step CI, or unsupported rows. Inventory
rows are not empirical evidence.

Success is an empty error list. There is no warnings-as-success channel.
No GitHub / network calls.
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
INVENTORY_PATH = REPO_ROOT / "configs" / "release" / "integration_ownership.yaml"

ALLOWED_STATUSES: tuple[str, ...] = (
    "VERIFIED",
    "INTEGRATED_ONLY",
    "OPEN_REVIEW",
    "BLOCKED_BY_CI",
    "BLOCKED_BY_TESTS",
    "BLOCKED_BY_SCIENCE",
    "DUPLICATE",
    "SUPERSEDED",
    "NEEDS_HUMAN_REVIEW",
    "UNVERIFIED",
)
REQUIRED_ENVELOPE_FIELDS: tuple[str, ...] = (
    "kind",
    "allowed_statuses",
    "work_items",
    "current_integration",
    "CURRENT_INTEGRATION_HEAD",
    "empirical_pass_from_this_pack",
    "inventory_is_not_evidence",
    "sole_merger",
)
REQUIRED_WORK_ITEM_FIELDS: tuple[str, ...] = (
    "id",
    "status",
)
REQUIRED_CURRENT_INTEGRATION_FIELDS: tuple[str, ...] = (
    "head_ref_oid",
    "merged",
    "on_origin_main",
    "status",
)
REQUIRED_KIND = "integration_ownership_inventory"
SOLE_MERGER_TOKENS = frozenset({"codex_c", "codex c", "codexc"})
AUTHOR_BODY_SHA = "af3ac584277747ae29882d3f5a39af5c4a436f22"
AUTHOR_BODY_SHA_PREFIX = "af3ac5842777"
ALLOWED_GRAPH_ACTORS = frozenset(
    {
        "lead",
        "alfred",
        "integration",
        "research",
        "research and tooling",
        "qa",
        "release",
        "christian",
        "christian v",
        "christian v.",
        "codex c",
        "codex_c",
        "codexc",
    }
)
NO_ACT_BOT_TOKENS = (
    "researchy",
    "nightly",
    "lingxi",
    "tinkabot",
    "chiefofstaff",
    "chief of staff",
    "chief_of_staff",
)
PASS_STRINGS = frozenset(
    {"pass", "scientific_pass", "verified_pass", "empirical_pass", "passed"}
)
EMPTY_STEP_TOKENS = (
    "steps=[]",
    "empty step",
    "empty-step",
    "empty_step",
    "~3s",
    "wall times ~3s",
    "jobs ~3s",
    "failure in ~3s",
    "unstarted",
    "jobs never run",
    "job was not started",
    "jobs were not started",
    "blobnotfound",
)
BILLING_UNSTARTED_TOKENS = (
    "billing_not_started",
    "billing-not-started",
    "billing blocked",
    "billing_blocked",
    "payments failed",
    "spending limit",
    "job was not started",
    "jobs never run",
    "unstarted",
)
PYTEST_NODE_TOKENS = (
    "pytest-node",
    "pytest node",
    "failed node id",
    "===== failures =====",
)
ISOLATED_COUNT_TOKENS = (
    "415/75/64/8/3",
    "exit 124",
    "exit124",
    "isolated run",
    "isolated-run",
    "author-claimed isolated",
    "415 files",
    "75 batches",
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
    ("google_api_key", re.compile(r"\bAIza[0-9A-Z]{35}\b")),
)


class IntegrationOwnershipValidationError(Exception):
    """Raised when validate(..., raise_on_error=True) sees one or more errors."""

    def __init__(self, errors: Sequence[str]) -> None:
        self.errors = list(errors)
        super().__init__(list(self.errors))


def load_yaml(path: str | Path) -> Any:
    text = Path(path).read_text(encoding="utf-8")
    return yaml.safe_load(text)


def load_inventory(path: str | Path | None = None) -> dict[str, Any]:
    doc = load_yaml(path or INVENTORY_PATH)
    if not isinstance(doc, dict):
        raise IntegrationOwnershipValidationError(["inventory:not_a_mapping"])
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
    _validate_inventory(doc, errors)
    return _finish(errors, raise_on_error)


def validate_integration_ownership(
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
        raise IntegrationOwnershipValidationError(unique)
    return unique


def _as_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _norm(value: Any) -> str:
    token = _as_str(value).strip().lower()
    token = token.replace("_", " ").replace("-", " ")
    token = re.sub(r"\s+", " ", token)
    return token


def _compact(value: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", _norm(value))


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


def _work_items(doc: Mapping[str, Any]) -> list[Any]:
    raw = doc.get("work_items")
    if raw is None:
        return []
    if not isinstance(raw, list):
        return [{"__invalid_work_items__": True}]
    return raw


def _context_rows(doc: Mapping[str, Any]) -> list[Any]:
    raw = doc.get("context_unmerged_named_by_236")
    if not isinstance(raw, list):
        return []
    return raw


def _reported_heads(doc: Mapping[str, Any]) -> list[Any]:
    reported = doc.get("reported_vs_live_heads")
    if not isinstance(reported, Mapping):
        return []
    rows = reported.get("reported")
    if not isinstance(rows, list):
        return []
    return rows


def _blob(obj: Any) -> str:
    parts: list[str] = []
    for _, value in _walk(obj):
        if isinstance(value, (str, int, float)) and not isinstance(value, bool):
            parts.append(_as_str(value))
    return "\n".join(parts)


def _row_blob(row: Mapping[str, Any]) -> str:
    parts: list[str] = []
    for key in (
        "notes",
        "evidence",
        "limitations",
        "title",
        "ci_status",
        "status",
        "summary",
    ):
        value = row.get(key)
        if isinstance(value, list):
            parts.extend(_as_str(item) for item in value)
        elif value is not None:
            parts.append(_as_str(value))
    label = row.get("research_claim_label")
    if isinstance(label, Mapping):
        parts.append(_blob(label))
    return "\n".join(parts)


def _is_body_sha(value: Any) -> bool:
    token = _as_str(value).strip().lower()
    if not token:
        return False
    if token == AUTHOR_BODY_SHA:
        return True
    return token.startswith(AUTHOR_BODY_SHA_PREFIX)


def _sha_token(value: Any) -> str:
    return _as_str(value).strip().lower()


def _validate_inventory(doc: Mapping[str, Any], errors: list[str]) -> None:
    _require_keys(doc, REQUIRED_ENVELOPE_FIELDS, "", errors)
    if "kind" in doc and doc.get("kind") != REQUIRED_KIND:
        errors.append(f"unexpected_kind:{doc.get('kind')}")

    if doc.get("inventory_is_not_evidence") is not True:
        if "inventory_is_not_evidence" in doc:
            errors.append("inventory_is_not_evidence_must_be_true")

    pack_empirical = doc.get("empirical_pass_from_this_pack")
    if pack_empirical is True or (
        "empirical_pass_from_this_pack" in doc and pack_empirical is not False
    ):
        errors.append("empirical_pass_from_this_pack_must_be_false")

    if _is_pass_value(doc.get("scientific_pass_from_this_pack")):
        errors.append("invented_scientific_pass:pack")

    _check_allowed_statuses_enum(doc, errors)
    _check_sole_merger(doc, errors)
    _check_live_head(doc, errors)
    _check_synthetic_and_proxy(doc, errors)
    _check_ownership_graph(doc, errors)
    _check_isolated_verified(doc, errors)

    current = doc.get("current_integration")
    if "current_integration" in doc:
        _require_keys(
            current if isinstance(current, Mapping) else None,
            REQUIRED_CURRENT_INTEGRATION_FIELDS,
            "current_integration",
            errors,
        )
        if isinstance(current, Mapping):
            _check_status_row(current, "current_integration", errors)
            _check_empty_step(current, "current_integration", errors, pack=doc)
            _check_billing_as_pass(current, "current_integration", errors)

    research = doc.get("research_phase")
    research_labeled = False
    if research is not None:
        if not isinstance(research, Mapping):
            errors.append("research_phase:not_a_mapping")
        else:
            research_labeled = True
            if research.get("inventory_is_not_evidence") is False:
                errors.append("research_phase.inventory_is_not_evidence_must_be_true")
            if research.get("empirical_pass_from_this_pack") is True:
                errors.append("research_phase.empirical_pass_from_this_pack_must_be_false")
            if _is_pass_value(research.get("scientific_pass_from_this_pack")):
                errors.append("invented_scientific_pass:research_phase")
            if research.get("researchy_acted") is True:
                errors.append("researchy_as_research")
            classifier = _norm(research.get("classifier"))
            if "researchy" in classifier:
                errors.append("researchy_as_research")

    rows = _work_items(doc)
    if doc.get("work_items") is not None and not isinstance(doc.get("work_items"), list):
        errors.append("work_items:not_a_list")
        return

    seen_ids: dict[str, str] = {}
    for index, raw in enumerate(rows):
        prefix = f"work_items[{index}]"
        if not isinstance(raw, Mapping):
            errors.append(f"{prefix}:not_a_mapping")
            continue
        _require_keys(raw, REQUIRED_WORK_ITEM_FIELDS, prefix, errors)
        ident = raw.get("id")
        if isinstance(ident, str) and ident:
            if ident in seen_ids:
                errors.append(f"duplicate_id:{ident}")
            else:
                seen_ids[ident] = prefix
        if research_labeled and "research_claim_label" not in raw:
            errors.append(f"missing_field:{prefix}.research_claim_label")
        _check_status_row(raw, prefix, errors)
        _check_empty_step(raw, prefix, errors, pack=doc)
        _check_billing_as_pass(raw, prefix, errors)
        _check_row_isolated(raw, prefix, errors)

    for index, raw in enumerate(_context_rows(doc)):
        prefix = f"context_unmerged_named_by_236[{index}]"
        if not isinstance(raw, Mapping):
            errors.append(f"{prefix}:not_a_mapping")
            continue
        ident = raw.get("id")
        if isinstance(ident, str) and ident:
            if ident in seen_ids:
                errors.append(f"duplicate_id:{ident}")
            else:
                seen_ids[ident] = prefix
        if "id" not in raw or raw.get("id") is None:
            errors.append(f"missing_field:{prefix}.id")
        if "status" in raw:
            _check_status_row(raw, prefix, errors)
        if research_labeled and "research_claim_label" not in raw:
            errors.append(f"missing_field:{prefix}.research_claim_label")

    for index, raw in enumerate(_reported_heads(doc)):
        prefix = f"reported_vs_live_heads.reported[{index}]"
        if not isinstance(raw, Mapping):
            errors.append(f"{prefix}:not_a_mapping")
            continue
        _check_status_row(raw, prefix, errors)
        oid = raw.get("oid") or raw.get("matching_live_full_oid")
        if _is_body_sha(oid) and _as_str(raw.get("status")).strip().upper() != "UNVERIFIED":
            errors.append(f"body_sha_as_live_head:{prefix}")
        if _is_body_sha(oid) and _norm(raw.get("role")) in {
            "current",
            "current integration head",
            "live",
            "current_prefix_of_live_head",
        }:
            errors.append(f"body_sha_as_live_head:{prefix}")

    _check_issues_isolated(doc, errors)
    _check_rollup_empty_step(doc, errors)


def _check_allowed_statuses_enum(doc: Mapping[str, Any], errors: list[str]) -> None:
    allowed = doc.get("allowed_statuses")
    if allowed is None:
        return
    if not isinstance(allowed, list):
        errors.append("allowed_statuses:not_a_list")
        return
    allowed_set = {item for item in allowed if isinstance(item, str)}
    expected = set(ALLOWED_STATUSES)
    extra = allowed_set - expected
    missing = expected - allowed_set
    for item in sorted(extra):
        errors.append(f"invalid_allowed_status:{item}")
    for item in sorted(missing):
        errors.append(f"missing_allowed_status:{item}")


def _status_values(row: Mapping[str, Any]) -> list[str]:
    values: list[str] = []
    for key in ("status", "ci_status", "integration_presence"):
        raw = row.get(key)
        if isinstance(raw, str) and raw.strip():
            values.append(raw.strip())
        elif isinstance(raw, list):
            values.extend(
                item.strip() for item in raw if isinstance(item, str) and item.strip()
            )
    return values


def _primary_status(row: Mapping[str, Any]) -> str:
    raw = row.get("status")
    if isinstance(raw, str):
        return raw.strip()
    return ""


def _check_status_row(row: Mapping[str, Any], prefix: str, errors: list[str]) -> None:
    for item in _status_values(row):
        if item not in ALLOWED_STATUSES:
            errors.append(f"invalid_status:{prefix}:{item}")
    status = _primary_status(row)
    merged = row.get("merged")
    on_main = row.get("on_origin_main")
    github_state = _as_str(row.get("github_state")).strip().upper()
    base = _as_str(row.get("base_ref_name")).strip().lower()
    prn = row.get("pr_number")

    if status == "INTEGRATED_ONLY":
        implies_main = on_main is True
        merged_to_main = merged is True and (on_main is True or base in {"main", "origin/main"})
        if implies_main or merged_to_main:
            errors.append(f"integrated_only_as_main:{prefix}")

    if status == "VERIFIED":
        supported = merged is True and on_main is True
        if not supported:
            openish = (
                merged is False
                or on_main is False
                or github_state in {"OPEN", "DRAFT"}
                or prn == 236
            )
            if openish:
                errors.append(f"invented_verified_on_open:{prefix}")
            else:
                errors.append(f"invented_verified:{prefix}")


def _head_locations(doc: Mapping[str, Any]) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    top = _sha_token(doc.get("CURRENT_INTEGRATION_HEAD"))
    if top:
        found.append(("CURRENT_INTEGRATION_HEAD", top))
    current = doc.get("current_integration")
    if isinstance(current, Mapping):
        oid = _sha_token(current.get("head_ref_oid"))
        if oid:
            found.append(("current_integration.head_ref_oid", oid))
    reported = doc.get("reported_vs_live_heads")
    if isinstance(reported, Mapping):
        oid = _sha_token(reported.get("live_oid"))
        if oid:
            found.append(("reported_vs_live_heads.live_oid", oid))
    research = doc.get("research_phase")
    if isinstance(research, Mapping):
        oid = _sha_token(research.get("current_integration_head"))
        if oid:
            found.append(("research_phase.current_integration_head", oid))
    return found


def _check_live_head(doc: Mapping[str, Any], errors: list[str]) -> None:
    locations = _head_locations(doc)
    for loc, oid in locations:
        if _is_body_sha(oid):
            errors.append(f"body_sha_as_live_head:{loc}")
    unique = {oid for _, oid in locations}
    if len(unique) > 1:
        errors.append("live_head_mismatch")
    for index, raw in enumerate(_work_items(doc)):
        if not isinstance(raw, Mapping):
            continue
        if raw.get("pr_number") != 236:
            continue
        oid = _sha_token(raw.get("head_ref_oid"))
        if oid and _is_body_sha(oid):
            errors.append(f"body_sha_as_live_head:work_items[{index}].head_ref_oid")


def _check_synthetic_and_proxy(doc: Mapping[str, Any], errors: list[str]) -> None:
    for path, value in _walk(doc):
        leaf = path.rsplit(".", 1)[-1]
        if leaf in {
            "synthetic_status",
            "synthetic",
        }:
            token = _as_str(value).strip().upper()
            if token and token != "NOT_SUPPORTED":
                if _is_pass_value(value) or token in {"PASS", "SUPPORTED", "TRUE"}:
                    errors.append(f"invented_scientific_pass:{path}")
                errors.append("synthetic_status_must_be_NOT_SUPPORTED")
        if leaf == "proxy_bayes_equals_formal" and value is not False:
            if value is True or _is_pass_value(value):
                errors.append("proxy_bayes_equals_formal_must_be_false")
        if leaf in {
            "scientific_pass",
            "scientific_pass_from_this_pack",
            "empirical_pass",
        } and _is_pass_value(value):
            errors.append(f"invented_scientific_pass:{path}")


def _is_sole_merger_token(value: Any) -> bool:
    return _compact(value) in {"codexc"} or _norm(value) in SOLE_MERGER_TOKENS


def _check_sole_merger(doc: Mapping[str, Any], errors: list[str]) -> None:
    if "sole_merger" in doc and not _is_sole_merger_token(doc.get("sole_merger")):
        errors.append("competing_merger:envelope")
    graph = doc.get("alfred_ownership_graph")
    if isinstance(graph, Mapping) and "sole_merger" in graph:
        if not _is_sole_merger_token(graph.get("sole_merger")):
            errors.append("competing_merger:alfred_ownership_graph")
    decisions = doc.get("ownership_decisions")
    roles = decisions.get("roles") if isinstance(decisions, Mapping) else None
    if isinstance(roles, Mapping):
        for key, raw in roles.items():
            if not isinstance(raw, Mapping):
                continue
            name = raw.get("name")
            scope = _norm(raw.get("scope"))
            may_merge = raw.get("may_merge")
            compete = raw.get("compete")
            is_codex = _is_sole_merger_token(name) or _compact(key) == "codexc"
            if scope == "sole merger" and not is_codex:
                errors.append(f"competing_merger:ownership_decisions.roles.{key}")
            if may_merge is True and not is_codex:
                errors.append(f"competing_merger:ownership_decisions.roles.{key}")
            if is_codex and compete is True:
                errors.append("competing_merger:codex_c.compete")
    merger_instruction = _norm(doc.get("merger_instruction"))
    if merger_instruction in {"merge", "merge now", "allowed to merge"}:
        errors.append("competing_merger:merger_instruction")


def _iter_role_entries(doc: Mapping[str, Any]) -> list[tuple[str, str, Mapping[str, Any]]]:
    entries: list[tuple[str, str, Mapping[str, Any]]] = []
    decisions = doc.get("ownership_decisions")
    roles = decisions.get("roles") if isinstance(decisions, Mapping) else None
    if isinstance(roles, Mapping):
        for key, raw in roles.items():
            if isinstance(raw, Mapping):
                entries.append((f"ownership_decisions.roles.{key}", _as_str(raw.get("name")), raw))
            else:
                entries.append((f"ownership_decisions.roles.{key}", _as_str(raw), {}))
    graph = doc.get("alfred_ownership_graph")
    if isinstance(graph, Mapping):
        for key in (
            "human",
            "lead_developer",
            "organization_auditor",
            "integration",
            "research",
            "research_and_tooling",
            "qa",
            "release",
            "sole_evidence_authority",
        ):
            if key not in graph:
                continue
            value = graph.get(key)
            if isinstance(value, list):
                for item in value:
                    entries.append((f"alfred_ownership_graph.{key}", _as_str(item), {}))
            else:
                entries.append((f"alfred_ownership_graph.{key}", _as_str(value), {}))
    used = doc.get("bots_used")
    if isinstance(used, list):
        for index, item in enumerate(used):
            entries.append((f"bots_used[{index}]", _as_str(item), {}))
    return entries


def _no_act_token_in(name: str) -> str | None:
    compact = _compact(name)
    normed = _norm(name)
    if "researchy" in compact or "researchy" in normed:
        return "researchy"
    if "nightly" in compact or "nightly" in normed:
        return "nightly"
    if "lingxi" in compact or "lingxi" in normed:
        return "lingxi"
    if "tinkabot" in compact:
        return "tinkabot"
    if "chiefofstaff" in compact or "chief of staff" in normed:
        return "chief_of_staff"
    return None


def _lingxi_assigned(doc: Mapping[str, Any]) -> bool:
    dup = doc.get("duplicate_decisions_this_wave")
    if not isinstance(dup, Mapping):
        return False
    bots = dup.get("bots")
    if not isinstance(bots, list):
        return False
    for raw in bots:
        if not isinstance(raw, Mapping):
            continue
        if _no_act_token_in(_as_str(raw.get("id"))) != "lingxi":
            continue
        if raw.get("act_this_wave") is True:
            return True
    return False


def _check_ownership_graph(doc: Mapping[str, Any], errors: list[str]) -> None:
    lead_names: list[str] = []
    research_names: list[str] = []
    qa_names: list[str] = []
    integration_names: list[str] = []
    evidence_authorities: list[str] = []

    for loc, name, raw in _iter_role_entries(doc):
        token = _no_act_token_in(name)
        loc_l = loc.lower()
        is_lead_slot = "lead_developer" in loc_l or loc_l.endswith(".lead")
        is_research_slot = "research" in loc_l and "researchy" not in loc_l
        is_qa_slot = loc_l.endswith(".qa") or ".qa" in loc_l
        is_integration_slot = "integration" in loc_l
        is_release_slot = "release" in loc_l or "evidence_authority" in loc_l

        if is_lead_slot and name.strip():
            lead_names.append(_norm(name))
        if is_research_slot and name.strip():
            research_names.append(_norm(name))
        if is_qa_slot and name.strip():
            qa_names.append(_norm(name))
        if is_integration_slot and name.strip():
            integration_names.append(_norm(name))
        if is_release_slot and name.strip():
            evidence_authorities.append(_norm(name))

        if token == "researchy" and (is_research_slot or "classifier" in loc_l):
            errors.append("researchy_as_research")
        elif token == "researchy":
            errors.append(f"no_act_bot_as_owner:{loc}")
        if token == "lingxi" and is_lead_slot:
            errors.append("lingxi_as_lead")
        elif token == "lingxi" and is_qa_slot:
            errors.append("lingxi_as_qa")
        elif token == "lingxi" and not _lingxi_assigned(doc):
            errors.append(f"no_act_bot_as_owner:{loc}")
        if token == "nightly" and is_integration_slot:
            errors.append("nightly_as_integration")
        elif token == "nightly":
            errors.append(f"no_act_bot_as_owner:{loc}")
        if token == "chief_of_staff" and is_lead_slot:
            errors.append("chief_of_staff_as_lead")
        elif token == "chief_of_staff":
            errors.append(f"no_act_bot_as_owner:{loc}")
        if token == "tinkabot":
            errors.append(f"no_act_bot_as_owner:{loc}")

        if raw.get("second_evidence_authority") is True:
            errors.append(f"second_evidence_authority:{loc}")
        scope = _norm(raw.get("scope"))
        if "evidence authority" in scope and "sole" not in scope:
            if _norm(raw.get("name")) != "release":
                errors.append(f"second_evidence_authority:{loc}")

    unique_leads = {item for item in lead_names if item}
    if len(unique_leads) > 1:
        errors.append("dual_primary_owners")
    primary = doc.get("primary_owners")
    if isinstance(primary, list) and len({_norm(item) for item in primary if _as_str(item).strip()}) > 1:
        errors.append("dual_primary_owners")
    graph = doc.get("alfred_ownership_graph")
    if isinstance(graph, Mapping):
        lead = graph.get("lead_developer")
        if isinstance(lead, list) and len({_norm(item) for item in lead if _as_str(item).strip()}) > 1:
            errors.append("dual_primary_owners")
        authority = graph.get("sole_evidence_authority")
        if authority is not None and _norm(authority) not in {"release", ""}:
            errors.append("second_evidence_authority:alfred_ownership_graph")

    decisions = doc.get("ownership_decisions")
    roles = decisions.get("roles") if isinstance(decisions, Mapping) else None
    if isinstance(roles, Mapping):
        owners: list[str] = []
        for key, raw in roles.items():
            if not isinstance(raw, Mapping):
                continue
            scope = _norm(raw.get("scope"))
            if "work_order_owner" in scope or key == "lead_developer":
                name = _norm(raw.get("name"))
                if name:
                    owners.append(name)
        if len(set(owners)) > 1:
            errors.append("dual_primary_owners")
        release = roles.get("release")
        if isinstance(release, Mapping) and release.get("second_evidence_authority") is True:
            errors.append("second_evidence_authority:ownership_decisions.roles.release")


def _empty_step_blob(row: Mapping[str, Any], pack: Mapping[str, Any] | None) -> str:
    parts = [_row_blob(row)]
    if pack is not None:
        rollup = pack.get("status_check_rollup_236")
        if isinstance(rollup, Mapping):
            parts.append(_blob(rollup))
        warnings = pack.get("required_warnings")
        if isinstance(warnings, list):
            parts.extend(_as_str(item) for item in warnings)
    return "\n".join(parts).lower()


def _has_empty_step(blob: str) -> bool:
    return any(token in blob for token in EMPTY_STEP_TOKENS)


def _has_pytest_node(blob: str) -> bool:
    if not any(token in blob for token in PYTEST_NODE_TOKENS):
        return False
    negated = any(
        token in blob
        for token in (
            "not a pytest-node",
            "not pytest-node",
            "not a pytest node",
            "≠ pytest",
            "!= pytest",
            "never pytest",
        )
    )
    strong = any(token in blob for token in ("failed node id", "===== failures ====="))
    if negated and not strong:
        return False
    return True


def _blocked_by_tests(row: Mapping[str, Any]) -> bool:
    return any(item == "BLOCKED_BY_TESTS" for item in _status_values(row))


def _check_empty_step(
    row: Mapping[str, Any],
    prefix: str,
    errors: list[str],
    *,
    pack: Mapping[str, Any] | None = None,
) -> None:
    if not _blocked_by_tests(row):
        return
    blob = _empty_step_blob(row, pack)
    if _has_empty_step(blob) and not _has_pytest_node(blob):
        errors.append(f"empty_step_as_blocked_by_tests:{prefix}")


def _check_rollup_empty_step(doc: Mapping[str, Any], errors: list[str]) -> None:
    rollup = doc.get("status_check_rollup_236")
    if not isinstance(rollup, Mapping):
        return
    blob = _blob(rollup).lower()
    if not _has_empty_step(blob):
        return
    labeled = _as_str(rollup.get("status")).strip().upper() == "BLOCKED_BY_TESTS"
    labeled = labeled or _as_str(rollup.get("ci_status")).strip().upper() == "BLOCKED_BY_TESTS"
    if labeled and not _has_pytest_node(blob):
        errors.append("empty_step_as_blocked_by_tests:status_check_rollup_236")


def _check_billing_as_pass(row: Mapping[str, Any], prefix: str, errors: list[str]) -> None:
    blob = _row_blob(row).lower()
    billing = any(token in blob for token in BILLING_UNSTARTED_TOKENS)
    if row.get("billing_not_started") is True:
        billing = True
    if not billing:
        return
    if _is_pass_value(row.get("test_results")) or _is_pass_value(row.get("pytest_result")):
        errors.append(f"billing_unstarted_as_pytest_pass:{prefix}")
    if row.get("pytest_pass") is True:
        errors.append(f"billing_unstarted_as_pytest_pass:{prefix}")
    if _is_pass_value(row.get("scientific_pass")):
        errors.append(f"billing_unstarted_as_pytest_pass:{prefix}")


def _mentions_isolated(obj: Any) -> bool:
    blob = _blob(obj).lower()
    if any(token in blob for token in ISOLATED_COUNT_TOKENS):
        return True
    if "415" in blob and "75" in blob and "isolated" in blob:
        return True
    if "64 passed" in blob and "8 failed" in blob:
        return True
    return False


def _independently_verified_true(obj: Mapping[str, Any]) -> bool:
    if obj.get("independently_verified") is True:
        return True
    token = _as_str(obj.get("independently_verified")).strip().lower()
    if token in {"true", "verified", "pass", "verified_pass"}:
        return True
    label = obj.get("research_claim_label")
    if isinstance(label, Mapping) and label.get("independently_verified") is True:
        return True
    claims = obj.get("scientific_claims")
    if isinstance(claims, Mapping) and claims.get("independently_verified") is True:
        return True
    return False


def _check_row_isolated(row: Mapping[str, Any], prefix: str, errors: list[str]) -> None:
    if _independently_verified_true(row) and _mentions_isolated(row):
        errors.append(f"invented_isolated_verified:{prefix}")


def _check_isolated_verified(doc: Mapping[str, Any], errors: list[str]) -> None:
    isolated = doc.get("author_claimed_isolated_run")
    if isinstance(isolated, Mapping):
        if _independently_verified_true(isolated) or _is_pass_value(
            isolated.get("test_results")
        ) or _is_pass_value(isolated.get("verified_pass")):
            errors.append("invented_isolated_verified:author_claimed_isolated_run")
        if isolated.get("treat_as_verified_pass") is True:
            errors.append("invented_isolated_verified:author_claimed_isolated_run")


def _check_issues_isolated(doc: Mapping[str, Any], errors: list[str]) -> None:
    issues = doc.get("scientific_claim_issues")
    if not isinstance(issues, list):
        return
    for index, raw in enumerate(issues):
        if not isinstance(raw, Mapping):
            continue
        prefix = f"scientific_claim_issues[{index}]"
        ident = _as_str(raw.get("id")).lower()
        if "isolated" in ident or _mentions_isolated(raw):
            if _independently_verified_true(raw) or _is_pass_value(raw.get("claim_status")):
                errors.append(f"invented_isolated_verified:{prefix}")
            if _as_str(raw.get("status")).strip().upper() == "VERIFIED":
                errors.append(f"invented_isolated_verified:{prefix}")
