#!/usr/bin/env python3
"""Thin Release CLI wrapping QA ``tests.release.blocker_registry_validate``.

Does not rewrite validation rules. Inventory is not evidence. Synthetic
results remain NOT_SUPPORTED. Billing-not-started is not pytest PASS.
Empty-step FAILURE is not TEST_FAILURE. Never invent PASS.

Usage::

    python scripts/validate_release_blockers.py [--registry PATH]
        [--format json|markdown|both] [--output-dir PATH]

Default: validate the live registry and print a report to stdout.
Files are written only when ``--output-dir`` is set. Generated reports
must not be committed.

Exit 0 if the QA error list is empty; exit 1 if it is not.
Warnings are never treated as success. Offline; no network clients.
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

from tests.release.blocker_registry_validate import (  # noqa: E402
    REGISTRY_PATH,
    BlockerRegistryValidationError,
    collect_forbidden_imports,
    load_registry,
    validate,
    validate_blocker_registry,
)

CLI_ID = "validate_release_blockers"
DEFAULT_FORMAT = "json"
JSON_FILENAME = "validate_release_blockers.json"
MARKDOWN_FILENAME = "validate_release_blockers.md"
BLOCKER_SUMMARY_KEYS: tuple[str, ...] = (
    "id",
    "category",
    "severity",
    "evidence",
    "scientific_impact",
    "release_impact",
)
CURRENT_INTEGRATION_ECHO_KEYS: tuple[str, ...] = (
    "head_ref_oid",
    "expected_head_from_work_order",
    "current_head_mismatch",
    "merged",
    "state",
)

# Human-triage statements. These are process caveats, not measured values.
REQUIRED_STATEMENTS: tuple[str, ...] = (
    "Inventory is not evidence.",
    "Synthetic results remain NOT_SUPPORTED. Never invent PASS.",
    "Billing-not-started is not pytest PASS.",
    "Empty-step FAILURE is not TEST_FAILURE.",
    "validation_ok means the QA error list is empty; it is not a scientific PASS.",
    "Remediation queue is owned by Integration and is not invented here.",
    "Merger: do not merge. Never close PRs.",
)


def _echo_or_null(mapping: Mapping[str, Any] | None, key: str) -> Any:
    if not isinstance(mapping, Mapping) or key not in mapping:
        return None
    return mapping[key]


def _as_mapping(value: Any) -> Mapping[str, Any] | None:
    return value if isinstance(value, Mapping) else None


def _summarize_blocker(row: Mapping[str, Any]) -> dict[str, Any]:
    evidence = row.get("exact_evidence") if "exact_evidence" in row else None
    if evidence is not None and not isinstance(evidence, list):
        evidence = None
    return {
        "id": _echo_or_null(row, "id"),
        "category": _echo_or_null(row, "category"),
        "severity": _echo_or_null(row, "severity"),
        "evidence": evidence,
        "scientific_impact": _echo_or_null(row, "scientific_impact"),
        "release_impact": _echo_or_null(row, "release_impact"),
    }


def _summarize_blockers(doc: Mapping[str, Any] | None) -> list[dict[str, Any]] | None:
    if not isinstance(doc, Mapping) or "blockers" not in doc:
        return None
    raw = doc.get("blockers")
    if not isinstance(raw, list):
        return None
    rows: list[dict[str, Any]] = []
    for item in raw:
        if isinstance(item, Mapping):
            rows.append(_summarize_blocker(item))
        else:
            rows.append({key: None for key in BLOCKER_SUMMARY_KEYS})
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


def build_report(
    doc: Mapping[str, Any] | None,
    errors: Sequence[str],
    *,
    registry_path: str | Path,
) -> dict[str, Any]:
    """Build an Integration-facing report by echoing registry fields or null."""
    error_list = [str(item) for item in errors]
    research = _as_mapping(doc.get("research_phase")) if isinstance(doc, Mapping) else None
    return {
        "cli_id": CLI_ID,
        "wraps": "tests.release.blocker_registry_validate",
        "offline": True,
        "validation_ok": error_list == [],
        "errors": error_list,
        "registry_path": str(registry_path),
        "inventory_is_not_evidence": _echo_or_null(doc, "inventory_is_not_evidence"),
        "empirical_pass_from_this_pack": _echo_or_null(
            doc, "empirical_pass_from_this_pack"
        ),
        "scientific_pass_from_this_pack": _echo_or_null(
            doc, "scientific_pass_from_this_pack"
        ),
        "synthetic_status": _echo_or_null(research, "synthetic_status"),
        "current_integration": _summarize_current_integration(doc),
        "blockers": _summarize_blockers(doc),
        "merger_instruction": _echo_or_null(doc, "merger_instruction"),
        "never_close_prs": _echo_or_null(doc, "never_close_prs"),
        "remediation_queue": None,
        "next_action": "Integration owns the remediation queue; this CLI does not invent one.",
        "required_statements": list(REQUIRED_STATEMENTS),
    }


def dumps_json(report: Mapping[str, Any]) -> str:
    return json.dumps(report, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False) + "\n"


def _md_cell(value: Any) -> str:
    if value is None:
        return "null"
    text = str(value).replace("|", "\\|").replace("\n", " ")
    return text


def render_markdown(report: Mapping[str, Any]) -> str:
    errors = report.get("errors") or []
    blockers = report.get("blockers")
    current = report.get("current_integration")
    current_map = current if isinstance(current, Mapping) else {}
    lines = [
        "# Release blocker registry validation",
        "",
        "Thin CLI wrap of QA `tests.release.blocker_registry_validate`. Rules are not rewritten.",
        "",
    ]
    lines.extend(f"- {item}" for item in REQUIRED_STATEMENTS)
    lines.extend(
        [
            "",
            f"**validation_ok:** `{report.get('validation_ok')}`",
            f"**registry_path:** `{report.get('registry_path')}`",
            f"**inventory_is_not_evidence:** `{report.get('inventory_is_not_evidence')}`",
            f"**empirical_pass_from_this_pack:** `{report.get('empirical_pass_from_this_pack')}`",
            f"**scientific_pass_from_this_pack:** `{report.get('scientific_pass_from_this_pack')}`",
            f"**synthetic_status:** `{report.get('synthetic_status')}`",
            f"**merger_instruction:** `{report.get('merger_instruction')}`",
            f"**never_close_prs:** `{report.get('never_close_prs')}`",
            f"**remediation_queue:** `{report.get('remediation_queue')}`",
            "",
            "## Current integration (echoed or null)",
            "",
            f"- head_ref_oid: `{current_map.get('head_ref_oid')}`",
            f"- expected_head_from_work_order: `{current_map.get('expected_head_from_work_order')}`",
            f"- current_head_mismatch: `{current_map.get('current_head_mismatch')}`",
            f"- merged: `{current_map.get('merged')}`",
            f"- state: `{current_map.get('state')}`",
            "",
            "## Validation errors",
            "",
        ]
    )
    if errors:
        lines.extend(f"- `{item}`" for item in errors)
    else:
        lines.append("- (none)")
    lines.extend(["", "## Blocker summary", ""])
    if blockers is None:
        lines.append("Blocker list unavailable (null).")
    elif not blockers:
        lines.append("No blocker rows were present in the registry.")
    else:
        lines.append(
            "| id | category | severity | scientific_impact | release_impact |"
        )
        lines.append("| --- | --- | --- | --- | --- |")
        for row in blockers:
            if not isinstance(row, Mapping):
                continue
            lines.append(
                "| {id} | {category} | {severity} | {scientific_impact} | {release_impact} |".format(
                    id=_md_cell(row.get("id")),
                    category=_md_cell(row.get("category")),
                    severity=_md_cell(row.get("severity")),
                    scientific_impact=_md_cell(row.get("scientific_impact")),
                    release_impact=_md_cell(row.get("release_impact")),
                )
            )
        lines.extend(["", "### Evidence (echoed exact_evidence, or null)", ""])
        for row in blockers:
            if not isinstance(row, Mapping):
                continue
            ident = _md_cell(row.get("id"))
            evidence = row.get("evidence")
            lines.append(f"#### `{ident}`")
            if evidence is None:
                lines.append("- evidence: null")
            elif isinstance(evidence, list) and evidence:
                for item in evidence:
                    lines.append(f"- {_md_cell(item)}")
            else:
                lines.append("- evidence: (empty list)")
            lines.append("")
    lines.extend(
        [
            "## Next action",
            "",
            str(report.get("next_action")),
            "",
            "Merger: **do not merge.** Never close PRs.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate configs/release/blocker_registry.yaml by wrapping QA "
            "tests.release.blocker_registry_validate. Offline. Do not invent PASS."
        )
    )
    parser.add_argument(
        "--registry",
        default=None,
        help="Registry YAML (default: configs/release/blocker_registry.yaml)",
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


def load_and_validate(registry_path: Path) -> tuple[Mapping[str, Any] | None, list[str]]:
    """Load then validate via QA helpers. Fail closed on load errors."""
    ast_errors = _self_ast_errors()
    if not registry_path.is_file():
        return None, ast_errors + [f"registry:not_found:{registry_path.as_posix()}"]
    try:
        doc = load_registry(registry_path)
    except BlockerRegistryValidationError as exc:
        return None, ast_errors + list(exc.errors)
    except Exception as exc:  # noqa: BLE001 — fail closed; do not invent a document
        return None, ast_errors + [f"registry:load_failed:{type(exc).__name__}:{exc}"]

    via_alias = validate_blocker_registry(doc)
    via_canonical = validate(doc)
    if via_alias != via_canonical:
        merged = sorted(set(via_alias) | set(via_canonical) | {"qa_validate_alias_mismatch"})
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
    registry = Path(args.registry) if args.registry else REGISTRY_PATH
    if not registry.is_absolute():
        registry = Path.cwd() / registry
    doc, errors = load_and_validate(registry)
    report = build_report(doc, errors, registry_path=registry)
    output_dir = Path(args.output_dir) if args.output_dir else None
    try:
        emit_report(report, fmt=args.format, output_dir=output_dir)
    except ValueError as exc:
        sys.stderr.write(f"validate_release_blockers failed: {exc}\n")
        return 1
    except OSError as exc:
        sys.stderr.write(f"validate_release_blockers failed: {exc}\n")
        return 1
    return 0 if errors == [] else 1


if __name__ == "__main__":
    raise SystemExit(main())
