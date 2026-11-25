"""Tests for tools/awareness_studio_research_loop/contract_adapters.py
against fixtures shaped like the *real* upstream registries (PR #276's
tools/awareness_studio_research/models.py, and the already-merged
tools/research_cycle/schema.py).
"""
from __future__ import annotations

import ast
import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from tools.awareness_studio_research_loop import contract_adapters as ca

_REPO_ROOT = Path(__file__).resolve().parents[2]
_FIXTURES_DIR = _REPO_ROOT / "fixtures" / "awareness_studio_research_loop" / "integration_contracts"


def _load_fixture(name: str) -> dict:
    return json.loads((_FIXTURES_DIR / name).read_text(encoding="utf-8"))


@pytest.fixture
def literature_export():
    return _load_fixture("literature_registry_export_sample.json")


@pytest.fixture
def hypothesis_registry():
    return _load_fixture("hypothesis_registry_sample.json")


@pytest.fixture
def experiment_plans():
    return _load_fixture("experiment_plans_sample.json")


@pytest.fixture
def experiment_evidence_updates():
    return _load_fixture("experiment_evidence_updates_sample.json")


# --- complete integration ---------------------------------------------------


def test_complete_integration_adapts_all_real_fixture_shapes(literature_export, hypothesis_registry, experiment_plans, experiment_evidence_updates):
    lit_bundle, lit_diagnostics = ca.adapt_literature_evidence_bundle(literature_export)
    assert len(lit_bundle["sources"]) == 2
    assert len(lit_bundle["claims"]) == 2
    assert len(lit_bundle["hypothesis_links"]) == 1
    assert not any(d.kind == ca.MISSING_FIELD for d in lit_diagnostics)

    hyp_bundle, hyp_diagnostics = ca.adapt_hypothesis_registry_bundle(hypothesis_registry)
    assert len(hyp_bundle["hypotheses"]) == 2
    ready_hyp = next(h for h in hyp_bundle["hypotheses"] if h["hypothesis_id"] == "HYP-DECENTERING-QZ-001")
    assert ready_hyp["null_prediction"]
    assert ready_hyp["falsification_criterion"]
    assert ready_hyp["claim_ids"] == []  # confirmed gap -- see test below

    plan_results = [ca.adapt_experiment_plan(p) for p in experiment_plans["plans"]]
    assert all(r.ok for r in plan_results)
    ready_plan = next(r.record for r in plan_results if r.record["experiment_id"] == "PLAN-DECENTERING-QZ-001")
    assert ready_plan["dataset_checksum"] == "data_sha_ds123"
    assert ready_plan["synthetic"] is False

    known_hypothesis_ids = {h["hypothesis_id"] for h in hyp_bundle["hypotheses"]}
    cross_diagnostics = ca.validate_cross_registry_hypothesis_links(claims=lit_bundle["claims"], hypothesis_links=lit_bundle["hypothesis_links"], known_hypothesis_ids=known_hypothesis_ids)
    assert cross_diagnostics == []  # the fixture's hypothesis_id is actually known


# --- missing source / disputed source ---------------------------------------


def test_claim_referencing_a_missing_source_bundle_still_adapts_other_records(literature_export):
    broken = copy.deepcopy(literature_export)
    broken["claims"][0]["source_id"] = None
    bundle, diagnostics = ca.adapt_literature_evidence_bundle(broken)
    assert len(bundle["claims"]) == 1  # the broken claim was dropped, not fabricated
    assert any(d.kind == ca.MISSING_FIELD and d.field == "source_id" for d in diagnostics)


def test_disputed_source_is_never_coerced_to_confirmed(literature_export):
    disputed_raw = literature_export["sources"][1]
    assert disputed_raw["verification_status"] == "disputed"

    result = ca.adapt_literature_source(disputed_raw)
    assert result.ok is True
    assert result.record["verification_status"] == "disputed"
    assert result.record["status"] == "disputed"
    assert result.record["evidence_tier"] == "T4_disputed"


def test_disputed_source_with_missing_checksum_is_flagged_not_dropped_silently():
    raw = {"source_id": "s-disputed", "source_checksum": "not-a-real-sha256", "verification_status": "disputed", "status": "disputed", "evidence_tier": "T4_disputed"}
    result = ca.adapt_literature_source(raw)
    assert result.ok is True
    assert any(d.kind == ca.UNVERIFIED_PROVENANCE and d.field == "source_checksum" for d in result.diagnostics)
    assert result.record["verification_status"] == "disputed"


# --- synthetic experiment ---------------------------------------------------


def test_synthetic_experiment_plan_is_flagged_and_never_reported_empirical(experiment_plans):
    synthetic_raw = experiment_plans["plans"][1]
    assert synthetic_raw["is_synthetic"] is True

    result = ca.adapt_experiment_plan(synthetic_raw)
    assert result.ok is True
    assert result.record["synthetic"] is True
    assert any(d.kind == ca.SYNTHETIC_ONLY_INPUT for d in result.diagnostics)


