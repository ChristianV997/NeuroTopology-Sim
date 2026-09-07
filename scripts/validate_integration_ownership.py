#!/usr/bin/env python3
"""Thin Release CLI wrapping QA ``tests.release.integration_ownership_validate``.

Does not rewrite validation rules. Inventory is not evidence. INTEGRATED_ONLY
is not merged into main. Synthetic remains NOT_SUPPORTED. Never invent PASS.
Proxy Bayes ≠ formal K. Empty-step CI FAILURE is not BLOCKED_BY_TESTS.
Billing-not-started is not pytest PASS.

Usage::

    python scripts/validate_integration_ownership.py [--inventory PATH]
        [--format json|markdown|both] [--output-dir PATH]

Default: validate the live inventory and print a report to stdout.
Files are written only when ``--output-dir`` is set. Generated reports
must not be committed.

Exit 0 if the QA error list is empty; exit 1 if it is not.
Warnings are never treated as success. Offline; no network clients.
Codex C is the sole merger; this CLI does not invent the merger queue.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tests.release.integration_ownership_validate import (  # noqa: E402
    INVENTORY_PATH,
    IntegrationOwnershipValidationError,
    collect_forbidden_imports,
    load_inventory,
    validate,
    validate_integration_ownership,
)

CLI_ID = "validate_integration_ownership"
DEFAULT_FORMAT = "json"
JSON_FILENAME = "validate_integration_ownership.json"
MARKDOWN_FILENAME = "validate_integration_ownership.md"
WORK_ITEM_SUMMARY_KEYS: tuple[str, ...] = ("id", "status", "pr_number")
CURRENT_INTEGRATION_ECHO_KEYS: tuple[str, ...] = (
    "head_ref_oid",
    "merged",
    "on_origin_main",
    "status",
)

# Human-triage statements. These are process caveats, not measured values.
REQUIRED_STATEMENTS: tuple[str, ...] = (
    "Inventory is not evidence.",
    "INTEGRATED_ONLY is not merged into main.",
    "Synthetic remains NOT_SUPPORTED. Never invent PASS.",
    "Proxy Bayes ≠ formal K.",
    "Empty-step CI FAILURE is not BLOCKED_BY_TESTS.",
    "Billing-not-started is not pytest PASS.",
    "validation_ok means QA error list empty; not a scientific PASS.",
    "Codex C is the sole merger; this CLI does not invent the merger queue.",
    "Merger: do not merge. Never close/retarget PRs.",
)


def _echo_or_null(mapping: Mapping[str, Any] | None, key: str) -> Any:
    if not isinstance(mapping, Mapping) or key not in mapping:
        return None
    return mapping[key]


def _as_mapping(value: Any) -> Mapping[str, Any] | None:
    return value if isinstance(value, Mapping) else None


def _summarize_work_item(row: Mapping[str, Any]) -> dict[str, Any]:
    return {key: _echo_or_null(row, key) for key in WORK_ITEM_SUMMARY_KEYS}


def _summarize_work_items(doc: Mapping[str, Any] | None) -> list[dict[str, Any]] | None:
    if not isinstance(doc, Mapping) or "work_items" not in doc:
        return None
    raw = doc.get("work_items")
    if not isinstance(raw, list):
        return None
    rows: list[dict[str, Any]] = []
    for item in raw:
        if isinstance(item, Mapping):
            rows.append(_summarize_work_item(item))
        else:
            rows.append({key: None for key in WORK_ITEM_SUMMARY_KEYS})
    return rows


def _summarize_current_integration(
    doc: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    if not isinstance(doc, Mapping) or "current_integration" not in doc:
        return None
    current = _as_mapping(doc.get("current_integration"))
    if current is None:
        return None
    return {key: _echo_or_null(current, key) for key in CURRENT_INTEGRATION_ECHO_KEYS}


def _synthetic_status(doc: Mapping[str, Any] | None) -> Any:
    """Echo research_phase.synthetic_status, else top-level; never invent PASS."""
    if not isinstance(doc, Mapping):
        return None
    research = _as_mapping(doc.get("research_phase"))
    if research is not None and "synthetic_status" in research:
        return research.get("synthetic_status")
    if "synthetic_status" in doc:
        return doc.get("synthetic_status")
    return None


def build_report(
    doc: Mapping[str, Any] | None,
    errors: Sequence[str],
    *,
    inventory_path: str | Path,
) -> dict[str, Any]:
    """Build an Integration-facing report by echoing inventory fields or null."""
    error_list = [str(item) for item in errors]
    return {
        "cli_id": CLI_ID,
        "wraps": "tests.release.integration_ownership_validate",
        "offline": True,
        "validation_ok": error_list == [],
        "errors": error_list,
        "inventory_path": str(inventory_path),
        "inventory_is_not_evidence": _echo_or_null(doc, "inventory_is_not_evidence"),
        "empirical_pass_from_this_pack": _echo_or_null(
            doc, "empirical_pass_from_this_pack"
        ),
        "CURRENT_INTEGRATION_HEAD": _echo_or_null(doc, "CURRENT_INTEGRATION_HEAD"),
        "current_integration": _summarize_current_integration(doc),
        "work_items": _summarize_work_items(doc),
        "sole_merger": _echo_or_null(doc, "sole_merger"),
        "synthetic_status": _synthetic_status(doc),
        "merger_instruction": _echo_or_null(doc, "merger_instruction"),
        "never_close_prs": _echo_or_null(doc, "never_close_prs"),
        "codex_c_merger_queue": None,
        "required_statements": list(REQUIRED_STATEMENTS),
    }


def dumps_json(report: Mapping[str, Any]) -> str:
    return (
        json.dumps(
            report,
            sort_keys=True,
            indent=2,
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    )


def _md_cell(value: Any) -> str:
    if value is None:
        return "null"
    text = str(value).replace("|", "\\|").replace("\n", " ")
    return text


def render_markdown(report: Mapping[str, Any]) -> str:
    errors = report.get("errors") or []
    work_items = report.get("work_items")
    current = report.get("current_integration")
    current_map = current if isinstance(current, Mapping) else {}
    lines = [
        "# Integration ownership inventory validation",
        "",
        "Thin CLI wrap of QA `tests.release.integration_ownership_validate`. Rules are not rewritten.",
        "",
    ]
    lines.extend(f"- {item}" for item in REQUIRED_STATEMENTS)
    lines.extend(
        [
            "",
            f"**validation_ok:** `{report.get('validation_ok')}`",
            f"**inventory_path:** `{report.get('inventory_path')}`",
            f"**inventory_is_not_evidence:** `{report.get('inventory_is_not_evidence')}`",
            f"**empirical_pass_from_this_pack:** `{report.get('empirical_pass_from_this_pack')}`",
            f"**CURRENT_INTEGRATION_HEAD:** `{report.get('CURRENT_INTEGRATION_HEAD')}`",
            f"**sole_merger:** `{report.get('sole_merger')}`",
            f"**synthetic_status:** `{report.get('synthetic_status')}`",
            f"**merger_instruction:** `{report.get('merger_instruction')}`",
            f"**never_close_prs:** `{report.get('never_close_prs')}`",
            f"**codex_c_merger_queue:** `{report.get('codex_c_merger_queue')}`",
            "",
            "## Current integration (echoed or null)",
            "",
            f"- head_ref_oid: `{current_map.get('head_ref_oid')}`",
            f"- merged: `{current_map.get('merged')}`",
            f"- on_origin_main: `{current_map.get('on_origin_main')}`",
            f"- status: `{current_map.get('status')}`",
            "",
            "## Validation errors",
            "",
        ]
    )
    if errors:
        lines.extend(f"- `{item}`" for item in errors)
    else:
        lines.append("- (none)")
    lines.extend(["", "## Work items summary", ""])
    if work_items is None:
        lines.append("Work-item list unavailable (null).")
    elif not work_items:
        lines.append("No work-item rows were present in the inventory.")
    else:
        lines.append("| id | status | pr_number |")
        lines.append("| --- | --- | --- |")
        for row in work_items:
            if not isinstance(row, Mapping):
                continue
            lines.append(
                "| {id} | {status} | {pr_number} |".format(
                    id=_md_cell(row.get("id")),
                    status=_md_cell(row.get("status")),
                    pr_number=_md_cell(row.get("pr_number")),
                )
            )
    lines.extend(
        [
            "",
            "## Next action",
            "",
            "Integration owns the Codex C merger queue; this CLI does not invent one.",
            "",
            "Merger: **do not merge.** Never close/retarget PRs.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate configs/release/integration_ownership.yaml by wrapping QA "
            "tests.release.integration_ownership_validate. Offline. Do not invent PASS."
        )
    )
    parser.add_argument(
        "--inventory",
        default=None,
        help="Inventory YAML (default: configs/release/integration_ownership.yaml)",
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
    return parser.parse_args(list(sys.argv[1:] if argv is None else argv))


def _self_ast_errors() -> list[str]:
    return collect_forbidden_imports(Path(__file__))


def load_and_validate(
    inventory_path: Path,
) -> tuple[Mapping[str, Any] | None, list[str]]:
    """Load then validate via QA helpers. Fail closed on load errors."""
    ast_errors = _self_ast_errors()
    if not inventory_path.is_file():
        return None, ast_errors + [f"inventory:not_found:{inventory_path.as_posix()}"]
    try:
        doc = load_inventory(inventory_path)
    except IntegrationOwnershipValidationError as exc:
        return None, ast_errors + list(exc.errors)
    except Exception as exc:  # noqa: BLE001 — fail closed; do not invent a document
        return None, ast_errors + [f"inventory:load_failed:{type(exc).__name__}:{exc}"]

    via_alias = validate_integration_ownership(doc)
    via_canonical = validate(doc)
    if via_alias != via_canonical:
        merged = sorted(
            set(via_alias) | set(via_canonical) | {"qa_validate_alias_mismatch"}
        )
        return doc, ast_errors + merged
    return doc, ast_errors + via_alias


def emit_report(
    report: Mapping[str, Any],
    *,
    fmt: str,
    output_dir: Path | None,
) -> list[Path]:
    payloads: list[tuple[str, str]] = []
    if fmt in {"json", "both"}:
        payloads.append(("json", dumps_json(report)))
    if fmt in {"markdown", "both"}:
        payloads.append(("markdown", render_markdown(report)))

    if output_dir is None:
        chunks = [text for _, text in payloads]
        sys.stdout.write("\n".join(chunk.rstrip("\n") for chunk in chunks) + "\n")
        return []

    output_dir.mkdir(parents=True, exist_ok=True)
    names = {"json": JSON_FILENAME, "markdown": MARKDOWN_FILENAME}
    written: list[Path] = []
    for kind, text in payloads:
        path = output_dir / names[kind]
        path.write_text(text, encoding="utf-8")
        written.append(path)
    return written


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    inventory = Path(args.inventory) if args.inventory else INVENTORY_PATH
    if not inventory.is_absolute():
        inventory = Path.cwd() / inventory
    doc, errors = load_and_validate(inventory)
    report = build_report(doc, errors, inventory_path=inventory)
    output_dir = Path(args.output_dir) if args.output_dir else None
    try:
        emit_report(report, fmt=args.format, output_dir=output_dir)
    except ValueError as exc:
        sys.stderr.write(f"validate_integration_ownership failed: {exc}\n")
        return 1
    except OSError as exc:
        sys.stderr.write(f"validate_integration_ownership failed: {exc}\n")
        return 1
    return 0 if errors == [] else 1


if __name__ == "__main__":
    raise SystemExit(main())
