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

from .models import WorkOrder


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
