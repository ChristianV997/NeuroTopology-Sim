"""Fail-closed PR retirement matrix rules (QA).

Importable helpers so Release can later wrap
``scripts/validate_pr_retirement_matrix.py`` without rewriting rules.

This module does not invent scientific PASS, biological evidence, duplicates,
whole-PR supersedes, or merge/close instructions. Inventory is not evidence.
Warnings never count as success.

No network. No secrets. Deterministic for a given mapping.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MATRIX_PATH = REPO_ROOT / "configs" / "release" / "pr_retirement_matrix.yaml"
FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "pr_retirement"

# Lead set. Careful work-order hints do not imply close / merge / retire.
LEAD_STATUS_HINTS = frozenset({"keep_open", "needs_human_review"})
CAREFUL_WO_STATUS_HINTS = frozenset(
    {
        "wait",
        "blocked",
        "hold",
        "parked",
        "deferred",
        "in_review",
        "wo_open",
        "wo_blocked",
        "wo_wait",
    }
)
ALLOWED_STATUS_HINTS = LEAD_STATUS_HINTS | CAREFUL_WO_STATUS_HINTS

RETIRE_OR_MERGE_HINTS = frozenset(
    {
        "close",
        "closed",
        "merge",
        "merged",
        "retire",
        "retired",
        "ready_to_merge",
        "recommend_merge",
        "recommend_close",
        "recommend_retire",
        "do_merge",
        "do_close",
        "do_retire",
        "merge_now",
        "close_now",
        "retire_now",
    }
)

# proxy_flagged / bayesian_warning / claim_class proxy — these ids only.
ALLOWED_PROXY_IDENTIFIERS = frozenset(
    {
        "nts-pr-219",
        "219",
        "pr219",
        "pr-219",
        "nts-pr-226",
        "226",
        "pr226",
        "pr-226",
        "nts-branch-scientific-falsification-contract",
        "codex/scientific-falsification-contract",
        "scientific-falsification-contract",
    }
)

# Child → parent order. Do not retire/merge a descendant before an ancestor.
CANONICAL_STACK_CHAINS: tuple[tuple[int, ...], ...] = (
    (211, 215, 224, 232),
    (212, 220),
    (219, 226),
    (213, 227),
)

STACK_RELATIONSHIP_KINDS = frozenset({"stacked", "stacked_chain"})

CI_NON_PASS_CLASSES = frozenset(
    {
        "billing_not_started",
        "disk_fail",
        "job_started_install_fail",
        "enospc",
        "enospace",
    }
)

PASS_TOKENS = frozenset({"pass", "passed", "success", "successful", "green"})
OPEN_LIKE_STATES = frozenset({"OPEN", "DRAFT", "BRANCH_ONLY"})

_BILLING_MARKERS = (
    "billing_not_started",
    "spending limit",
    "account payments have failed",
    "payments/spending-limit",
)
_ENOSPC_MARKERS = (
    "enospc",
    "errno 28",
    "no space left on device",
    "disk_fail",
    "disk-full",
    "disk full",
)


@dataclass(frozen=True)
class ValidationResult:
    """Fail-closed result. ``ok`` is true only when ``errors`` is empty."""

    errors: tuple[str, ...]
    warnings: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.errors


class MatrixLoadError(ValueError):
    """Matrix could not be loaded as a mapping."""


def load_matrix(path: str | Path) -> dict[str, Any]:
    raw = Path(path).read_text(encoding="utf-8")
    data = yaml.safe_load(raw)
    if not isinstance(data, dict):
        raise MatrixLoadError(f"matrix is not a mapping: {path}")
    return data


def validate_path(path: str | Path | None = None) -> ValidationResult:
    target = Path(path) if path is not None else DEFAULT_MATRIX_PATH
    try:
        data = load_matrix(target)
    except (OSError, yaml.YAMLError, MatrixLoadError) as exc:
        return ValidationResult(errors=(f"matrix_load: {target}: {exc}",))
    return validate_matrix(data)


def validate_pr_retirement_matrix(
    source: Mapping[str, Any] | str | Path | None = None,
) -> ValidationResult:
    """Validate a mapping or a YAML path. Default is the live matrix."""
    if source is None or isinstance(source, (str, Path)):
        return validate_path(source)
    return validate_matrix(source)


def validate_matrix(data: Mapping[str, Any]) -> ValidationResult:
    errors: list[str] = []
    rows = _as_list(data.get("rows"))

    _check_research_locks(rows, errors)
    _check_invented_pass(data, rows, errors)
    _check_proxy_flags(rows, errors)
    _check_duplicates(data, errors)
    _check_superseded(data, errors)
    _check_stacked_child_before_parent(data, rows, errors)
    _check_open_as_merged(rows, errors)
    _check_billing_enospc_not_pass(data, rows, errors)
    _check_status_hints(data, rows, errors)

    return ValidationResult(errors=tuple(errors))


def detect_stack_edges(data: Mapping[str, Any]) -> frozenset[tuple[int, int]]:
    """Return ``(child_pr, parent_pr)`` pairs, including transitive ancestors.

    Sources: canonical chains plus ``relationships`` with stacked kinds.
    """
    pairs: set[tuple[int, int]] = set(_canonical_stack_pairs())
    for rel in _as_list(data.get("relationships")):
        if not isinstance(rel, Mapping):
            continue
        kind = str(rel.get("kind") or "").strip().lower()
        if kind not in STACK_RELATIONSHIP_KINDS:
            continue
        members = [_coerce_pr(x) for x in _as_list(rel.get("members"))]
        members = [m for m in members if m is not None]
        if len(members) >= 2:
            pairs.update(_pairs_along_chain(tuple(members)))
        for edge in _as_list(rel.get("edges")):
            if not isinstance(edge, Mapping):
                continue
            child = _coerce_pr(edge.get("from"))
            parent = _coerce_pr(edge.get("to"))
            if child is not None and parent is not None:
                pairs.add((child, parent))
        child = _coerce_pr(rel.get("from"))
        parent = _coerce_pr(rel.get("to"))
        if child is not None and parent is not None:
            pairs.add((child, parent))
    return frozenset(pairs)


def child_before_parent_violations(
    data: Mapping[str, Any],
    rows: Iterable[Mapping[str, Any]] | None = None,
) -> tuple[str, ...]:
    errors: list[str] = []
    row_list = list(rows) if rows is not None else _as_list(data.get("rows"))
    _check_stacked_child_before_parent(data, row_list, errors)
    return tuple(errors)


def run_validation(path: str | Path | None = None) -> int:
    """Return 0 if clean else 1. Release may wrap this without rewriting rules."""
    result = validate_path(path)
    return 0 if result.ok else 1


def _canonical_stack_pairs() -> set[tuple[int, int]]:
    pairs: set[tuple[int, int]] = set()
    for chain in CANONICAL_STACK_CHAINS:
        pairs.update(_pairs_along_chain(chain))
    return pairs


def _pairs_along_chain(chain: tuple[int, ...]) -> set[tuple[int, int]]:
    pairs: set[tuple[int, int]] = set()
    for index, child in enumerate(chain):
        for parent in chain[:index]:
            pairs.add((child, parent))
    return pairs


def _check_research_locks(rows: list[Any], errors: list[str]) -> None:
    if not rows:
        errors.append("scientific_locks: matrix has no rows")
        return
    for row in rows:
        if not isinstance(row, Mapping):
            errors.append("scientific_locks: row is not a mapping")
            continue
        label = _row_label(row)
        rc = row.get("research_classification")
        if not isinstance(rc, Mapping):
            errors.append(
                f"scientific_locks: {label} missing research_classification "
                "with scientific_pass_allowed=false and biological_evidence=false"
            )
            continue
        if rc.get("scientific_pass_allowed") is not False:
            errors.append(
                f"scientific_locks: {label} scientific_pass_allowed must be false "
                f"(got {rc.get('scientific_pass_allowed')!r})"
            )
        if rc.get("biological_evidence") is not False:
            errors.append(
                f"scientific_locks: {label} biological_evidence must be false "
                f"(got {rc.get('biological_evidence')!r})"
            )


def _check_invented_pass(
    data: Mapping[str, Any],
    rows: list[Any],
    errors: list[str],
) -> None:
    phase = data.get("research_phase")
    if isinstance(phase, Mapping):
        if phase.get("scientific_pass_from_this_pack") is True:
            errors.append(
                "invented_pass: research_phase.scientific_pass_from_this_pack "
                "invents a scientific PASS from inventory"
            )
        if phase.get("biological_evidence_from_this_pack") is True:
            errors.append(
                "invented_pass: research_phase.biological_evidence_from_this_pack "
                "invents biological evidence from inventory"
            )
        _flag_pass_fields("research_phase", phase, errors)

    _flag_pass_fields("matrix", data, errors)

    for row in rows:
        if not isinstance(row, Mapping):
            continue
        label = _row_label(row)
        _flag_pass_fields(label, row, errors)
        rc = row.get("research_classification")
        if isinstance(rc, Mapping):
            _flag_pass_fields(f"{label}.research_classification", rc, errors)


def _flag_pass_fields(scope: str, mapping: Mapping[str, Any], errors: list[str]) -> None:
    if mapping.get("scientific_pass_allowed") is True:
        errors.append(
            f"invented_pass: {scope} scientific_pass_allowed=true invents a "
            "scientific PASS from inventory"
        )
    if mapping.get("empirical_claim_present") is True:
        errors.append(
            f"invented_pass: {scope} empirical_claim_present=true invents an "
            "empirical claim/PASS from inventory"
        )
    for key in (
        "scientific_pass",
        "empirical_pass",
        "scientific_verdict",
        "empirical_verdict",
        "verdict",
        "claim_verdict",
        "pass_status",
        "claim_class",
    ):
        if key not in mapping:
            continue
        token = _norm_token(mapping.get(key))
        if token in PASS_TOKENS or token in {
            "scientific_pass",
            "empirical_pass",
            "scientificpass",
            "empiricalpass",
        }:
            errors.append(
                f"invented_pass: {scope} {key}={mapping.get(key)!r} invents a "
                "scientific/empirical PASS from inventory"
            )


def _check_proxy_flags(rows: list[Any], errors: list[str]) -> None:
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        if not _row_has_proxy_signal(row):
            continue
        if _row_proxy_allowed(row):
            continue
        label = _row_label(row)
        errors.append(
            f"proxy_flag_not_allowed: {label} proxy_flagged / bayesian_warning / "
            "claim_class proxy / evidence_mode=proxy is only allowed on nts-pr-219 "
            "(or pr 219), nts-pr-226 (or 226), and the falsification BRANCH_ONLY "
            "id (codex/scientific-falsification-contract)"
        )


def _row_has_proxy_signal(row: Mapping[str, Any]) -> bool:
    blobs: list[Mapping[str, Any]] = [row]
    rc = row.get("research_classification")
    if isinstance(rc, Mapping):
        blobs.append(rc)
    for blob in blobs:
        for key in (
            "proxy_evidence_flag",
            "proxy_flagged",
            "bayesian_warning",
            "proxy_bayes",
        ):
            if _truthy(blob.get(key)):
                return True
        claim_class = _norm_token(blob.get("claim_class"))
        if claim_class in {"proxy", "proxy_bayes", "bayesian_proxy", "proxybayes"}:
            return True
        if _norm_token(blob.get("evidence_mode")) == "proxy":
            return True
    return False


def _row_proxy_allowed(row: Mapping[str, Any]) -> bool:
    tokens = [
        _norm_token(row.get("id")),
        _norm_token(row.get("pr_number")),
        _norm_token(row.get("branch")),
    ]
    row_id = _norm_token(row.get("id"))
    if row_id.startswith("nts-pr-"):
        tokens.append(row_id.split("nts-pr-", 1)[1])
    return any(token in ALLOWED_PROXY_IDENTIFIERS for token in tokens if token)


def _check_duplicates(data: Mapping[str, Any], errors: list[str]) -> None:
    entries = list(_iter_named_entries(data, "duplicate_candidates"))
    phase = data.get("research_phase")
    if isinstance(phase, Mapping):
        for entry in _as_list(phase.get("duplicate_candidates_verified")):
            entries.append(("research_phase.duplicate_candidates_verified", entry))
    for row in _as_list(data.get("rows")):
        if not isinstance(row, Mapping):
            continue
        if row.get("duplicate_of") not in (None, "", False):
            entries.append((f"{_row_label(row)}.duplicate_of", row))
        for entry in _as_list(row.get("duplicate_candidates")):
            entries.append((f"{_row_label(row)}.duplicate_candidates", entry))

    for scope, entry in entries:
        if not _has_cited_evidence(entry):
            errors.append(
                f"duplicate_without_evidence: {scope} invents a duplicate "
                "without cited evidence fields"
            )


def _check_superseded(data: Mapping[str, Any], errors: list[str]) -> None:
    entries = list(_iter_named_entries(data, "superseded_candidates"))
    phase = data.get("research_phase")
    if isinstance(phase, Mapping):
        for entry in _as_list(phase.get("superseded_candidates_verified")):
            entries.append(("research_phase.superseded_candidates_verified", entry))

    for scope, entry in entries:
        if not isinstance(entry, Mapping):
            errors.append(
                f"invented_superseded: {scope} is not a mapping with cited evidence"
            )
            continue
        pr_number = _superseded_pr(entry)
        by = _coerce_pr(entry.get("superseded_by") if "superseded_by" in entry else entry.get("by"))
        whole = entry.get("whole_pr_superseded")
        if whole is None:
            whole = entry.get("whole_pr")
        scope_text = str(entry.get("scope") or "")
        docs_only = "docs" in scope_text.lower() or "inventory" in scope_text.lower()
        allowed_216 = (
            pr_number == 216
            and by == 225
            and whole is False
            and docs_only
        )
        if pr_number == 216 and whole is not False:
            errors.append(
                f"whole_pr_superseded: {scope} labels whole #216 superseded; "
                "only docs-only #216→#225 with whole_pr=false is allowed"
            )
            continue
        if allowed_216:
            continue
        if not _has_cited_evidence(entry):
            errors.append(
                f"invented_superseded: {scope} invents a superseded label "
                "without cited evidence fields"
            )


def _superseded_pr(entry: Mapping[str, Any]) -> int | None:
    direct = _coerce_pr(entry.get("pr_number"))
    if direct is not None:
        return direct
    for key in ("id", "scope"):
        parsed = _coerce_pr(entry.get(key))
        if parsed is not None:
            return parsed
    return None


def _check_stacked_child_before_parent(
    data: Mapping[str, Any],
    rows: list[Any],
    errors: list[str],
) -> None:
    edges = detect_stack_edges(data)
    by_pr: dict[int, Mapping[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        pr_number = _coerce_pr(row.get("pr_number"))
        if pr_number is not None:
            by_pr[pr_number] = row

    for child_pr, parent_pr in sorted(edges):
        child = by_pr.get(child_pr)
        parent = by_pr.get(parent_pr)
        if child is None:
            continue
        child_intent = _retire_intent(child)
        if child_intent is None:
            continue
        parent_merged = False
        if parent is not None:
            parent_merged = _recorded_merged(parent) and not _is_open_or_draft(parent)
        if parent_merged:
            continue
        field, value = child_intent
        errors.append(
            f"stacked_child_before_parent: #{child_pr} {field}={value!r} would "
            f"retire/merge the stacked child before parent #{parent_pr}"
        )

    for order_scope, order in _iter_order_lists(data, rows):
        index = {_coerce_pr(item): pos for pos, item in enumerate(order)}
        index = {pr: pos for pr, pos in index.items() if pr is not None}
        for child_pr, parent_pr in sorted(edges):
            if child_pr in index and parent_pr in index and index[child_pr] < index[parent_pr]:
                errors.append(
                    f"stacked_child_before_parent: {order_scope} lists #{child_pr} "
                    f"before parent #{parent_pr}"
                )


def _iter_order_lists(
    data: Mapping[str, Any],
    rows: list[Any],
) -> list[tuple[str, list[Any]]]:
    found: list[tuple[str, list[Any]]] = []
    for key in ("retirement_order", "merge_order", "recommended_order"):
        values = _as_list(data.get(key))
        if values:
            found.append((key, values))
    rec = data.get("recommendation")
    if isinstance(rec, Mapping):
        for key in ("retirement_order", "merge_order", "order"):
            values = _as_list(rec.get(key))
            if values:
                found.append((f"recommendation.{key}", values))
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        for key in ("retirement_order", "merge_order"):
            values = _as_list(row.get(key))
            if values:
                found.append((f"{_row_label(row)}.{key}", values))
    return found


def _retire_intent(row: Mapping[str, Any]) -> tuple[str, str] | None:
    for key in (
        "status_hint",
        "recommendation",
        "retirement_recommendation",
        "recommended_action",
        "merge_recommendation",
        "action",
    ):
        value = row.get(key)
        if isinstance(value, Mapping):
            for inner_key in ("action", "status", "hint", "status_hint"):
                token = _hint_token(value.get(inner_key))
                if token in RETIRE_OR_MERGE_HINTS:
                    return f"{key}.{inner_key}", token
            continue
        token = _hint_token(value)
        if token in RETIRE_OR_MERGE_HINTS:
            return key, token
    return None


def _check_open_as_merged(rows: list[Any], errors: list[str]) -> None:
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        if not _is_open_or_draft(row):
            continue
        if not _recorded_merged(row):
            continue
        label = _row_label(row)
        errors.append(
            f"open_as_merged: {label} is open/draft/BRANCH_ONLY but recorded as "
            f"merged (merged={row.get('merged')!r} merge_status={row.get('merge_status')!r} "
            f"merged_at={row.get('merged_at')!r})"
        )


def _is_open_or_draft(row: Mapping[str, Any]) -> bool:
    state = str(row.get("state") or "").strip().upper()
    if state in OPEN_LIKE_STATES:
        return True
    return row.get("draft") is True


def _recorded_merged(row: Mapping[str, Any]) -> bool:
    if row.get("merged") is True:
        return True
    if _hint_token(row.get("merge_status")) in {"merged", "merge"}:
        return True
    merged_at = row.get("merged_at")
    return merged_at not in (None, "", False)


def _check_billing_enospc_not_pass(
    data: Mapping[str, Any],
    rows: list[Any],
    errors: list[str],
) -> None:
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        if _ci_treated_as_pass(row):
            errors.append(
                f"billing_or_enospc_as_pass: {_row_label(row)} treats "
                "billing_not_started / ENOSPC / install-fail as a pass"
            )
    for blocker in _as_list(data.get("ci_blockers")):
        if not isinstance(blocker, Mapping):
            continue
        classification = _norm_token(blocker.get("classification"))
        if classification not in CI_NON_PASS_CLASSES and not _mentions_billing_or_enospc(blocker):
            continue
        if _mapping_says_pass(blocker):
            errors.append(
                f"billing_or_enospc_as_pass: ci_blocker {blocker.get('id')!r} "
                "treats billing_not_started / ENOSPC as a pass"
            )


def _ci_treated_as_pass(row: Mapping[str, Any]) -> bool:
    summary = row.get("check_summary")
    blobs: list[Mapping[str, Any]] = [row]
    if isinstance(summary, Mapping):
        blobs.append(summary)
    blocked = False
    for blob in blobs:
        classification = _norm_token(blob.get("classification"))
        if classification in CI_NON_PASS_CLASSES or _mentions_billing_or_enospc(blob):
            blocked = True
    if not blocked:
        return False
    for blob in blobs:
        if _mapping_says_pass(blob):
            return True
        classification = _norm_token(blob.get("classification"))
        if classification in PASS_TOKENS:
            return True
    return False


def _mapping_says_pass(mapping: Mapping[str, Any]) -> bool:
    for key in (
        "treated_as_pass",
        "ci_pass",
        "tests_pass",
        "tests_passed",
        "overall_pass",
        "passed",
    ):
        if _truthy(mapping.get(key)):
            return True
    for key in ("overall", "verdict", "result", "ci_result", "pass_status"):
        if _norm_token(mapping.get(key)) in PASS_TOKENS:
            return True
    return False


def _mentions_billing_or_enospc(mapping: Mapping[str, Any]) -> bool:
    parts = [
        str(mapping.get("classification") or ""),
        str(mapping.get("annotation") or ""),
        str(mapping.get("note") or ""),
        str(mapping.get("id") or ""),
    ]
    text = " ".join(parts).lower()
    return any(marker in text for marker in _BILLING_MARKERS + _ENOSPC_MARKERS)


def _check_status_hints(
    data: Mapping[str, Any],
    rows: list[Any],
    errors: list[str],
) -> None:
    allowed = set(ALLOWED_STATUS_HINTS)
    declared = {
        _hint_token(item)
        for item in _as_list(data.get("status_hint_allowed"))
        if _hint_token(item)
    }
    # Matrix-declared extras cannot smuggle retire/merge/close into the allowlist.
    allowed |= declared - RETIRE_OR_MERGE_HINTS
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        if "status_hint" not in row or row.get("status_hint") in (None, ""):
            continue
        token = _hint_token(row.get("status_hint"))
        if token not in allowed:
            errors.append(
                f"status_hint_not_allowed: {_row_label(row)} status_hint="
                f"{row.get('status_hint')!r} is outside the Lead set "
                f"(keep_open / needs_human_review) and careful WO statuses"
            )


def _iter_named_entries(
    data: Mapping[str, Any],
    key: str,
) -> list[tuple[str, Any]]:
    return [(f"{key}[{index}]", entry) for index, entry in enumerate(_as_list(data.get(key)))]


def _has_cited_evidence(entry: Any) -> bool:
    if not isinstance(entry, Mapping):
        return False
    evidence = entry.get("evidence")
    if evidence is None:
        evidence = entry.get("evidence_links")
    if evidence is None:
        evidence = entry.get("evidence_fields")
    if isinstance(evidence, list):
        return any(str(item).strip() for item in evidence)
    if isinstance(evidence, str):
        return bool(evidence.strip())
    return False


def _row_label(row: Mapping[str, Any]) -> str:
    row_id = row.get("id")
    if row_id:
        return str(row_id)
    pr_number = row.get("pr_number")
    if pr_number is not None:
        return f"pr-{pr_number}"
    branch = row.get("branch")
    if branch:
        return str(branch)
    return "row"


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _truthy(value: Any) -> bool:
    return value is True or value == 1 or (
        isinstance(value, str) and value.strip().lower() in {"true", "yes", "1"}
    )


def _norm_token(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip().lower()
    text = text.replace("#", "")
    text = text.replace(" ", "")
    text = text.replace("_", "-")
    return text


def _hint_token(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip().lower().replace("-", "_").replace(" ", "_")


def _coerce_pr(value: Any) -> int | None:
    if value is None or value is False:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    text = str(value).strip()
    if not text:
        return None
    lowered = text.lower().replace("https://github.com/christianv997/neurotopology-sim/pull/", "")
    lowered = lowered.replace("nts-pr-", "").replace("pr-", "").replace("pr ", "")
    lowered = lowered.replace("#", "").strip()
    # "#216 inventory docs only" → leading int
    digits = []
    for char in lowered:
        if char.isdigit():
            digits.append(char)
        elif digits:
            break
    if digits:
        return int("".join(digits))
    return None
