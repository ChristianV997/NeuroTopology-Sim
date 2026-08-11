"""ExternalToolRegistry CLI.

Usage::

    # validate the seed registry
    python -m external_tools.export_registry --validate

    # list every tool (compact summary)
    python -m external_tools.export_registry --list

    # filter by priority / integration mode / category (each implies a
    # filtered listing even without --list)
    python -m external_tools.export_registry --priority P0
    python -m external_tools.export_registry --integration-mode optional_backend
    python -m external_tools.export_registry --category topology_tda

    # rank the next safe, high-leverage adapter candidates
    python -m external_tools.export_registry --recommended-next
    python -m external_tools.export_registry --recommended-next --limit 5

    # dump the (validated) seed registry to a consolidated output file
    python -m external_tools.export_registry --out outputs/external_tools/registry.json

This is the package's only CLI entry point. `external_tools.tool_record`,
`external_tools.adapter_contract`, and `external_tools.registry` are
library-only, matching how `benchmarks.dataset_registry`/
`benchmarks.artifact_registry` have no CLI of their own even though
`benchmarks.export_registry` does.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Optional

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from external_tools.registry import ExternalToolRegistry, RegistryError  # noqa: E402
from external_tools.tool_record import ExternalToolRecordV1  # noqa: E402

_DEFAULT_SEED = _REPO_ROOT / "external_tools" / "registry_seed.json"


def _summarize(record: ExternalToolRecordV1) -> dict[str, Any]:
    return {
        "tool_id": record.tool_id,
        "name": record.name,
        "category": record.category,
        "license": record.license,
        "license_risk": record.license_risk,
        "commercial_use_status": record.commercial_use_status,
        "integration_mode": record.integration_mode,
        "priority": record.priority,
        "current_status": record.current_status,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--registry", type=Path, default=_DEFAULT_SEED,
        help=f"registry JSON to load (default: {_DEFAULT_SEED.relative_to(_REPO_ROOT)})",
    )
    parser.add_argument("--out", type=Path, default=None, help="write the (validated) registry here")
    parser.add_argument("--validate", action="store_true", help="validate every record in the registry")
    parser.add_argument("--list", action="store_true", help="list every tool (or the filtered subset)")
    parser.add_argument("--priority", default=None, help="filter by priority (e.g. P0)")
    parser.add_argument("--integration-mode", default=None, help="filter by integration_mode")
    parser.add_argument("--category", default=None, help="filter by category")
    parser.add_argument(
        "--recommended-next", action="store_true",
        help="rank the next safe, high-leverage adapter candidates",
    )
    parser.add_argument("--limit", type=int, default=None, help="max results for --recommended-next")
    args = parser.parse_args()

    try:
        registry = ExternalToolRegistry.load(args.registry)
    except RegistryError as exc:
        print(f"[external_tools.export_registry] FAILED: {exc}")
        return 1

    exit_code = 0
    any_filter = args.priority is not None or args.integration_mode is not None or args.category is not None

    if args.validate:
        errors = registry.validate()
        if errors:
            print(json.dumps({"valid": False, "errors": errors}, indent=2))
            exit_code = 1
        else:
            print(json.dumps({"valid": True, "tools": len(registry.tools)}, indent=2))

    if args.list or any_filter:
        tools = registry.list_tools(
            priority=args.priority, integration_mode=args.integration_mode, category=args.category,
        )
        print(json.dumps([_summarize(t) for t in tools], indent=2))

    if args.recommended_next:
        ranked = registry.recommended_next(limit=args.limit)
        print(json.dumps([_summarize(t) for t in ranked], indent=2))

    no_action = not any([args.validate, args.list, any_filter, args.recommended_next])

    if args.out:
        # --out always (re)writes a validated snapshot of the loaded
        # registry, whether or not another action was also requested --
        # mirrors benchmarks.export_registry's --out behavior.
        errors = registry.validate()
        written = registry.save(args.out)
        print(json.dumps({"out": str(written), "tools": len(registry.tools), "valid": not errors}, indent=2))
        if errors:
            exit_code = 1

    if no_action and not args.out:
        parser.print_help()
        return 1

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
