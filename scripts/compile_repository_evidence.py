#!/usr/bin/env python3
"""Compile a Lead/Research contribution inventory into a release evidence report.

Offline by default. Inventory is not evidence. Synthetic data cannot establish
a scientific PASS. This compiler never invents merge status for PRs #210/#211/#212
and never promotes unverified author_test_results to scientific PASS.

Writes files only when --output / --output-dir / --write is passed.
Otherwise prints to stdout and does not touch the filesystem.
"""

from __future__ import annotations

import argparse
import json
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping, Sequence

COMPILER_ID = "compile_repository_evidence"
DEFAULT_FORMAT = "json"
JSON_FILENAME = "compiled_repository_evidence.json"
MARKDOWN_FILENAME = "compiled_repository_evidence.md"
MERGER_INSTRUCTION = "do_not_merge"

# Live GitHub mutation is never implemented. This flag name exists only so a
# caller who asks for it gets a documented refusal instead of a silent no-op.
_FORBIDDEN_LIVE_FLAGS = ("--live", "--github-write", "--mutate-github")

# Canonical required-warning statements. Inventory text is preserved first;
# these are appended only when their token coverage is missing.
CANONICAL_REQUIRED_WARNINGS: tuple[str, ...] = (
    "PRs #210, #211, #212 are NOT merged unless independently verified as merged.",
    "scientific-falsification branch has no confirmed PR unless one is found.",
    "Missing Antigravity/Grok implementation reports are unverified.",
    "Synthetic data cannot establish a scientific PASS.",
    "Current proxy Bayesian method requires correction / formal likelihood validation before strong empirical interpretation.",
)

_WATCHED_PR_TOKENS = ("210", "211", "212")
_NOT_MERGED_TOKENS = ("not merged", "not-merged", "remain unmerged")
_FALSIFICATION_TOKENS = ("falsification", "scientific-falsification")
_NO_PR_TOKENS = ("no confirmed pr", "no pr", "has no pr", "without a pr")
_ANTIGRAVITY_TOKENS = ("antigravity",)
_GROK_TOKENS = ("grok",)
_UNVERIFIED_TOKENS = ("unverified",)
_SYNTHETIC_TOKENS = ("synthetic",)
_PASS_TOKENS = ("pass",)
_PROXY_TOKENS = ("proxy", "bayes", "bayesian")
_LIKELIHOOD_TOKENS = ("formal likelihood", "likelihood validation", "formal marginal")

# Stdlib urllib/http.client may be imported transitively by yaml/json.
# Refuse only non-stdlib network / MarketOS clients if they appear.
_NETWORK_MODULE_PREFIXES = (
    "requests",
    "httpx",
    "aiohttp",
    "github",
    "ghapi",
    "marketos",
)

_NON_EMPIRICAL = frozenset({"synthetic", "proxy", "unsupported"})
_SYNTHETIC = frozenset({"synthetic"})
_PASS_EXACT = frozenset({"pass", "scientific_pass"})


class CompilerError(Exception):
    """Fail-closed compiler error. Exit non-zero; do not emit a report."""

    def __init__(self, errors: Sequence[str], *, exit_code: int = 1) -> None:
        self.errors = list(errors)
        self.exit_code = exit_code
        super().__init__(list(self.errors))


def _ensure_repo_on_path(repo_root: Path) -> None:
    root = str(repo_root.resolve())
    if root not in sys.path:
        sys.path.insert(0, root)


def _import_validators(repo_root: Path):
    _ensure_repo_on_path(repo_root)
    # Imported after sys.path mutation so the QA-owned validator is consumed,
    # not copied. No network clients.
    from tests.release.evidence_validate import (  # noqa: WPS433
        WATCHED_PRS,
        load_inventory,
        load_schema,
        validate_compiled_report,
        validate_inventory,
    )

    return {
        "WATCHED_PRS": WATCHED_PRS,
        "load_inventory": load_inventory,
        "load_schema": load_schema,
        "validate_compiled_report": validate_compiled_report,
        "validate_inventory": validate_inventory,
    }


def _as_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return list(value)
    return [value]


def _lower(value: Any) -> str:
    return _as_str(value).strip().lower()


def _classification(row: Mapping[str, Any]) -> Mapping[str, Any]:
    raw = row.get("research_classification")
    return raw if isinstance(raw, Mapping) else {}


