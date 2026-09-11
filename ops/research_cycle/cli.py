"""CLI for the research-cycle operator pack."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ops.research_cycle.catalog import load_catalog
from ops.research_cycle.exit_codes import BLOCKED, NOT_AVAILABLE
from ops.research_cycle.inventory import build_inventory, render_inventory_markdown
from ops.research_cycle.json_util import dumps
from ops.research_cycle.runner import config_from_namespace, discover_repo_root, run_audit
from ops.research_cycle.safety import SafetyError, require_output_dir
from ops.research_cycle.validate_pack import validate_catalog_document


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="research-cycle-operator-pack",
        description=(
            "Read-only orchestrator for existing research-cycle audit CLIs. "
            "--output-dir is required for audit. Infrastructure PASS is not a scientific PASS."
        ),
    )
    parser.add_argument(
        "command",
        nargs="?",
        default="audit",
        choices=("audit", "inventory", "validate-catalog"),
        help="audit (default), inventory, or validate-catalog",
    )
    parser.add_argument("--output-dir", help="Required for audit. Only write location.")
    parser.add_argument("--catalog", help="Catalog JSON path (default: ops/research_cycle/catalog.json)")
    parser.add_argument("--python", default=sys.executable, help="Python interpreter for child CLIs")
    parser.add_argument("--repo-root", help="Repository root (default: auto-detect)")
    parser.add_argument("--registry", help="Research-cycle registry JSON")
    parser.add_argument("--claims", help="Research-claims JSON")
    parser.add_argument("--empirical-manifest", help="Empirical-source manifest JSON/YAML")
    parser.add_argument("--provenance", help="Dataset provenance declaration JSON")
    parser.add_argument("--research-state-manifest", help="compile_research_state manifest JSON")
    parser.add_argument("--performance-pair", help="Performance release-evidence pair JSON")
    parser.add_argument("--candidates", help="dataset_acquisition candidate export JSON")
    parser.add_argument("--candidate-id", help="Candidate id for cache-policy dry run")
    parser.add_argument("--cache-target-root", help="Declared repo-relative target_root (never executed)")
    parser.add_argument("--benchmark-matrix", help="run_benchmark_matrix.py matrix path")
    parser.add_argument("--steps", help="Comma-separated step ids to run")
    parser.add_argument("--allow-solver", action="store_true", help="Opt in to non-dry-run campaign commands")
    parser.add_argument("--include-optional", action="store_true", help="Also run optional catalog extras")
    parser.add_argument("--timeout-s", type=int, help="Override every child timeout")
    parser.add_argument("--now", help="Frozen timestamp for deterministic reports")
    parser.add_argument(
        "--shell-family",
        choices=("posix", "powershell"),
        default="posix",
        help="Which thin wrapper invoked this pack",
    )
    parser.add_argument("--no-surfaces", action="store_true", help="Skip Obsidian/command-center/RAG emission")
    parser.add_argument("--json", action="store_true", help="Print inventory/validation as JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    repo_root = Path(args.repo_root).resolve() if args.repo_root else discover_repo_root()
    catalog_path = Path(args.catalog).resolve() if args.catalog else repo_root / "ops" / "research_cycle" / "catalog.json"

    if args.command == "validate-catalog":
        try:
            report = validate_catalog_document(catalog_path)
        except Exception as exc:  # noqa: BLE001 - CLI surfaces catalog errors
            print(str(exc), file=sys.stderr)
            return NOT_AVAILABLE
        if args.json:
            print(dumps(report), end="\n")
        else:
            print(f"catalog_ok={report['ok']} steps={report['step_count']}")
        return 0 if report["ok"] else 30

    try:
        catalog = load_catalog(catalog_path)
    except FileNotFoundError:
        print(f"catalog not found: {catalog_path}", file=sys.stderr)
        return NOT_AVAILABLE
    except Exception as exc:  # noqa: BLE001
        print(f"catalog load failed: {exc}", file=sys.stderr)
        return NOT_AVAILABLE

    if args.command == "inventory":
        inventory = build_inventory(catalog, repo_root=repo_root, python=args.python)
        if args.output_dir:
            try:
                out = require_output_dir(args.output_dir)
            except SafetyError as exc:
                print(str(exc), file=sys.stderr)
                return BLOCKED
            (out / "inventory.json").write_text(dumps(inventory) + "\n", encoding="utf-8")
            (out / "inventory.md").write_text(render_inventory_markdown(inventory), encoding="utf-8")
        if args.json or not args.output_dir:
            print(dumps(inventory), end="\n")
        return 0

    try:
        output_dir = require_output_dir(args.output_dir)
    except SafetyError as exc:
        print(str(exc), file=sys.stderr)
        return BLOCKED

    config = config_from_namespace(args, repo_root=repo_root, output_dir=output_dir, catalog=catalog)
    try:
        report, code = run_audit(config)
    except SafetyError as exc:
        print(str(exc), file=sys.stderr)
        return BLOCKED
    print(f"overall_status={report['overall_status']} exit={code}")
    print("Infrastructure PASS is not a scientific PASS. Synthetic is not an empirical PASS.")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