def test_synthetic_evidence_update_is_flagged(experiment_evidence_updates):
    synthetic_raw = experiment_evidence_updates["evidence_updates"][1]
    execution_result, null_test, contradiction = ca.adapt_experiment_evidence_update(synthetic_raw)
    assert execution_result.ok is True
    assert execution_result.record["data_mode"] == "synthetic"
    assert any(d.kind == ca.SYNTHETIC_ONLY_INPUT for d in execution_result.diagnostics)


# --- contradictory evidence --------------------------------------------------


def test_contradictory_evidence_update_is_surfaced(experiment_evidence_updates):
    raw = experiment_evidence_updates["evidence_updates"][1]
    assert raw["is_contradictory"] is True
    _, _, contradiction = ca.adapt_experiment_evidence_update(raw)
    assert contradiction is not None
    assert contradiction["hypothesis_id"] == "HYP-UNREVIEWED-002"
    assert "conflicts with" in contradiction["detail"]


def test_non_contradictory_evidence_update_has_no_contradiction_record(experiment_evidence_updates):
    raw = experiment_evidence_updates["evidence_updates"][0]
    assert raw["is_contradictory"] is False
    _, _, contradiction = ca.adapt_experiment_evidence_update(raw)
    assert contradiction is None


# --- invalid checksum --------------------------------------------------------


def test_experiment_plan_checksum_is_never_substituted_for_dataset_checksum():
    raw = {"plan_id": "P-X", "hypothesis_id": "H-X", "is_synthetic": False, "provenance": {}, "checksum": "plan-content-hash-not-dataset"}
    result = ca.adapt_experiment_plan(raw)
    assert result.ok is True
    assert result.record["dataset_checksum"] is None
    assert result.record["source_record_checksum"] == "plan-content-hash-not-dataset"
    assert any(d.kind == ca.MISSING_FIELD and d.field == "dataset_checksum" for d in result.diagnostics)


def test_source_checksum_wrong_length_is_flagged_unverified_not_rejected():
    raw = {"source_id": "s1", "source_checksum": "too-short-to-be-sha256"}
    result = ca.adapt_literature_source(raw)
    assert result.ok is True
    assert any(d.kind == ca.UNVERIFIED_PROVENANCE for d in result.diagnostics)


# --- missing human review ----------------------------------------------------


def test_missing_human_review_gate_field_is_a_diagnostic_not_a_default_approval():
    result = ca.adapt_human_review_gate({}, subject_id="H-X")
    assert result.ok is False
    assert any(d.kind == ca.MISSING_FIELD and d.field == "passed" for d in result.diagnostics)


def test_unreviewed_hypothesis_maps_to_pending_not_approved(hypothesis_registry):
    unreviewed = hypothesis_registry["hypotheses"][1]["human_review_gate"]
    assert unreviewed["passed"] is False
    result = ca.adapt_human_review_gate(unreviewed, subject_id="HYP-UNREVIEWED-002")
    assert result.ok is True
    assert result.record["decision"] == "pending"
    assert any(d.kind == ca.AMBIGUOUS_MAPPING for d in result.diagnostics)


def test_approved_hypothesis_maps_to_approved_unambiguously(hypothesis_registry):
    approved = hypothesis_registry["hypotheses"][0]["human_review_gate"]
    assert approved["passed"] is True
    result = ca.adapt_human_review_gate(approved, subject_id="HYP-DECENTERING-QZ-001")
    assert result.ok is True
    assert result.record["decision"] == "approved"
    assert not any(d.kind == ca.AMBIGUOUS_MAPPING for d in result.diagnostics)


# --- never-coerce guards -----------------------------------------------------


def test_never_coerce_list_has_exactly_the_five_required_entries():
    assert ca.NEVER_COERCE == ("formal_to_proxy", "empirical_to_synthetic", "theory_to_observation", "disputed_source_to_confirmed_source", "prediction_to_causal_effect")


def test_theoretical_claim_status_is_never_reported_as_empirical():
    raw = {"claim_id": "c1", "source_id": "s1", "claim_text": "A theoretical proposal.", "claim_status": "theoretical"}
    result = ca.adapt_extracted_claim(raw)
    assert result.ok is True
    assert result.record["claim_status"] == "theoretical"


def test_ledger_row_unknown_scientific_status_stays_unknown_not_promoted():
    raw = {"experiment_id": "E1", "scientific_status": "not-a-real-value"}
    result = ca.adapt_ledger_row(raw)
    assert result.ok is True
    assert result.record["scientific_status"] == "unknown"
    assert any(d.kind == ca.INCOMPATIBLE_TYPE for d in result.diagnostics)


# --- deterministic output -----------------------------------------------------


