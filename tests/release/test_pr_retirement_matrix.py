"""Fail-closed tests for the PR retirement register matrix.

Consumes the live matrix at HEAD read-only. Malformed fixtures live under
``tests/release/fixtures/pr_retirement/``. No network. No secrets.
Warnings never count as success (warnings-only results are not OK).

Release may wrap ``pr_retirement_validate.py`` later; these tests own the rules.
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

import pytest

_RELEASE_DIR = Path(__file__).resolve().parent
if str(_RELEASE_DIR) not in sys.path:
    sys.path.insert(0, str(_RELEASE_DIR))

from pr_retirement_validate import (  # noqa: E402
    ALLOWED_PROXY_IDENTIFIERS,
    ALLOWED_STATUS_HINTS,
    CANONICAL_STACK_CHAINS,
    DEFAULT_MATRIX_PATH,
    FIXTURE_DIR,
    ValidationResult,
    child_before_parent_violations,
    detect_stack_edges,
    load_matrix,
    validate_matrix,
    validate_path,
    validate_pr_retirement_matrix,
)

_NEW_MODULES = (
    _RELEASE_DIR / "pr_retirement_validate.py",
    Path(__file__).resolve(),
)

_AST_DENIED_MODULES = frozenset(
    {
        "urllib.request",
        "urllib.client",
        "requests",
        "http.client",
        "httpx",
        "aiohttp",
        "socket",
        "ftplib",
        "smtplib",
        "subprocess",
        "github",
        "ghapi",
    }
)

_AST_DENIED_ATTRS = frozenset(
    {
        "urlopen",
        "urlretrieve",
        "create_connection",
    }
)

_SECRET_VALUE_RE = re.compile(
    r"(sk-ant-[A-Za-z0-9_-]{8,}|sk-proj-[A-Za-z0-9_-]{8,}|ghp_[A-Za-z0-9]{8,}"
    r"|xoxb-[A-Za-z0-9-]{8,}|AKIA[0-9A-Z]{8,})"
)

_MALFORMED = (
    ("invented_pass.yaml", "invented_pass"),
    ("proxy_wrong_id.yaml", "proxy_flag_not_allowed"),
    ("invented_duplicate.yaml", "duplicate_without_evidence"),
    ("whole_pr_supersede.yaml", "whole_pr_superseded"),
    ("stacked_child_before_parent.yaml", "stacked_child_before_parent"),
    ("open_as_merged.yaml", "open_as_merged"),
    ("billing_as_pass.yaml", "billing_or_enospc_as_pass"),
)


def _live() -> dict:
    return load_matrix(DEFAULT_MATRIX_PATH)


def test_live_matrix_path_exists_at_head():
    assert DEFAULT_MATRIX_PATH.is_file()
    assert DEFAULT_MATRIX_PATH.resolve().as_posix().endswith(
        "configs/release/pr_retirement_matrix.yaml"
    )


def test_live_matrix_validates_clean():
    result = validate_pr_retirement_matrix(DEFAULT_MATRIX_PATH)
    assert result.ok
    assert result.errors == ()


def test_live_matrix_validate_path_and_mapping_agree():
    from_path = validate_path(DEFAULT_MATRIX_PATH)
    from_map = validate_matrix(_live())
    assert from_path.errors == from_map.errors
    assert from_path.ok and from_map.ok


def test_live_matrix_scientific_locks():
    rows = _live()["rows"]
    assert rows
    for row in rows:
        rc = row["research_classification"]
        assert rc["scientific_pass_allowed"] is False
        assert rc["biological_evidence"] is False


def test_live_matrix_no_invented_pass():
    result = validate_matrix(_live())
    assert not any(err.startswith("invented_pass:") for err in result.errors)


def test_live_matrix_proxy_only_on_allowlist():
    allowed_rows = []
    for row in _live()["rows"]:
        rc = row.get("research_classification") or {}
        flagged = bool(rc.get("proxy_evidence_flag")) or rc.get("evidence_mode") == "proxy"
        if not flagged:
            continue
        tokens = {
            str(row.get("id") or "").lower(),
            str(row.get("pr_number") or ""),
            str(row.get("branch") or "").lower(),
        }
        assert tokens & {
            "nts-pr-219",
            "219",
            "nts-pr-226",
            "226",
            "nts-branch-scientific-falsification-contract",
            "codex/scientific-falsification-contract",
        }, row.get("id")
        allowed_rows.append(row["id"])
    assert set(allowed_rows) == {
        "nts-pr-219",
        "nts-pr-226",
        "nts-branch-scientific-falsification-contract",
    }


def test_live_matrix_duplicate_candidates_empty():
    data = _live()
    assert data.get("duplicate_candidates") == []
    phase = data.get("research_phase") or {}
    assert phase.get("duplicate_candidates_verified") in ([], None)


def test_live_matrix_superseded_is_docs_only_216():
    data = _live()
    items = data.get("superseded_candidates") or []
    assert items
    for item in items:
        assert item["pr_number"] == 216
        assert item["superseded_by"] == 225
        assert item["whole_pr_superseded"] is False
        assert "docs" in str(item.get("scope") or "").lower() or "inventory" in str(
            item.get("scope") or ""
        ).lower()
        assert item.get("evidence")


def test_live_matrix_stacked_edges_detected():
    edges = detect_stack_edges(_live())
    expected = {
        (215, 211),
        (224, 215),
        (224, 211),
        (232, 224),
        (232, 215),
        (232, 211),
        (220, 212),
        (226, 219),
        (227, 213),
    }
    assert expected <= set(edges)
    assert child_before_parent_violations(_live()) == ()


def test_live_matrix_open_not_merged():
    for row in _live()["rows"]:
        if str(row.get("state") or "").upper() in {"OPEN", "DRAFT"} or row.get("draft") is True:
            assert row.get("merged") is False
            assert row.get("merge_status") in (None, "", "open")
            assert row.get("merged_at") in (None, "", False)


def test_live_matrix_billing_and_enospc_not_pass():
    result = validate_matrix(_live())
    assert not any(err.startswith("billing_or_enospc_as_pass:") for err in result.errors)
    for row in _live()["rows"]:
        summary = row.get("check_summary") or {}
        classification = str(summary.get("classification") or "")
        if classification in {"billing_not_started", "disk_fail", "job_started_install_fail"}:
            assert summary.get("treated_as_pass") in (None, False)
            assert str(summary.get("overall") or "").lower() not in {"pass", "success"}


def test_live_matrix_status_hints_in_lead_set():
    for row in _live()["rows"]:
        hint = row.get("status_hint")
        if hint in (None, ""):
            continue
        assert hint in ALLOWED_STATUS_HINTS


def test_deterministic_repeat():
    first = validate_pr_retirement_matrix(DEFAULT_MATRIX_PATH)
    second = validate_pr_retirement_matrix(DEFAULT_MATRIX_PATH)
    assert first.errors == second.errors
    assert first.ok == second.ok
    third = validate_matrix(_live())
    assert third.errors == first.errors


@pytest.mark.parametrize("filename,needle", _MALFORMED)
def test_malformed_fixtures_fail_closed(filename, needle):
    path = FIXTURE_DIR / filename
    result = validate_path(path)
    assert not result.ok
    assert any(needle in err for err in result.errors), result.errors


def test_warnings_never_count_as_success():
    tainted = ValidationResult(
        errors=("invented_pass: fixture",),
        warnings=(),
    )
    warned_only = ValidationResult(errors=(), warnings=("note only",))
    clean = ValidationResult(errors=(), warnings=())
    assert tainted.ok is False
    assert warned_only.ok is False
    assert clean.ok is True


def test_proxy_allowed_ids_do_not_fail():
    data = {
        "status_hint_allowed": ["keep_open", "needs_human_review"],
        "rows": [
            {
                "id": "nts-pr-219",
                "pr_number": 219,
                "state": "OPEN",
                "merged": False,
                "status_hint": "needs_human_review",
                "research_classification": {
                    "scientific_pass_allowed": False,
                    "biological_evidence": False,
                    "proxy_evidence_flag": True,
                    "claim_class": "proxy",
                    "evidence_mode": "proxy",
                    "bayesian_warning": True,
                },
            },
            {
                "id": "nts-pr-226",
                "pr_number": 226,
                "state": "OPEN",
                "merged": False,
                "status_hint": "needs_human_review",
                "research_classification": {
                    "scientific_pass_allowed": False,
                    "biological_evidence": False,
                    "proxy_flagged": True,
                },
            },
            {
                "id": "nts-branch-scientific-falsification-contract",
                "pr_number": None,
                "branch": "codex/scientific-falsification-contract",
                "state": "BRANCH_ONLY",
                "merged": False,
                "status_hint": "needs_human_review",
                "research_classification": {
                    "scientific_pass_allowed": False,
                    "biological_evidence": False,
                    "proxy_evidence_flag": True,
                    "evidence_mode": "proxy",
                },
            },
        ],
        "duplicate_candidates": [],
        "superseded_candidates": [],
    }
    result = validate_matrix(data)
    assert result.ok, result.errors
    assert "219" in ALLOWED_PROXY_IDENTIFIERS
    assert "codex/scientific-falsification-contract" in ALLOWED_PROXY_IDENTIFIERS


def test_stack_helper_rejects_child_before_parent_order():
    data = load_matrix(FIXTURE_DIR / "stacked_child_before_parent.yaml")
    edges = detect_stack_edges(data)
    assert (215, 211) in edges
    violations = child_before_parent_violations(data)
    assert violations
    assert any("215" in item and "211" in item for item in violations)


def test_stack_helper_uses_canonical_chains():
    assert CANONICAL_STACK_CHAINS == (
        (211, 215, 224, 232),
        (212, 220),
        (219, 226),
        (213, 227),
    )
    edges = detect_stack_edges({"rows": [], "relationships": []})
    assert (232, 211) in edges
    assert (220, 212) in edges
    assert (226, 219) in edges
    assert (227, 213) in edges


def test_docs_only_216_supersede_is_allowed():
    data = {
        "rows": [
            {
                "id": "nts-pr-216",
                "pr_number": 216,
                "state": "OPEN",
                "draft": True,
                "merged": False,
                "status_hint": "needs_human_review",
                "research_classification": {
                    "scientific_pass_allowed": False,
                    "biological_evidence": False,
                },
            }
        ],
        "duplicate_candidates": [],
        "superseded_candidates": [
            {
                "id": "nts-pr-216-inventory-docs",
                "pr_number": 216,
                "scope": "inventory_docs_only",
                "superseded_by": 225,
                "whole_pr_superseded": False,
                "evidence": ["#225 title superseding #216 inventory"],
            }
        ],
    }
    assert validate_matrix(data).ok


def test_evidenced_duplicate_is_allowed():
    data = {
        "rows": [
            {
                "id": "nts-pr-214",
                "pr_number": 214,
                "state": "OPEN",
                "merged": False,
                "status_hint": "keep_open",
                "research_classification": {
                    "scientific_pass_allowed": False,
                    "biological_evidence": False,
                },
            }
        ],
        "duplicate_candidates": [
            {
                "id": "nts-pr-214",
                "of": 220,
                "evidence": ["cited GitHub file overlap (fixture only)"],
            }
        ],
        "superseded_candidates": [],
    }
    result = validate_matrix(data)
    assert result.ok, result.errors


def test_status_hint_retire_is_rejected():
    data = {
        "rows": [
            {
                "id": "nts-pr-221",
                "pr_number": 221,
                "state": "OPEN",
                "merged": False,
                "status_hint": "retire",
                "research_classification": {
                    "scientific_pass_allowed": False,
                    "biological_evidence": False,
                },
            }
        ],
        "duplicate_candidates": [],
        "superseded_candidates": [],
    }
    result = validate_matrix(data)
    assert not result.ok
    assert any("status_hint_not_allowed" in err for err in result.errors)


def test_careful_wo_status_hint_allowed():
    data = {
        "rows": [
            {
                "id": "nts-pr-221",
                "pr_number": 221,
                "state": "OPEN",
                "merged": False,
                "status_hint": "blocked",
                "research_classification": {
                    "scientific_pass_allowed": False,
                    "biological_evidence": False,
                },
            }
        ],
        "duplicate_candidates": [],
        "superseded_candidates": [],
    }
    assert validate_matrix(data).ok


def test_retirement_order_child_before_parent_fails():
    data = {
        "rows": [
            {
                "id": "nts-pr-212",
                "pr_number": 212,
                "state": "OPEN",
                "merged": False,
                "status_hint": "keep_open",
                "research_classification": {
                    "scientific_pass_allowed": False,
                    "biological_evidence": False,
                },
            },
            {
                "id": "nts-pr-220",
                "pr_number": 220,
                "state": "OPEN",
                "merged": False,
                "status_hint": "keep_open",
                "research_classification": {
                    "scientific_pass_allowed": False,
                    "biological_evidence": False,
                },
            },
        ],
        "retirement_order": [220, 212],
        "duplicate_candidates": [],
        "superseded_candidates": [],
    }
    result = validate_matrix(data)
    assert not result.ok
    assert any("stacked_child_before_parent" in err for err in result.errors)


def test_unreadable_matrix_is_error_not_warning():
    result = validate_path(_RELEASE_DIR / "fixtures" / "pr_retirement" / "missing.yaml")
    assert not result.ok
    assert result.errors[0].startswith("matrix_load:")


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_ast_denylist_new_modules():
    offenders = []
    for path in _NEW_MODULES:
        imported = _imported_modules(path)
        for name in imported:
            if name in _AST_DENIED_MODULES or any(
                name == denied or name.startswith(denied + ".")
                for denied in _AST_DENIED_MODULES
            ):
                offenders.append((path.name, name))
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in _AST_DENIED_ATTRS:
                offenders.append((path.name, node.attr))
            if isinstance(node, ast.Name) and node.id in {"urlopen", "urlretrieve"}:
                offenders.append((path.name, node.id))
    assert not offenders, offenders


def test_no_secret_literals_in_new_modules():
    helper = _RELEASE_DIR / "pr_retirement_validate.py"
    text = helper.read_text(encoding="utf-8")
    match = _SECRET_VALUE_RE.search(text)
    assert match is None, f"{helper.name} contains secret-shaped literal {match.group(0)!r}"
    pem = "BEGIN " + "PRIVATE " + "KEY"
    env_assign = (
        "ANTHROPIC_" + "API_KEY=",
        "OPENAI_" + "API_KEY=",
        "AIRTABLE_" + "API_KEY=",
    )
    for path in _NEW_MODULES:
        body = path.read_text(encoding="utf-8")
        assert pem not in body, f"{path.name} contains PEM material"
        for token in env_assign:
            assert token not in body, f"{path.name} contains {token!r}"


def test_no_network_source_strings():
    helper = _RELEASE_DIR / "pr_retirement_validate.py"
    banned = (
        "requests.get(",
        "urllib.request",
        "http.client",
        "socket.create_connection",
        "urlopen(",
        "subprocess.",
    )
    text = helper.read_text(encoding="utf-8")
    for token in banned:
        assert token not in text, f"{helper.name} contains {token!r}"
