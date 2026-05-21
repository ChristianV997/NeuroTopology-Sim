"""Generate stale PR reconciliation artifacts from manual PR JSON fixtures."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class PRAuditRecord:
    pr_number: int
    branch: str
    mergeability: str
    changed_files: int
    additions: int
    deletions: int
    status: str
    unique_commits_vs_main: bool | None
    superseded_by_pr: int | None = None


def _normalize_mergeability(value: Any) -> str:
    if value is True:
        return "mergeable"
    if value is False:
        return "conflicting"
    if value is None:
        return "unknown"
    return str(value)


def recommended_action(record: PRAuditRecord) -> str:
    if record.status == "closed":
        return "no_action_closed"

    if record.superseded_by_pr is not None:
        return f"close_as_superseded_by_pr_{record.superseded_by_pr}"

    if (
        record.changed_files == 0
        and record.additions == 0
        and record.deletions == 0
        and record.unique_commits_vs_main is False
    ):
        return "close_as_noop_superseded_by_main"

    if record.unique_commits_vs_main is True:
        return "keep_open_has_unique_commits"

    return "manual_review_required"


def evaluate(records: list[PRAuditRecord]) -> list[dict[str, Any]]:
    evaluated: list[dict[str, Any]] = []
    for record in records:
        evaluated.append(
            {
                "pr_number": record.pr_number,
                "branch": record.branch,
                "mergeability": record.mergeability,
                "changed_files": record.changed_files,
                "additions": record.additions,
                "deletions": record.deletions,
                "status": record.status,
                "unique_commits_vs_main": record.unique_commits_vs_main,
                "superseded_by_pr": record.superseded_by_pr,
                "recommended_action": recommended_action(record),
            }
        )
    return evaluated


def load_records(fixture_path: Path) -> list[PRAuditRecord]:
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    records: list[PRAuditRecord] = []
    for item in payload["pull_requests"]:
        records.append(
            PRAuditRecord(
                pr_number=int(item["pr_number"]),
                branch=str(item["branch"]),
                mergeability=_normalize_mergeability(item.get("mergeability")),
                changed_files=int(item["changed_files"]),
                additions=int(item["additions"]),
                deletions=int(item["deletions"]),
                status=str(item["status"]),
                unique_commits_vs_main=item.get("unique_commits_vs_main"),
                superseded_by_pr=item.get("superseded_by_pr"),
            )
        )
    return records


def write_json(path: Path, evaluated: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"pull_requests": evaluated}, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    records = load_records(args.fixture)
    write_json(args.out, evaluate(records))


if __name__ == "__main__":
    main()