def _claim_class(row: Mapping[str, Any]) -> str:
    classified = _classification(row)
    if "claim_class" in classified:
        return _lower(classified.get("claim_class"))
    return _lower(row.get("claim_class"))


def _data_mode(row: Mapping[str, Any]) -> str:
    classified = _classification(row)
    if "data_mode" in classified:
        return _lower(classified.get("data_mode"))
    return _lower(row.get("data_mode"))


def _value_class(row: Mapping[str, Any]) -> str:
    classified = _classification(row)
    if "value_class" in classified:
        return _lower(classified.get("value_class"))
    return _lower(row.get("value_class"))


def _empirical_pass_allowed(row: Mapping[str, Any]) -> Any:
    classified = _classification(row)
    if "empirical_pass_allowed" in classified:
        return classified.get("empirical_pass_allowed")
    return row.get("empirical_pass_allowed")


def _is_synthetic_row(row: Mapping[str, Any]) -> bool:
    return _claim_class(row) in _SYNTHETIC or _data_mode(row) in _SYNTHETIC


def _is_weak_claim(row: Mapping[str, Any]) -> bool:
    return _claim_class(row) in _NON_EMPIRICAL or _is_synthetic_row(row)


def _is_pass_value(value: Any) -> bool:
    if value is True:
        return True
    return isinstance(value, str) and value.strip().lower() in _PASS_EXACT


def _scientific_pass(row: Mapping[str, Any]) -> Any:
    status = row.get("verification_status")
    if isinstance(status, Mapping) and "scientific_pass" in status:
        return status.get("scientific_pass")
    return row.get("scientific_pass")


def _author_test_results(row: Mapping[str, Any]) -> Any:
    status = row.get("verification_status")
    if isinstance(status, Mapping) and "author_test_results" in status:
        return status.get("author_test_results")
    if "author_test_results" in row:
        return row.get("author_test_results")
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


def _is_leftover_or_blocked(row: Mapping[str, Any]) -> bool:
    section = _as_str(row.get("section")).upper()
    ident = _as_str(row.get("id")).lower()
    return section == "BLOCKED" or "leftover" in ident or row.get("leftover") is True


def _blob(parts: Sequence[Any]) -> str:
    return "\n".join(_as_str(item) for item in parts).lower()


def _has_tokens(text: str, tokens: Sequence[str]) -> bool:
    return any(token in text for token in tokens)


def _warning_coverage(warnings: Sequence[str]) -> dict[str, bool]:
    text = _blob(warnings)
    return {
        "watched_prs_not_merged": all(pr in text for pr in _WATCHED_PR_TOKENS)
        and _has_tokens(text, _NOT_MERGED_TOKENS),
        "falsification_no_pr": _has_tokens(text, _FALSIFICATION_TOKENS)
        and _has_tokens(text, _NO_PR_TOKENS),
        "antigravity_grok_unverified": _has_tokens(text, _ANTIGRAVITY_TOKENS)
        and _has_tokens(text, _GROK_TOKENS)
        and _has_tokens(text, _UNVERIFIED_TOKENS),
        "synthetic_not_pass": _has_tokens(text, _SYNTHETIC_TOKENS)
        and _has_tokens(text, _PASS_TOKENS),
        "proxy_formal_likelihood": _has_tokens(text, _PROXY_TOKENS)
        and _has_tokens(text, _LIKELIHOOD_TOKENS),
    }


def merge_required_warnings(inventory: Mapping[str, Any]) -> list[str]:
    """Preserve inventory + research warnings; inject canonical gaps only."""
    merged: list[str] = []
    seen: set[str] = set()
    for source in (inventory.get("required_warnings"), None):
        for item in _as_list(source):
            text = _as_str(item).strip()
            if text and text not in seen:
                seen.add(text)
                merged.append(text)
    research = inventory.get("research_phase")
    if isinstance(research, Mapping):
        for item in _as_list(research.get("required_warnings")):
            text = _as_str(item).strip()
            if text and text not in seen:
                seen.add(text)
                merged.append(text)

    coverage = _warning_coverage(merged)
    canonical_by_key = {
        "watched_prs_not_merged": CANONICAL_REQUIRED_WARNINGS[0],
        "falsification_no_pr": CANONICAL_REQUIRED_WARNINGS[1],
        "antigravity_grok_unverified": CANONICAL_REQUIRED_WARNINGS[2],
        "synthetic_not_pass": CANONICAL_REQUIRED_WARNINGS[3],
        "proxy_formal_likelihood": CANONICAL_REQUIRED_WARNINGS[4],
    }
    for key, statement in canonical_by_key.items():
        if not coverage.get(key):
            merged.append(statement)
    return merged


