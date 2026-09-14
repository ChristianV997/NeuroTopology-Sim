"""Read-only reconciliation CLI: git branch facts + an optional GitHub
metadata snapshot -> strict JSON + Markdown report.

This script never mutates the repository or any remote: it contains no
`git push`, `merge`, `rebase`, `checkout -b`, or branch-deletion call
anywhere in its call graph. See docs/integration_reconciliation/ for the
report schema and how to produce a `--github-snapshot` file.

Usage::

    python scripts/verify_integration_reconciliation.py \\
        --repo-path . --target-ref origin/main \\
        --github-snapshot /path/to/snapshot.json \\
        --dashboard-src apps/awareness_studio/src \\
        --output-dir /tmp/reconciliation

By default this reconciles the hand-curated `work_orders.default_registry()`
list (a fixed set of historical PRs). Pass `--work-orders-from-snapshot` to
instead reconcile every PR present in `--github-snapshot` (required together
with that flag) -- use this to audit the current PR pile as a whole rather
than a pre-selected list of known branches.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from tools.integration_reconciliation import github_source, reconcile, reporting, work_orders  # noqa: E402


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-path", type=Path, default=Path("."))
    parser.add_argument("--target-ref", default="origin/main")
    parser.add_argument("--github-snapshot", type=Path, default=None)
    parser.add_argument("--dashboard-src", type=Path, default=Path("apps/awareness_studio/src"))
    parser.add_argument("--output-dir", type=Path, default=None, help="write report.json/report.md here")
    parser.add_argument(
        "--work-orders-from-snapshot",
        action="store_true",
        help="reconcile every PR in --github-snapshot instead of work_orders.default_registry()",
    )
    args = parser.parse_args(argv)

    if args.work_orders_from_snapshot and args.github_snapshot is None:
        parser.error("--work-orders-from-snapshot requires --github-snapshot")

    snapshot = None
    if args.github_snapshot is not None:
        snapshot = github_source.load_snapshot_from_file(args.github_snapshot)

    selected_work_orders = (
        work_orders.work_orders_from_snapshot(snapshot)
        if args.work_orders_from_snapshot
        else work_orders.default_registry()
    )

    report = reconcile.reconcile(
        repo_path=args.repo_path,
        work_orders=selected_work_orders,
        target_ref=args.target_ref,
        github_snapshot=snapshot,
        dashboard_src=args.dashboard_src,
    )

    json_text = reporting.to_json(report)
    markdown_text = reporting.to_markdown(report)

    if args.output_dir is not None:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        (args.output_dir / "report.json").write_text(json_text + "\n", encoding="utf-8")
        (args.output_dir / "report.md").write_text(markdown_text, encoding="utf-8")
    else:
        print(json_text)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
