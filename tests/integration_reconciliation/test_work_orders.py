from __future__ import annotations

from tools.integration_reconciliation import work_orders


def test_default_registry_has_eight_entries():
    """3 PRs with a known number + the reported scientific-falsification-contract
    branch + 4 antigravity/grok branch reports = 8 work orders total."""
    registry = work_orders.default_registry()
    assert len(registry) == 8


def test_default_registry_work_order_ids_are_unique():
    registry = work_orders.default_registry()
    ids = [entry.work_order_id for entry in registry]
    assert len(ids) == len(set(ids))


def test_default_registry_known_branches_present():
    registry = work_orders.default_registry()
    branches = {entry.expected_branch for entry in registry}
    assert branches == {
        "claude/ecosystem-integration",
        "cursor/streaming-performance-benchmarks",
        "codex/interop-signal-contracts",
        "codex/scientific-falsification-contract",
        "antigravity/mne-scipy-streaming-eeg",
        "antigravity/test-isolation-dependency-profiles",
        "grok/tool-admission-research",
        "grok-bot/retrofit-inventory",
    }


def test_scientific_falsification_contract_has_no_reported_pr():
    registry = work_orders.default_registry()
    entry = next(e for e in registry if e.work_order_id == "scientific-falsification-contract")
    assert entry.reported_pr_number is None
    assert "PR creation" in entry.reported_status_note


def test_reported_prs_match_known_open_work():
    registry = work_orders.default_registry()
    reported = {
        e.work_order_id: e.reported_pr_number
        for e in registry
        if e.reported_pr_number is not None
    }
    assert reported == {
        "ecosystem-integration-scaffold": 210,
        "streaming-performance": 211,
        "signal-interoperability": 212,
    }