def test_adapting_the_same_fixture_twice_is_byte_identical(literature_export):
    bundle1, diagnostics1 = ca.adapt_literature_evidence_bundle(literature_export)
    bundle2, diagnostics2 = ca.adapt_literature_evidence_bundle(literature_export)
    assert json.dumps(bundle1, sort_keys=True) == json.dumps(bundle2, sort_keys=True)
    assert [d.to_dict() for d in diagnostics1] == [d.to_dict() for d in diagnostics2]


# --- ambiguous entity_type gap (a genuinely confirmed cross-registry finding) -


def test_evidence_update_entity_type_hypothesis_link_is_flagged_as_ambiguous(literature_export):
    hlink_update = next(u for u in literature_export["evidence_updates"] if u["entity_type"] == "hypothesis_link")
    result = ca.adapt_evidence_update(hlink_update)
    assert result.ok is True
    assert any(d.kind == ca.AMBIGUOUS_MAPPING and d.field == "entity_type" for d in result.diagnostics)


def test_evidence_update_entity_type_outside_registry_vocabulary_is_incompatible():
    result = ca.adapt_evidence_update({"update_id": "u1", "entity_type": "hypothesis", "entity_id": "h1"})
    # "hypothesis" is what the orchestrator wants but the real registry
    # never emits it -- so it is flagged as incompatible with the
    # registry's own vocabulary, not silently accepted.
    assert any(d.kind == ca.INCOMPATIBLE_TYPE and d.field == "entity_type" for d in result.diagnostics)


# --- finite-JSON checks -------------------------------------------------------


def test_non_finite_observed_p_value_is_nulled_not_left_as_nan_or_inf():
    raw = {"evidence_id": "e1", "experiment_id": "E1", "hypothesis_id": "H1", "observed_p_value": float("nan"), "is_contradictory": False}
    execution_result, null_test, _ = ca.adapt_experiment_evidence_update(raw)
    assert execution_result.ok is True
    assert null_test is not None
    assert null_test["statistic"] is None

    raw_inf = {"evidence_id": "e2", "experiment_id": "E2", "hypothesis_id": "H1", "observed_p_value": float("inf"), "is_contradictory": False}
    _, null_test_inf, _ = ca.adapt_experiment_evidence_update(raw_inf)
    assert null_test_inf["statistic"] is None


def test_full_validation_report_serializes_with_allow_nan_false(literature_export, hypothesis_registry, experiment_plans, experiment_evidence_updates):
    lit_bundle, lit_diagnostics = ca.adapt_literature_evidence_bundle(literature_export)
    hyp_bundle, hyp_diagnostics = ca.adapt_hypothesis_registry_bundle(hypothesis_registry)
    plan_results = [ca.adapt_experiment_plan(p) for p in experiment_plans["plans"]]
    report = {
        "literature_evidence": lit_bundle,
        "hypothesis_registry": hyp_bundle,
        "plans": [r.record for r in plan_results if r.ok],
        "diagnostics": [d.to_dict() for d in lit_diagnostics + hyp_diagnostics],
    }
    text = json.dumps(report, indent=2, sort_keys=True, allow_nan=False)
    assert "NaN" not in text
    assert "Infinity" not in text
    assert json.loads(text) == report


# --- no-heavy-import / no-network --------------------------------------------

_FORBIDDEN_TOP_LEVEL_MODULES = {"mne", "scipy", "torch", "ripser", "gudhi", "boto3", "botocore", "sklearn", "subprocess", "socket", "urllib", "requests"}


def _imported_top_level_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module.split(".")[0])
    return names


def test_contract_adapters_module_has_no_forbidden_imports():
    path = _REPO_ROOT / "tools" / "awareness_studio_research_loop" / "contract_adapters.py"
    found = _imported_top_level_modules(path) & _FORBIDDEN_TOP_LEVEL_MODULES
    assert found == set()


def test_contract_adapters_does_not_import_tools_awareness_studio_research_or_tools_research_cycle():
    """Read-only means read-only: this module must not take a hard
    import dependency on either upstream package, only consume their
    shapes as data."""
    path = _REPO_ROOT / "tools" / "awareness_studio_research_loop" / "contract_adapters.py"
    imported = _imported_top_level_modules(path)
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    from_imports = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module}
    assert "tools.awareness_studio_research" not in from_imports
    assert "tools.research_cycle" not in from_imports
    assert not any(m.startswith("tools") and m not in {"tools.awareness_studio_research_loop"} for m in imported)


def test_isolated_subprocess_execution_of_the_validation_script(tmp_path):
    out_dir = tmp_path / "out"
    result = subprocess.run(
        [sys.executable, "-m", "scripts.validate_awareness_cycle_integration", "--output-dir", str(out_dir), "--now", "2026-01-01T00:00:00+00:00"],
        cwd=str(_REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    assert (out_dir / "contract_integration_report.json").is_file()
