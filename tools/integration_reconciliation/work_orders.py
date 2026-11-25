"""The registry of expected work orders this reconciliation tracks.

Kept as plain Python data (not a config file) because this tool has no
ownership over any `configs/**` path -- this registry lives entirely
inside tools/integration_reconciliation/**, which this branch does own.
`default_registry()` encodes the "known open work" the coordinator has
described across this reconciliation effort's two rounds so far; callers
(including all unit tests) may pass their own ``tuple[WorkOrder, ...]``
instead, so nothing here is hardwired into the matching logic itself.

Updated for round 2 (PR #218 continuation): PR numbers for the three
"antigravity"/"grok-bot" branches that PR #218's own dry-run found were
stale-reported as "incomplete/unavailable" are now confirmed
(#213/#214/#209); four new work orders (#215, #217, #219, #222) were
added per the coordinator's updated "known open work" list.
"""
from __future__ import annotations

from typing import Any

from .models import WorkOrder


def work_orders_from_snapshot(snapshot: dict[str, Any]) -> tuple[WorkOrder, ...]:
    """Build one WorkOrder per PR entry in a GitHub snapshot.

    `default_registry()` is a hand-curated list of specific historical PRs
    and goes stale as soon as those PRs close and new ones open (as
    happened between this tool's two rounds and the current, much larger
    PR pile). This is the alternative for "reconcile whatever is actually
    open right now": every `pull_requests` entry in the snapshot becomes
    its own work order, keyed by PR number, with no hand-maintained list
    to fall out of sync. Entries missing a `head_ref` are skipped (a
    work order with no `expected_branch` can't be matched against git
    facts at all, so it would only ever surface as manual-review noise).
    """
    orders: list[WorkOrder] = []
    for pr in snapshot.get("pull_requests", []):
        head_ref = pr.get("head_ref")
        if not head_ref:
            continue
        number = pr.get("number")
        title = pr.get("title") or head_ref
        orders.append(
            WorkOrder(
                work_order_id=f"pr-{number}" if number is not None else head_ref,
                description=f"PR #{number}: {title}" if number is not None else str(title),
                expected_branch=head_ref,
                reported_pr_number=number,
            )
        )
    return tuple(orders)


def default_registry() -> tuple[WorkOrder, ...]:
    return (
        WorkOrder(
            work_order_id="retrofit-inventory",
            description="PR #209: retrofit inventory",
            expected_branch="grok-bot/retrofit-inventory",
            reported_pr_number=209,
        ),
        WorkOrder(
            work_order_id="ecosystem-integration-scaffold",
            description="PR #210: ecosystem scaffold",
            expected_branch="claude/ecosystem-integration",
            reported_pr_number=210,
        ),
        WorkOrder(
            work_order_id="streaming-performance",
            description="PR #211: streaming performance",
            expected_branch="cursor/streaming-performance-benchmarks",
            reported_pr_number=211,
        ),
        WorkOrder(
            work_order_id="signal-interoperability",
            description="PR #212: interoperability contracts",
            expected_branch="codex/interop-signal-contracts",
            reported_pr_number=212,
        ),
        WorkOrder(
            work_order_id="test-isolation-dependency-profiles",
            description="PR #213: dependency profiles",
            expected_branch="antigravity/test-isolation-dependency-profiles",
            reported_pr_number=213,
        ),
        WorkOrder(
            work_order_id="mne-scipy-streaming-eeg",
            description="PR #214: MNE/SciPy streaming EEG",
            expected_branch="antigravity/mne-scipy-streaming-eeg",
            reported_pr_number=214,
        ),
        WorkOrder(
            work_order_id="process-memory-telemetry",
            description="PR #215: process-memory telemetry",
            expected_branch="cursor/rss-memory-telemetry",
            reported_pr_number=215,
        ),
        WorkOrder(
            work_order_id="tooling-capability-registry",
            description="PR #217: tooling capability registry",
            expected_branch="grok/tool-registry-admission",
            reported_pr_number=217,
        ),
        WorkOrder(
            work_order_id="bayesian-hardening",
            description="PR #219: Bayesian hardening",
            expected_branch="codex/bayes-falsification-hardening",
            reported_pr_number=219,
        ),
        WorkOrder(
            work_order_id="ci-test-infrastructure",
            description="PR #222: CI/test infrastructure",
            expected_branch="codex/ci-root-cause-and-green",
            reported_pr_number=222,
        ),
        WorkOrder(
            work_order_id="scientific-falsification-contract",
            description=(
                "scientific-falsification-contract branch reported pushed "
                "but PR creation previously failed"
            ),
            expected_branch="codex/scientific-falsification-contract",
            reported_pr_number=None,
            reported_status_note="PR creation previously failed (as reported); still no confirmed PR",
        ),
        WorkOrder(
            work_order_id="grok-tool-admission-research",
            description=(
                "Grok branch report (previously incomplete/unavailable); note "
                "grok/tool-registry-admission (PR #217) and "
                "grok/tool-capability-snapshot are separate branches, not this one"
            ),
            expected_branch="grok/tool-admission-research",
            reported_pr_number=None,
            reported_status_note="reported incomplete/unavailable; still no confirmed PR",
        ),
    )
