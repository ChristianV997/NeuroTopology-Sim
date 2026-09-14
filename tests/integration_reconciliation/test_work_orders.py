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


def test_work_orders_from_snapshot_builds_one_per_pr():
    snapshot = {
        "schema": "NTS.GitHubReconciliationSnapshot.v1",
        "pull_requests": [
            {"number": 100, "head_ref": "claude/foo", "title": "Add foo"},
            {"number": 101, "head_ref": "codex/bar", "title": "Add bar"},
        ],
    }
    orders = work_orders.work_orders_from_snapshot(snapshot)
    assert len(orders) == 2
    assert {o.work_order_id for o in orders} == {"pr-100", "pr-101"}
    assert {o.expected_branch for o in orders} == {"claude/foo", "codex/bar"}
    assert {o.reported_pr_number for o in orders} == {100, 101}


def test_work_orders_from_snapshot_ids_are_unique_and_stable():
    snapshot = {
        "pull_requests": [
            {"number": 5, "head_ref": "a/b"},
            {"number": 6, "head_ref": "c/d"},
        ],
    }
    orders = work_orders.work_orders_from_snapshot(snapshot)
    ids = [o.work_order_id for o in orders]
    assert ids == ["pr-5", "pr-6"]
    assert len(ids) == len(set(ids))


def test_work_orders_from_snapshot_skips_entries_with_no_head_ref():
    snapshot = {
        "pull_requests": [
            {"number": 7, "head_ref": "has/branch"},
            {"number": 8},
        ],
    }
    orders = work_orders.work_orders_from_snapshot(snapshot)
    assert len(orders) == 1
    assert orders[0].reported_pr_number == 7


def test_work_orders_from_snapshot_empty_pull_requests_yields_empty_tuple():
    assert work_orders.work_orders_from_snapshot({"pull_requests": []}) == ()
