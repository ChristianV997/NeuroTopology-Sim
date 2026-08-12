"""CLI for the open-source trend scout + integration opportunity registry.

    python -m oss_opportunities.export_oss_opportunities from-manual-seed \
        --seed <seed.json> --out outputs/oss_opportunities/opportunities

    python -m oss_opportunities.export_oss_opportunities from-trendshift-fixture \
        --fixture <trendshift_snapshot.json> --out outputs/oss_opportunities/trendshift

    python -m oss_opportunities.export_oss_opportunities from-starmap-fixture \
        --fixture <starmap_snapshot.json> --out outputs/oss_opportunities/starmap

    python -m oss_opportunities.export_oss_opportunities live-trendshift-scan \
        --timeframe daily --timeframe weekly --out outputs/oss_opportunities/live \
        --allow-live-network

    python -m oss_opportunities.export_oss_opportunities plan \
        --batch <OpenSourceLeverageBatch.json> \
        --out outputs/oss_opportunities/plan --max-selected 20

    python -m oss_opportunities.export_oss_opportunities render \
        --batch <OpenSourceLeverageBatch.json> --plan <OpenSourceIntegrationPlan.json> \
        --out outputs/oss_opportunities/summary

No subcommand ever installs a dependency, clones a repository, or executes
external code -- this CLI is metadata-scouting-and-planning only.
`live-trendshift-scan` performs zero network I/O unless
`--allow-live-network` is explicitly passed; even then it only fetches
Trendshift's public trending pages (bounded, best-effort HTML parse) and
never redistributes a raw Trendshift Signal API payload.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from oss_opportunities.opportunity_batch import OpenSourceLeverageBatchV1, build_opportunities_from_candidates
from oss_opportunities.planner import OpenSourceIntegrationPlanV1, plan_oss_integrations_from_opportunities
from oss_opportunities.renderer import write_oss_opportunity_summary
from oss_opportunities.repository_candidate import OpenSourceRepositoryCandidateV1
from oss_opportunities.source_ingestion import (
    TrendshiftLiveScanError,
    import_from_manual_seed,
    import_from_starmap_fixture,
    import_from_trendshift_fixture,
    import_from_trendshift_live_scan,
)
from oss_opportunities.validation import OssOpportunityStoreError, validate_repo_relative_root

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _resolve_out_root(raw: str) -> Path:
    errors = validate_repo_relative_root(raw, "out")
    if errors:
        raise OssOpportunityStoreError("; ".join(errors))
    return (_REPO_ROOT / raw).resolve()


def _build_and_write(candidates: list[OpenSourceRepositoryCandidateV1], out_root: Path) -> OpenSourceLeverageBatchV1:
    if not candidates:
        raise OssOpportunityStoreError("no candidates produced -- nothing to score")
    batch = build_opportunities_from_candidates(candidates)
    batch.write_json(out_root / "OpenSourceLeverageBatch.json")
    return batch


def _print_batch_summary(batch: OpenSourceLeverageBatchV1) -> None:
    print(json.dumps(
        {
            "batch_id": batch.batch_id,
            "candidates_seen": batch.candidates_seen,
            "opportunities_ranked": len(batch.opportunities_ranked),
            "opportunities_rejected": len(batch.opportunities_rejected),
            "top_by_category": batch.top_by_category,
            "top_immediate_adapters": batch.top_immediate_adapters,
            "top_architecture_emulation": batch.top_architecture_emulation,
        },
        indent=2,
    ))


def _cmd_from_manual_seed(args: argparse.Namespace) -> int:
    out_root = _resolve_out_root(args.out)
    candidates = import_from_manual_seed(args.seed)
    batch = _build_and_write(candidates, out_root)
    _print_batch_summary(batch)
    return 0


def _cmd_from_trendshift_fixture(args: argparse.Namespace) -> int:
    out_root = _resolve_out_root(args.out)
    candidates = import_from_trendshift_fixture(args.fixture)
    batch = _build_and_write(candidates, out_root)
    _print_batch_summary(batch)
    return 0


def _cmd_from_starmap_fixture(args: argparse.Namespace) -> int:
    out_root = _resolve_out_root(args.out)
    candidates = import_from_starmap_fixture(args.fixture)
    batch = _build_and_write(candidates, out_root)
    _print_batch_summary(batch)
    return 0


def _cmd_live_trendshift_scan(args: argparse.Namespace) -> int:
    if not args.allow_live_network:
        print("FAILED: --allow-live-network is required for a live Trendshift scan", file=sys.stderr)
        return 2
    out_root = _resolve_out_root(args.out)
    try:
        candidates = import_from_trendshift_live_scan(timeframes=args.timeframe or ["daily"])
    except TrendshiftLiveScanError as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        return 1
    if not candidates:
        print("FAILED: live Trendshift scan returned no parseable candidates", file=sys.stderr)
        return 1
    batch = _build_and_write(candidates, out_root)
    _print_batch_summary(batch)
    return 0


def _cmd_plan(args: argparse.Namespace) -> int:
    out_root = _resolve_out_root(args.out)
    batch = OpenSourceLeverageBatchV1.from_json(Path(args.batch).read_text(encoding="utf-8"))
    plan = plan_oss_integrations_from_opportunities(batch, max_selected=args.max_selected)
    plan.write_json(out_root / "OpenSourceIntegrationPlan.json")
    print(json.dumps(
        {
            "plan_id": plan.plan_id, "batch_id": plan.batch_id,
            "immediate_adapter_candidates": len(plan.immediate_adapter_candidates),
            "architecture_emulation_candidates": len(plan.architecture_emulation_candidates),
            "documentation_reference_candidates": len(plan.documentation_reference_candidates),
            "license_review_queue": len(plan.license_review_queue),
            "proposed_next_prs": plan.proposed_next_prs,
        },
        indent=2,
    ))
    return 0


def _cmd_render(args: argparse.Namespace) -> int:
    out_root = _resolve_out_root(args.out)
    batch = OpenSourceLeverageBatchV1.from_json(Path(args.batch).read_text(encoding="utf-8"))
    plan = OpenSourceIntegrationPlanV1.from_json(Path(args.plan).read_text(encoding="utf-8")) if args.plan else None
    written = write_oss_opportunity_summary(
        batch, plan, out_root, write_html=not args.no_html,
        reproducibility_commands=[
            f"python -m oss_opportunities.export_oss_opportunities render --batch {args.batch} "
            + (f"--plan {args.plan} " if args.plan else "") + f"--out {args.out}"
        ],
    )
    print(json.dumps({k: str(v) for k, v in written.items()}, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("from-manual-seed")
    p.add_argument("--seed", required=True)
    p.add_argument("--out", required=True)
    p.set_defaults(func=_cmd_from_manual_seed)

    p = sub.add_parser("from-trendshift-fixture")
    p.add_argument("--fixture", required=True)
    p.add_argument("--out", required=True)
    p.set_defaults(func=_cmd_from_trendshift_fixture)

    p = sub.add_parser("from-starmap-fixture")
    p.add_argument("--fixture", required=True)
    p.add_argument("--out", required=True)
    p.set_defaults(func=_cmd_from_starmap_fixture)

    p = sub.add_parser("live-trendshift-scan")
    p.add_argument("--timeframe", action="append", choices=["daily", "weekly", "monthly", "yearly"])
    p.add_argument("--out", required=True)
    p.add_argument("--allow-live-network", action="store_true")
    p.set_defaults(func=_cmd_live_trendshift_scan)

    p = sub.add_parser("plan")
    p.add_argument("--batch", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--max-selected", type=int, default=20)
    p.set_defaults(func=_cmd_plan)

    p = sub.add_parser("render")
    p.add_argument("--batch", required=True)
    p.add_argument("--plan")
    p.add_argument("--out", required=True)
    p.add_argument("--no-html", action="store_true")
    p.set_defaults(func=_cmd_render)

    return parser


def main(argv: list[str] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (OssOpportunityStoreError, FileNotFoundError, ValueError) as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
