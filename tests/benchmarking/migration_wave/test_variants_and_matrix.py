"""Read-only PR capability matrix and same-surface comparison rules."""
from __future__ import annotations

from pathlib import Path

from tools.benchmarking.migration_wave.schema import VARIANT_NAMES
from tools.benchmarking.migration_wave.variants import detect_capabilities, inventory_variants, resolve_variant_root

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_inventory_includes_all_variants():
    rows = inventory_variants(REPO_ROOT)
    names = {row["variant"] for row in rows}
    assert names == set(VARIANT_NAMES)
    main = next(row for row in rows if row["variant"] == "current_main")
    assert main["available"] is True
    assert main["capabilities"]["chunk_cache"] is True
    assert main["inspected_read_only"] is True


def test_pr_trees_detected_when_present():
    rows = {row["variant"]: row for row in inventory_variants(REPO_ROOT)}
    for name in ("pr_331", "pr_344", "pr_345", "pr_346"):
        root = resolve_variant_root(name, harness_root=REPO_ROOT)
        if root is None:
            continue
        caps = detect_capabilities(root)
        if name == "pr_331":
            assert caps["approved_adapter"] is True
            assert caps["fetch_plan"] is False
        if name == "pr_344":
            assert caps["fetch_plan"] is True
        if name == "pr_345":
            assert caps["dandi_window"] is True
        if name == "pr_346":
            assert caps["bounded_s3"] is True


def test_current_main_has_migrated_openneuro_and_dandi():
    caps = detect_capabilities(REPO_ROOT)
    assert caps["fetch_plan"] is True
    assert caps["dandi_window"] is True
    assert caps["bounded_s3"] is False
    assert caps["approved_adapter"] is False