def _derive_tests(row: Mapping[str, Any]) -> list[Any]:
    if "tests" in row and row.get("tests") is not None:
        return _as_list(row.get("tests"))
    names: list[Any] = []
    for item in _as_list(row.get("changed_file_summary") or row.get("changed_files")):
        text = _as_str(item)
        lowered = text.lower()
        if "test" in lowered:
            names.append(item)
    return names


def _derive_changed_files(row: Mapping[str, Any]) -> list[Any]:
    if "changed_files" in row:
        return _as_list(row.get("changed_files"))
    return _as_list(row.get("changed_file_summary"))


def _derive_artifacts(row: Mapping[str, Any]) -> list[Any]:
    if "artifacts" in row and row.get("artifacts") is not None:
        return _as_list(row.get("artifacts"))
    return []


def _derive_test_results(row: Mapping[str, Any]) -> Any:
    """Never promote unverified author counts to PASS / claimed."""
    if "test_results" in row and row.get("test_results") is not None:
        value = row.get("test_results")
        if _is_pass_value(value) and _lower(_author_test_results(row)) == "unverified":
            return "unverified"
        if _is_pass_value(value) and _is_synthetic_row(row):
            return "unverified"
        return value
    author = _author_test_results(row)
    if _is_pass_value(author):
        return "unverified"
    if author is None:
        return "unverified"
    return author


def _derive_scientific_assertions(row: Mapping[str, Any]) -> list[Any]:
    if "scientific_assertions" in row and row.get("scientific_assertions") is not None:
        cleaned: list[Any] = []
        for item in _as_list(row.get("scientific_assertions")):
            if _is_pass_value(item):
                continue
            if isinstance(item, Mapping) and _is_pass_value(
                item.get("verdict", item.get("status"))
            ):
                continue
            cleaned.append(item)
        if cleaned:
            return cleaned
    classified = _classification(row)
    assertions = [
        "This inventory row does not establish a scientific verdict.",
        (
            f"claim_class={classified.get('claim_class', row.get('claim_class'))}; "
            f"data_mode={classified.get('data_mode', row.get('data_mode'))}; "
            f"empirical_pass_allowed={_empirical_pass_allowed(row)}."
        ),
    ]
    scientific = _scientific_pass(row)
    if scientific is not None and not _is_pass_value(scientific):
        assertions.append(f"verification scientific_pass remains {scientific}.")
    note = classified.get("bayesian_note")
    if classified.get("bayesian_warning") is True:
        if note:
            assertions.append(_as_str(note))
        else:
            assertions.append(
                "Proxy Bayes needs formal likelihood validation before strong empirical interpretation."
            )
    return assertions


def _derive_open_questions(row: Mapping[str, Any]) -> list[Any]:
    if "open_questions" in row and row.get("open_questions") is not None:
        return _as_list(row.get("open_questions"))
    questions: list[Any] = []
    classified = _classification(row)
    for item in _as_list(classified.get("methodological_limitations")):
        questions.append(item)
    if _is_synthetic_row(row):
        questions.append("Synthetic fixtures still cannot establish a scientific PASS.")
    if classified.get("bayesian_warning") is True:
        questions.append(
            "Proxy Bayes still requires formal likelihood validation."
        )
    if _lower(row.get("merge_status")) in {"open", "draft", "branch_only"}:
        questions.append("Unmerged work is not a landed scientific result.")
    if _lower((row.get("verification_status") or {}).get("implementation_report")) in {
        "missing",
        "not_located",
        "unverified",
    }:
        questions.append("Implementation report is missing or unverified.")
    if not questions:
        questions.append("Independent scientific validation is still required.")
    return questions


def _derive_next_action(row: Mapping[str, Any], *, pack_next: str) -> str:
    if "next_action" in row and row.get("next_action"):
        return _as_str(row.get("next_action"))
    prn = _pr_number(row)
    if prn in {210, 211, 212}:
        return "Hold: do not invent merge for this watched PR; Integration reviews only."
    if _lower(row.get("merge_status")) == "branch_only":
        return "Tracked gap: branch_only scientific-falsification has no PR unless one is found."
    return pack_next


def _derive_pr(row: Mapping[str, Any]) -> Any:
    if "pr" in row:
        return row.get("pr")
    number = _pr_number(row)
    url = row.get("pr_url")
    if number is not None and url:
        return {"number": number, "url": url}
    if number is not None:
        return number
    if url is not None:
        return url
    return None


