"""Catalog schema, required step order, and inventory probes."""

from __future__ import annotations

from ops.research_cycle.catalog import load_catalog
from ops.research_cycle.validate_pack import REQUIRED_STEP_IDS, validate_catalog_document

from tests.ops.research_cycle.conftest import CATALOG, REPO_ROOT


def test_catalog_document_valid():
    report = validate_catalog_document(CATALOG)
    assert report["ok"] is True, report["errors"]
    assert report["step_count"] == len(REQUIRED_STEP_IDS)


def test_required_step_order_is_strictly_increasing():
    catalog = load_catalog(CATALOG)
    ids = [step.id for step in catalog.steps]
    assert ids == list(REQUIRED_STEP_IDS)
    orders = [step.order for step in catalog.steps]
    assert orders == sorted(orders)
    assert orders == list(range(1, 12))


def test_catalog_wraps_existing_clis_not_invented_runners():
    catalog = load_catalog(CATALOG)
    wraps = {step.id: list(step.wraps) for step in catalog.steps}
    assert any("validate_research_cycle.py" in item for item in wraps["research_plan_audit"])
    assert any("validate_research_claims.py" in item for item in wraps["claim_gate"])
    assert any("validate_empirical_source_manifest.py" in item for item in wraps["artifact_manifest"])
    assert any("compile_research_state.py" in item for item in wraps["evidence_graph"])
    assert any("dataset_acquisition.export_plan" in item for item in wraps["cache_policy"])
    assert any("run_benchmark_matrix.py" in item for item in wraps["simulation_campaign"])
    assert any("evaluate_performance_release_evidence.py" in item for item in wraps["release_evidence"])
    joined = " ".join(str(part) for argv in (step.argv_template for step in catalog.steps) for part in argv)
    assert "run_tests_isolated" not in joined
    assert "run_research_campaign.py" not in joined


def test_simulation_campaign_is_dry_run_by_default():
    catalog = load_catalog(CATALOG)
    step = catalog.step_by_id("simulation_campaign")
    assert step is not None
    assert "--dry-run" in step.argv_template
    assert step.solver is False


def test_every_step_has_positive_timeout():
    catalog = load_catalog(CATALOG)
    for step in catalog.all_steps(include_optional=True):
        assert step.timeout_s > 0, step.id
        assert step.network is False


def test_targeted_tests_use_existing_fixed_list():
    catalog = load_catalog(CATALOG)
    step = catalog.step_by_id("targeted_tests")
    assert step is not None
    argv = " ".join(step.argv_template)
    assert "tests/research_cycle/test_experiment_planners_and_serialization.py" in argv
    assert "tests/research_claims/test_research_claim_auditor.py" in argv
    assert "tests/release/test_validate_release_blockers_cli.py" in argv
    assert "tests/runner" not in argv
    for rel in (
        "tests/research_cycle/test_experiment_planners_and_serialization.py",
        "tests/research_claims/test_research_claim_auditor.py",
        "tests/release/test_validate_release_blockers_cli.py",
    ):
        assert (REPO_ROOT / rel).is_file()
