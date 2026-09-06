from __future__ import annotations

from tools.integration_reconciliation import work_orders


def test_default_registry_has_twelve_entries():
    """10 PRs with a known number (#209, #210, #211, #212, #213, #214,
    #215, #217, #219, #222) + the scientific-falsification-contract branch
    + the grok/tool-admission-research branch report = 12 work orders."""
    registry = work_orders.default_registry()
    assert len(registry) == 12


def test_default_registry_work_order_ids_are_unique():
    registry = work_orders.default_registry()
    ids = [entry.work_order_id for entry in registry]
    assert len(ids) == len(set(ids))


def test_default_registry_known_branches_present():
    registry = work_orders.default_registry()
    branches = {entry.expected_branch for entry in registry}
    assert branches == {
        "grok-bot/retrofit-inventory",
        "claude/ecosystem-integration",
        "cursor/streaming-performance-benchmarks",
        "codex/interop-signal-contracts",
        "antigravity/test-isolation-dependency-profiles",
        "antigravity/mne-scipy-streaming-eeg",
        "cursor/rss-memory-telemetry",
        "grok/tool-registry-admission",
        "codex/bayes-falsification-hardening",
        "codex/ci-root-cause-and-green",
        "codex/scientific-falsification-contract",
        "grok/tool-admission-research",
    }


def test_scientific_falsification_contract_has_no_reported_pr():
    registry = work_orders.default_registry()
    entry = next(e for e in registry if e.work_order_id == "scientific-falsification-contract")
    assert entry.reported_pr_number is None
    assert "PR creation" in entry.reported_status_note


def test_grok_tool_admission_research_has_no_reported_pr():
    registry = work_orders.default_registry()
    entry = next(e for e in registry if e.work_order_id == "grok-tool-admission-research")
    assert entry.reported_pr_number is None


def test_reported_prs_match_known_open_work():
    registry = work_orders.default_registry()
    reported = {
        e.work_order_id: e.reported_pr_number
        for e in registry
        if e.reported_pr_number is not None
    }
    assert reported == {
        "retrofit-inventory": 209,
        "ecosystem-integration-scaffold": 210,
        "streaming-performance": 211,
        "signal-interoperability": 212,
        "test-isolation-dependency-profiles": 213,
        "mne-scipy-streaming-eeg": 214,
        "process-memory-telemetry": 215,
        "tooling-capability-registry": 217,
        "bayesian-hardening": 219,
        "ci-test-infrastructure": 222,
    }