def _sanitize_verification_status(row: Mapping[str, Any]) -> dict[str, Any]:
    raw = row.get("verification_status")
    status = dict(raw) if isinstance(raw, Mapping) else {}
    for key in (
        "existence",
        "merge_status",
        "scientific_pass",
        "author_test_results",
        "implementation_report",
    ):
        status.setdefault(key, "unverified" if key != "scientific_pass" else "not_claimed")
    # Never upgrade unverified author tests or synthetic/proxy rows to PASS.
    if _lower(status.get("author_test_results")) == "unverified" and _is_pass_value(
        status.get("scientific_pass")
    ):
        status["scientific_pass"] = "not_claimed"
    if _is_synthetic_row(row) and (
        _is_pass_value(status.get("scientific_pass")) or status.get("scientific_pass") == "claimed"
    ):
        status["scientific_pass"] = "not_claimed"
    if _is_weak_claim(row) and _is_pass_value(status.get("scientific_pass")):
        status["scientific_pass"] = "not_claimed"
    if _is_pass_value(status.get("author_test_results")):
        status["author_test_results"] = "unverified"
    return status


def map_contribution(row: Mapping[str, Any], *, pack_next: str) -> dict[str, Any]:
    """Map one inventory row onto compiled contribution fields + aliases."""
    compiled = deepcopy(dict(row))
    compiled["pr"] = _derive_pr(row)
    if "pr_number" not in compiled:
        compiled["pr_number"] = _pr_number(row)
    compiled["changed_files"] = _derive_changed_files(row)
    compiled["tests"] = _derive_tests(row)
    compiled["test_results"] = _derive_test_results(row)
    compiled["artifacts"] = _derive_artifacts(row)
    compiled["scientific_assertions"] = _derive_scientific_assertions(row)
    compiled["open_questions"] = _derive_open_questions(row)
    compiled["next_action"] = _derive_next_action(row, pack_next=pack_next)
    compiled["verification_status"] = _sanitize_verification_status(row)
    compiled["compiled_from_author_test_results"] = False
    compiled["tests_used_as_compiled_evidence"] = False
    # Required compiled keys must exist even when inventory left them null.
    for key in (
        "id",
        "repository",
        "baseline_commit",
        "branch",
        "agent",
        "work_order",
        "final_commit",
        "limitations",
        "merge_status",
        "evidence_source",
    ):
        compiled.setdefault(key, row.get(key))
    if compiled.get("limitations") is None:
        compiled["limitations"] = []
    return compiled


def annotate_reused_lanes(rows: list[dict[str, Any]]) -> None:
    """Inventories may repeat reused lanes; compiled reports may not.

    Keep the highest PR (else first) as the active compiled row. Mark the
    rest leftover=true so QA uniqueness applies without inventing merge status.
    """
    by_branch: dict[str, list[int]] = {}
    for index, row in enumerate(rows):
        if _is_leftover_or_blocked(row):
            continue
        branch = row.get("branch")
        if isinstance(branch, str) and branch.strip():
            by_branch.setdefault(branch, []).append(index)
    for branch, indexes in by_branch.items():
        if len(indexes) < 2:
            continue

        def _rank(i: int) -> tuple[int, int, int]:
            prn = _pr_number(rows[i])
            return (1 if prn is not None else 0, prn or 0, i)

        ranked = sorted(indexes, key=_rank, reverse=True)
        keeper = ranked[0]
        keeper_id = rows[keeper].get("id")
        for index in ranked[1:]:
            rows[index]["leftover"] = True
            rows[index]["compiler_reused_lane"] = True
            rows[index]["compiler_active_peer_id"] = keeper_id
            note = (
                "Compiler marked leftover=true because this inventory reused "
                f"branch {branch!r}; compiled reports forbid duplicate active "
                f"branches. Canonical compiled row for this lane is {keeper_id}."
            )
            limitations = _as_list(rows[index].get("limitations"))
            if note not in limitations:
                limitations.append(note)
            rows[index]["limitations"] = limitations


