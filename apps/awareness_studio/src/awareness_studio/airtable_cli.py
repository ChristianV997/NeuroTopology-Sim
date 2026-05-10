"""
CLI: awareness-airtable <command> [options]

Commands:
  status                     Show Airtable configuration status
  sync-runs [--allow-write]  Sync run cards to Airtable Runs table
"""
import argparse
import json
import sys
from pathlib import Path


def cmd_status(args: argparse.Namespace) -> int:
    from awareness_studio.integrations.airtable_sync import airtable_status
    status = airtable_status()
    print(json.dumps(status, indent=2))
    if not status["api_key_set"] or not status["base_id_set"]:
        print("\n[WARN] Airtable not fully configured.", file=sys.stderr)
        return 1
    return 0


def cmd_sync_runs(args: argparse.Namespace) -> int:
    from awareness_studio.integrations.airtable_sync import sync_runs_from_run_cards
    from awareness_studio import config

    run_cards_dir = Path(args.run_cards_dir) if args.run_cards_dir else None

    if args.allow_write and not config.AIRTABLE_ENABLED:
        print(
            "[ERROR] --allow-write requested but AIRTABLE_ENABLED=false. "
            "Set AIRTABLE_ENABLED=true in .env to permit writes.",
            file=sys.stderr,
        )
        return 1

    summary = sync_runs_from_run_cards(run_cards_dir=run_cards_dir, allow_write=args.allow_write)
    data = summary.to_dict()
    print(json.dumps(data, indent=2))

    if summary.errors:
        print(f"\n[WARN] {len(summary.errors)} sync error(s).", file=sys.stderr)
        return 2
    if summary.dry_run:
        print(
            f"\n[DRY-RUN] Would sync {summary.total} run(s). "
            "Pass --allow-write to execute.",
            file=sys.stderr,
        )
    else:
        print(f"\n[OK] Synced {summary.updated}/{summary.total} runs.", file=sys.stderr)
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Awareness Studio — Airtable Ops Mirror CLI"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="Check Airtable configuration and connectivity")

    sync_p = sub.add_parser("sync-runs", help="Sync run cards to Airtable")
    sync_p.add_argument(
        "--allow-write", action="store_true",
        help="Execute writes (requires AIRTABLE_ENABLED=true)",
    )
    sync_p.add_argument(
        "--run-cards-dir", default=None,
        help="Override run cards directory (default: .data/run_cards/)",
    )

    args = parser.parse_args()
    dispatch = {"status": cmd_status, "sync-runs": cmd_sync_runs}
    sys.exit(dispatch[args.command](args))


if __name__ == "__main__":
    main()
