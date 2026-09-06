"""The registry of expected work orders this reconciliation tracks.

Kept as plain Python data (not a config file) because this tool has no
ownership over any `configs/**` path -- this registry lives entirely
inside tools/integration_reconciliation/**, which this branch does own.
`default_registry()` encodes the exact "known open work" the coordinator
described; callers (including all unit tests) may pass their own
``tuple[WorkOrder, ...]`` instead, so nothing here is hardwired into the
matching logic itself.
"""
from __future__ import annotations

from .models import WorkOrder


def default_registry() -> tuple[WorkOrder, ...]:
    return (
        WorkOrder(
            work_order_id="ecosystem-integration-scaffold",
            description="PR #210: ecosystem integration scaffold",
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
            description="PR #212: signal interoperability",
            expected_branch="codex/interop-signal-contracts",
            reported_pr_number=212,
        ),
        WorkOrder(
            work_order_id="scientific-falsification-contract",
            description=(
                "scientific-falsification-contract branch reported pushed "
                "but PR creation previously failed"
            ),
            expected_branch="codex/scientific-falsification-contract",
            reported_pr_number=None,
            reported_status_note="PR creation previously failed (as reported)",
        ),
        WorkOrder(
            work_order_id="antigravity-mne-scipy-streaming-eeg",
            description="Antigravity branch report (previously incomplete/unavailable)",
            expected_branch="antigravity/mne-scipy-streaming-eeg",
            reported_pr_number=None,
            reported_status_note="reported incomplete/unavailable at time of assignment",
        ),
        WorkOrder(
            work_order_id="antigravity-test-isolation-dependency-profiles",
            description="Antigravity branch report (previously incomplete/unavailable)",
            expected_branch="antigravity/test-isolation-dependency-profiles",
            reported_pr_number=None,
            reported_status_note="reported incomplete/unavailable at time of assignment",
        ),
        WorkOrder(
            work_order_id="grok-tool-admission-research",
            description="Grok branch report (previously incomplete/unavailable)",
            expected_branch="grok/tool-admission-research",
            reported_pr_number=None,
            reported_status_note="reported incomplete/unavailable at time of assignment",
        ),
        WorkOrder(
            work_order_id="grok-bot-retrofit-inventory",
            description="Grok-bot branch report (previously incomplete/unavailable)",
            expected_branch="grok-bot/retrofit-inventory",
            reported_pr_number=None,
            reported_status_note="reported incomplete/unavailable at time of assignment",
        ),
    )