def _row_has_proxy_or_scientific_blocker(row: Mapping[str, Any]) -> bool:
    classified = _classification(row)
    if classified.get("bayesian_warning") is True:
        return True
    if _claim_class(row) in {"proxy", "synthetic", "unsupported"}:
        return True
    if _data_mode(row) in {"synthetic", "proxy"}:
        return True
    if _value_class(row) == "scientific" and _lower(_scientific_pass(row)) != "pass":
        # Scientific surface without a validated PASS (and we never set PASS).
        return True
    if _claim_class(row) == "empirical" and _empirical_pass_allowed(row) is not True:
        return True
    if _claim_class(row) == "empirical" and _lower(_scientific_pass(row)) not in {
        "pass",
    }:
        return True
    return False


def _has_falsification_branch_gap(rows: Sequence[Mapping[str, Any]]) -> bool:
    for row in rows:
        ident = _lower(row.get("id"))
        branch = _lower(row.get("branch"))
        title = _lower(row.get("title"))
        falsification = (
            "falsification" in ident or "falsification" in branch or "falsification" in title
        )
        if not falsification:
            continue
        if _lower(row.get("merge_status")) == "branch_only" and _pr_number(row) is None:
            return True
        if row.get("pr_number") is None and row.get("pr_url") is None and _lower(
            row.get("merge_status")
        ) in {"branch_only", "unverified"}:
            return True
    return False


def _ci_is_known_blocked(rows: Sequence[Mapping[str, Any]]) -> bool:
    """CI is 'known blocked' only from explicit hold_ci-style notes.

    Inventory github_checks FAILURE values are author-recorded snapshot notes,
    not independently re-run CI. Do not treat them as a compiled CI verdict
    unless a hold_ci / ci_blocked flag is present.
    """
    for row in rows:
        if row.get("hold_ci") is True or row.get("ci_blocked") is True:
            return True
        notes = _blob(
            [
                row.get("ci_note"),
                row.get("hold_ci_note"),
                *(_as_list(row.get("limitations"))),
            ]
        )
        if "hold_ci" in notes or "ci_blocked" in notes:
            return True
    return False


def _watched_prs_still_open(rows: Sequence[Mapping[str, Any]], watched: Sequence[int]) -> bool:
    for prn in watched:
        row = next((item for item in rows if _pr_number(item) == prn), None)
        if row is None:
            return True
        if _lower(row.get("merge_status")) != "merged":
            return True
        if row.get("is_draft") is True:
            return True
    return False


def choose_release_recommendation(
    inventory: Mapping[str, Any],
    rows: Sequence[Mapping[str, Any]],
    *,
    watched: Sequence[int],
) -> tuple[str, str, list[str]]:
    """Fail-closed recommendation. Prefer scientific block on the live matrix."""
    blockers: list[str] = []
    scientific_rows = [row for row in rows if _row_has_proxy_or_scientific_blocker(row)]
    if scientific_rows:
        blockers.append(
            "Scientific/proxy/synthetic/unsupported rows remain; "
            "empirical_pass_from_this_pack is false."
        )
    if inventory.get("empirical_pass_from_this_pack") is True:
        blockers.append("Pack claimed empirical_pass_from_this_pack; compiler refuses that.")
    research = inventory.get("research_phase")
    if isinstance(research, Mapping) and research.get("empirical_pass_from_this_pack") is False:
        blockers.append(
            "Research locked empirical_pass_from_this_pack=false "
            "(proxy Bayes + synthetic cannot establish PASS)."
        )
    if any(_classification(row).get("bayesian_warning") is True for row in rows):
        blockers.append("Proxy Bayes requires formal likelihood validation.")
    if any(_is_synthetic_row(row) for row in rows):
        blockers.append("Synthetic rows cannot establish a scientific PASS.")

    missing_branch = _has_falsification_branch_gap(rows)
    if missing_branch:
        blockers.append(
            "scientific-falsification is branch_only with no confirmed PR unless one is found."
        )

    watched_open = _watched_prs_still_open(rows, watched)
    if watched_open:
        blockers.append("PRs #210, #211, #212 are not independently verified as merged.")

    # Rule 1: scientific / proxy / missing empirical validation.
    if scientific_rows or any(
        item.startswith("Proxy") or "synthetic" in item.lower() or "empirical_pass" in item
        for item in blockers
    ):
        rationale = (
            "BLOCKED_BY_SCIENTIFIC_VALIDATION because Research locked proxy Bayes, "
            "synthetic data cannot establish scientific PASS, and "
            "empirical_pass_from_this_pack is false. Inventory is not evidence. "
            "This compiler does not promote unverified author_test_results."
        )
        return "BLOCKED_BY_SCIENTIFIC_VALIDATION", rationale, blockers

    # Rule 2: missing branches / falsification without PR.
    if missing_branch:
        rationale = (
            "BLOCKED_BY_MISSING_BRANCHES: branch_only scientific-falsification "
            "has no confirmed PR. Dominant blocker after scientific checks cleared."
        )
        return "BLOCKED_BY_MISSING_BRANCHES", rationale, blockers

    # Rule 3: explicit hold_ci notes only. Snapshot FAILURE strings are not enough.
    if _ci_is_known_blocked(rows):
        rationale = (
            "BLOCKED_BY_CI because hold_ci-style notes mark CI as known blocked. "
            "Author-recorded github_checks FAILURE values alone are unverified."
        )
        return "BLOCKED_BY_CI", rationale, blockers

    # Never READY_FOR_MERGE_REVIEW while watched PRs are open/draft or the
    # pack is inventory-not-evidence with remaining scientific blockers.
    if watched_open or inventory.get("inventory_is_not_evidence") is True:
        rationale = (
            "READY_FOR_REVIEW for this inventory pack only. "
            "Not READY_FOR_MERGE_REVIEW: watched PRs #210/#211/#212 remain "
            "open/draft or inventory_is_not_evidence is true. Merger: do not merge."
        )
        return "READY_FOR_REVIEW", rationale, blockers

    rationale = (
        "READY_FOR_REVIEW for this inventory pack. Merger: do not merge. "
        "READY_FOR_MERGE_REVIEW is reserved for independently verified merges."
    )
    return "READY_FOR_REVIEW", rationale, blockers


