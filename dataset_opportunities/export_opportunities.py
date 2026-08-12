"""CLI for the dataset opportunity scout pipeline.

    python -m dataset_opportunities.export_opportunities from-candidates \
        --candidates outputs/dataset_importers/candidates.json --out outputs/dataset_opportunities/batch1

    python -m dataset_opportunities.export_opportunities from-eegdash-fixture \
        --fixture tests/fixtures/eegdash_datasets.json --out outputs/dataset_opportunities/batch1

    python -m dataset_opportunities.export_opportunities eegdash-metadata-query \
        --query '{"tasks": ["rest"]}' --out outputs/dataset_opportunities/batch1 --allow-live-metadata-query

    python -m dataset_opportunities.export_opportunities plan \
        --batch outputs/dataset_opportunities/batch1/DatasetOpportunityBatch.json \
        --out outputs/dataset_opportunities/batch1 --max-selected 10

    python -m dataset_opportunities.export_opportunities render \
        --batch outputs/dataset_opportunities/batch1/DatasetOpportunityBatch.json \
        --plan outputs/dataset_opportunities/batch1/DatasetOpportunityPlan.json \
        --out outputs/dataset_opportunities/batch1/summary.md

No subcommand ever downloads raw dataset content, extracts features, or runs
a report/benchmark pipeline -- this CLI is metadata-scouting-and-planning
only. `eegdash-metadata-query` performs zero network I/O unless
`--allow-live-metadata-query` is explicitly passed.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from dataset_importers.candidate_record import DatasetCandidateRecordV1
from dataset_importers.eegdash_importer import EegdashImporterUnavailable, import_eegdash_candidates
from dataset_opportunities.opportunity_batch import DatasetOpportunityBatchV1, build_opportunities_from_candidates
from dataset_opportunities.planner import DatasetOpportunityPlanV1, plan_next_actions_from_opportunities
from dataset_opportunities.renderer import write_opportunity_summary
from dataset_opportunities.validation import DatasetOpportunityStoreError, validate_repo_relative_root

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _resolve_out_root(raw: str) -> Path:
    errors = validate_repo_relative_root(raw, "out")
    if errors:
        raise DatasetOpportunityStoreError("; ".join(errors))
    return (_REPO_ROOT / raw).resolve()


def _load_candidates_json(path: Path) -> list[DatasetCandidateRecordV1]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    entries = payload.get("candidates") if isinstance(payload, dict) else payload
    return [DatasetCandidateRecordV1.from_dict(e) for e in entries]


def _build_and_write(candidates: list[DatasetCandidateRecordV1], out_root: Path, query_summary: str) -> DatasetOpportunityBatchV1:
    if not candidates:
        raise DatasetOpportunityStoreError("no candidates provided -- nothing to score")
    batch = build_opportunities_from_candidates(candidates, query_summary=query_summary)
    batch.write_json(out_root / "DatasetOpportunityBatch.json")
    return batch


def _cmd_from_candidates(args: argparse.Namespace) -> int:
    out_root = _resolve_out_root(args.out)
    candidates = _load_candidates_json(Path(args.candidates))
    batch = _build_and_write(candidates, out_root, query_summary=f"candidates file: {args.candidates}")
    _print_batch_summary(batch)
    return 0


def _cmd_from_eegdash_fixture(args: argparse.Namespace) -> int:
    out_root = _resolve_out_root(args.out)
    candidates = import_eegdash_candidates(fixture_path=args.fixture)
    batch = _build_and_write(candidates, out_root, query_summary=f"eegdash fixture: {args.fixture}")
    _print_batch_summary(batch)
    return 0


def _cmd_eegdash_metadata_query(args: argparse.Namespace) -> int:
    if not args.allow_live_metadata_query:
        print("FAILED: --allow-live-metadata-query is required for a live eegdash metadata query", file=sys.stderr)
        return 2
    out_root = _resolve_out_root(args.out)
    query: dict[str, Any] = json.loads(Path(args.query).read_text(encoding="utf-8")) if args.query else {}
    try:
        candidates = import_eegdash_candidates(live_query=True, query=query, limit=args.limit)
    except EegdashImporterUnavailable as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        return 1
    batch = _build_and_write(candidates, out_root, query_summary=f"eegdash live query: {query}")
    _print_batch_summary(batch)
    return 0


def _cmd_plan(args: argparse.Namespace) -> int:
    out_root = _resolve_out_root(args.out)
    batch = DatasetOpportunityBatchV1.from_json(Path(args.batch).read_text(encoding="utf-8"))
    plan = plan_next_actions_from_opportunities(batch, max_selected=args.max_selected)
    plan.write_json(out_root / "DatasetOpportunityPlan.json")
    print(json.dumps(plan.to_dict(), indent=2))
    return 0


def _cmd_render(args: argparse.Namespace) -> int:
    batch = DatasetOpportunityBatchV1.from_json(Path(args.batch).read_text(encoding="utf-8"))
    plan = DatasetOpportunityPlanV1.from_json(Path(args.plan).read_text(encoding="utf-8")) if args.plan else None
    out_path = Path(args.out)
    errors = validate_repo_relative_root(str(out_path.parent) if out_path.parent != Path(".") else "outputs", "out")
    write_opportunity_summary(batch, plan, out_path, reproducibility_commands=[
        f"python -m dataset_opportunities.export_opportunities render --batch {args.batch} "
        + (f"--plan {args.plan} " if args.plan else "") + f"--out {args.out}"
    ])
    print(json.dumps({"summary_path": str(out_path)}, indent=2))
    return 0


def _print_batch_summary(batch: DatasetOpportunityBatchV1) -> None:
    print(json.dumps(
        {
            "batch_id": batch.batch_id,
            "total_candidates_seen": batch.total_candidates_seen,
            "total_opportunities_ranked": batch.total_opportunities_ranked,
            "total_rejected": len(batch.rejected_opportunities),
            "top_recommended_actions": batch.top_recommended_actions,
        },
        indent=2,
    ))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("from-candidates")
    p.add_argument("--candidates", required=True)
    p.add_argument("--out", required=True)
    p.set_defaults(func=_cmd_from_candidates)

    p = sub.add_parser("from-eegdash-fixture")
    p.add_argument("--fixture", required=True)
    p.add_argument("--out", required=True)
    p.set_defaults(func=_cmd_from_eegdash_fixture)

    p = sub.add_parser("eegdash-metadata-query")
    p.add_argument("--query")
    p.add_argument("--out", required=True)
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--allow-live-metadata-query", action="store_true")
    p.set_defaults(func=_cmd_eegdash_metadata_query)

    p = sub.add_parser("plan")
    p.add_argument("--batch", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--max-selected", type=int, default=10)
    p.set_defaults(func=_cmd_plan)

    p = sub.add_parser("render")
    p.add_argument("--batch", required=True)
    p.add_argument("--plan")
    p.add_argument("--out", required=True)
    p.set_defaults(func=_cmd_render)

    return parser


def main(argv: list[str] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (DatasetOpportunityStoreError, FileNotFoundError, ValueError) as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
