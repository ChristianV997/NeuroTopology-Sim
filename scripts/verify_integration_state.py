"""Read-only authoritative integration-state verifier CLI.

Never mutates the repository or any remote: every git call is read-only,
and GitHub-side facts come only from an optional pre-fetched JSON
snapshot this script reads, never fetches itself.

Usage::

    python scripts/verify_integration_state.py \\
        --repo-path . --integration-branch origin/codex/integration-all-open-prs \\
        --main-ref origin/main \\
        --pr-snapshot /path/to/pr_snapshot.json \\
        --handoff-claim "round1=3b36cb5..." --handoff-claim "round2=be277ecd..." \\
        --output-dir /tmp/state_lock
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from tools.integration_state import github_source, reporting, state  # noqa: E402


def _parse_handoff_claim(raw: str) -> tuple[str, str]:
    label, _, commit = raw.partition("=")
    if not commit:
        raise argparse.ArgumentTypeError(f"--handoff-claim must be LABEL=COMMIT, got {raw!r}")
    return label, commit


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-path", type=Path, default=Path("."))
    parser.add_argument("--integration-branch", required=True)
    parser.add_argument("--main-ref", default="origin/main")
    parser.add_argument("--local-worktree-ref", default="HEAD")
    parser.add_argument("--pr-snapshot", type=Path, default=None)
    parser.add_argument("--handoff-claim", action="append", default=[], metavar="LABEL=COMMIT")
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args(argv)

    pr_snapshot = None
    if args.pr_snapshot is not None:
        pr_snapshot = github_source.load_pr_snapshot_from_file(args.pr_snapshot)

    handoff_claims = dict(_parse_handoff_claim(raw) for raw in args.handoff_claim)

    report = state.build_state_lock_report(
        repo_path=args.repo_path,
        integration_branch_ref=args.integration_branch,
        main_ref=args.main_ref,
        local_worktree_ref=args.local_worktree_ref,
        pr_snapshot=pr_snapshot,
        handoff_claims=handoff_claims,
    )

    json_text = reporting.to_json(report)
    markdown_text = reporting.to_markdown(report)

    if args.output_dir is not None:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        (args.output_dir / "report.json").write_text(json_text + "\n", encoding="utf-8")
        (args.output_dir / "report.md").write_text(markdown_text, encoding="utf-8")
    else:
        print(json_text)

    return 1 if report.contradictory_handoffs else 0


if __name__ == "__main__":
    raise SystemExit(main())