def compile_report(
    *,
    repo_root: Path,
    matrix_path: Path | None = None,
    schema_path: Path | None = None,
    generated_at: str | None = None,
    offline: bool = True,
    allow_unverified_github_metadata_read: bool = False,
) -> dict[str, Any]:
    """Build a compiled_report dict. Fail-closed on inventory or report errors."""
    if not offline:
        raise CompilerError(
            ["compiler:live_github_mutation_refused"],
            exit_code=2,
        )

    validators = _import_validators(repo_root)
    schema = validators["load_schema"](schema_path)
    inventory = validators["load_inventory"](matrix_path)

    inventory_errors = validators["validate_inventory"](inventory, schema=schema)
    if inventory_errors:
        raise CompilerError([f"inventory:{item}" for item in inventory_errors])

    pack_next = "Integration: assembly recommendation only; do not merge."
    rows = [map_contribution(row, pack_next=pack_next) for row in inventory.get("contributions") or []]
    annotate_reused_lanes(rows)

    recommendation, rationale, blockers = choose_release_recommendation(
        inventory,
        rows,
        watched=validators["WATCHED_PRS"],
    )

    inspected_at = inventory.get("inspected_at")
    resolved_generated_at = generated_at if generated_at is not None else inspected_at

    github_metadata_note = (
        "GitHub metadata read was requested but is not implemented; "
        "compiler stayed offline. Treat any GitHub field as unverified "
        "unless the inventory already recorded evidence_source=github_api."
        if allow_unverified_github_metadata_read
        else "Offline compile; no GitHub client was imported or called."
    )

    report: dict[str, Any] = {
        "schema_version": schema.get("schema_version"),
        "kind": "compiled_report",
        "repository": inventory.get("repository"),
        "baseline_commit": inventory.get("baseline_commit"),
        "inventory_is_not_evidence": True,
        "empirical_pass_from_this_pack": False,
        "required_warnings": merge_required_warnings(inventory),
        "release_recommendation": recommendation,
        "release_recommendation_rationale": rationale,
        "scientific_blockers": blockers,
        "evidence_source": "compiled_from_inventory",
        "inventory_evidence_source": inventory.get("evidence_source"),
        "contributions": rows,
        "merger_instruction": inventory.get("merger_instruction") or MERGER_INSTRUCTION,
        "compiler": {
            "id": COMPILER_ID,
            "offline": True,
            "github_metadata_read": False,
            "github_metadata_note": github_metadata_note,
            "generated_at": resolved_generated_at,
            "matrix_path": str(
                (matrix_path or (repo_root / "docs" / "release" / "agent_contribution_matrix.yaml"))
            ),
            "schema_path": str(
                (schema_path or (repo_root / "configs" / "release" / "evidence_schema.yaml"))
            ),
        },
        "inventory_id": inventory.get("inventory_id"),
        "next_action": pack_next,
    }

    report_errors = validators["validate_compiled_report"](report, schema=schema)
    if report_errors:
        raise CompilerError([f"compiled_report:{item}" for item in report_errors])
    return report


def dumps_json(report: Mapping[str, Any]) -> str:
    return json.dumps(report, sort_keys=True, indent=2, ensure_ascii=False) + "\n"


def render_markdown(report: Mapping[str, Any]) -> str:
    warnings = _as_list(report.get("required_warnings"))
    contributions = report.get("contributions") or []
    lines = [
        "# Compiled repository evidence report",
        "",
        "This file is a generated compiler summary. It is not scientific evidence.",
        "",
        "## Required statements",
        "",
        "- Inventory is not evidence.",
        "- Synthetic data cannot establish a scientific PASS.",
        "- PRs #210, #211, and #212 are NOT merged unless independently verified as merged.",
        "- Proxy Bayes needs formal likelihood validation before strong empirical interpretation.",
        "- The scientific-falsification branch has no PR unless one is found.",
        "- Antigravity/Grok reports are unverified.",
        "",
        f"**inventory_is_not_evidence:** `{report.get('inventory_is_not_evidence')}`",
        f"**empirical_pass_from_this_pack:** `{report.get('empirical_pass_from_this_pack')}`",
        f"**release_recommendation:** `{report.get('release_recommendation')}`",
        f"**merger_instruction:** `{report.get('merger_instruction')}`",
        "",
        "## Recommendation rationale",
        "",
        _as_str(report.get("release_recommendation_rationale")),
        "",
        "## Scientific blockers",
        "",
    ]
    blockers = _as_list(report.get("scientific_blockers"))
    if blockers:
        lines.extend(f"- {item}" for item in blockers)
    else:
        lines.append("- None recorded by the compiler.")
    lines.extend(
        [
            "",
            "## Envelope",
            "",
            f"- kind: `{report.get('kind')}`",
            f"- schema_version: `{report.get('schema_version')}`",
            f"- repository: {report.get('repository')}",
            f"- baseline_commit: `{report.get('baseline_commit')}`",
            f"- evidence_source: `{report.get('evidence_source')}` "
            f"(inventory source: `{report.get('inventory_evidence_source')}`)",
            f"- contribution_count: {len(contributions)}",
            "",
            "## Required warnings",
            "",
        ]
    )
    lines.extend(f"- {item}" for item in warnings)
    lines.extend(["", "## Contributions", ""])
    lines.append(
        "| id | pr | merge_status | claim_class | scientific_pass | test_results |"
    )
    lines.append("| --- | --- | --- | --- | --- | --- |")
    for row in contributions:
        if not isinstance(row, Mapping):
            continue
        classified = _classification(row)
        prn = _pr_number(row)
        status = row.get("verification_status") if isinstance(row.get("verification_status"), Mapping) else {}
        lines.append(
            "| {id} | {pr} | {merge} | {claim} | {sci} | {tests} |".format(
                id=_as_str(row.get("id")),
                pr=_as_str(prn) if prn is not None else "",
                merge=_as_str(row.get("merge_status")),
                claim=_as_str(classified.get("claim_class")),
                sci=_as_str(status.get("scientific_pass")),
                tests=_as_str(row.get("test_results")),
            )
        )
    lines.extend(
        [
            "",
            "## Limitations",
            "",
            "- Inventory is not evidence and was not re-validated against live GitHub in this offline compile.",
            "- Synthetic data cannot establish a scientific PASS.",
            "- PRs #210, #211, and #212 are not merged; this compiler does not invent a merge.",
            "- Proxy Bayes needs formal likelihood validation.",
            "- Falsification branch has no PR unless found.",
            "- Antigravity/Grok reports are unverified.",
            "- Unverified author_test_results are not compiled evidence and are not PASS.",
            "",
            f"**Next action:** {report.get('next_action')}",
            "",
            "Merger: **do not merge.**",
            "",
        ]
    )
    return "\n".join(lines)


def _resolve_repo_root(value: str) -> Path:
    return Path(value).resolve()


def _refuse_if_network_imported() -> None:
    imported = []
    for name in sys.modules:
        lowered = name.lower()
        for prefix in _NETWORK_MODULE_PREFIXES:
            if lowered == prefix or lowered.startswith(prefix + "."):
                imported.append(name)
                break
    if imported:
        raise CompilerError(
            [f"compiler:network_module_imported:{name}" for name in sorted(imported)],
            exit_code=2,
        )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    raw = list(sys.argv[1:] if argv is None else argv)
    for flag in _FORBIDDEN_LIVE_FLAGS:
        if flag in raw:
            raise CompilerError(
                [f"compiler:refused_live_github_flag:{flag}"],
                exit_code=2,
            )

    parser = argparse.ArgumentParser(
        description=(
            "Compile docs/release/agent_contribution_matrix.yaml into a "
            "compiled_report. Offline default. Inventory is not evidence."
        )
    )
    parser.add_argument("--repo-root", default=".", help="Repository root (default: .)")
    parser.add_argument(
        "--matrix",
        default=None,
        help="Inventory YAML (default: docs/release/agent_contribution_matrix.yaml)",
    )
    parser.add_argument(
        "--schema",
        default=None,
        help="Schema YAML (default: configs/release/evidence_schema.yaml)",
    )
    parser.add_argument(
        "--format",
        choices=("json", "markdown", "both"),
        default=DEFAULT_FORMAT,
        help="Emit JSON, Markdown, or both (default: json)",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="If set, write report files here. Omit to print to stdout only.",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Optional single output file (json or markdown). Not used with --format both.",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write files. Requires --output-dir or --output.",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        default=True,
        help="Refuse live GitHub mutation (default).",
    )
    parser.add_argument(
        "--allow-unverified-github-metadata-read",
        action="store_true",
        default=False,
        help=(
            "Document-only switch. No GitHub client is imported. Any metadata "
            "remains unverified unless the inventory already used github_api."
        ),
    )
    parser.add_argument(
        "--generated-at",
        default=None,
        help="Frozen timestamp for deterministic output. Default: inventory inspected_at.",
    )
    return parser.parse_args(raw)


def emit_report(
    report: Mapping[str, Any],
    *,
    fmt: str,
    output_dir: Path | None,
    output: Path | None,
    write: bool,
) -> list[Path]:
    written: list[Path] = []
    payloads: list[tuple[str, str]] = []
    if fmt in {"json", "both"}:
        payloads.append(("json", dumps_json(report)))
    if fmt in {"markdown", "both"}:
        payloads.append(("markdown", render_markdown(report)))

    should_write = write or output_dir is not None or output is not None
    if should_write and output_dir is None and output is None:
        raise CompilerError(["compiler:--write requires --output-dir or --output"], exit_code=2)
    if output is not None and fmt == "both":
        raise CompilerError(
            ["compiler:--output cannot be used with --format both; use --output-dir"],
            exit_code=2,
        )

    if not should_write:
        chunks = [text for _, text in payloads]
        # Report output is UTF-8. Windows may expose a legacy cp1252 stdout;
        # a Unicode symbol in valid JSON/Markdown must not cause a CLI error.
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
        sys.stdout.write("\n".join(chunk.rstrip("\n") for chunk in chunks) + "\n")
        return written

    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(payloads[0][1], encoding="utf-8")
        written.append(output)
        return written

    assert output_dir is not None
    output_dir.mkdir(parents=True, exist_ok=True)
    names = {"json": JSON_FILENAME, "markdown": MARKDOWN_FILENAME}
    for kind, text in payloads:
        path = output_dir / names[kind]
        path.write_text(text, encoding="utf-8")
        written.append(path)
    return written


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = parse_args(argv)
        repo_root = _resolve_repo_root(args.repo_root)
        matrix = Path(args.matrix) if args.matrix else None
        schema = Path(args.schema) if args.schema else None
        if matrix is not None and not matrix.is_absolute():
            matrix = repo_root / matrix
        if schema is not None and not schema.is_absolute():
            schema = repo_root / schema
        report = compile_report(
            repo_root=repo_root,
            matrix_path=matrix,
            schema_path=schema,
            generated_at=args.generated_at,
            offline=True if args.offline else False,
            allow_unverified_github_metadata_read=args.allow_unverified_github_metadata_read,
        )
        _refuse_if_network_imported()
        output_dir = Path(args.output_dir) if args.output_dir else None
        output = Path(args.output) if args.output else None
        emit_report(
            report,
            fmt=args.format,
            output_dir=output_dir,
            output=output,
            write=args.write,
        )
        return 0
    except CompilerError as exc:
        sys.stderr.write("compile_repository_evidence failed:\n")
        for item in exc.errors:
            sys.stderr.write(f"  {item}\n")
        return exc.exit_code


if __name__ == "__main__":
    sys.exit(main())
