import json
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from tests.research_plan_quality.conftest import variant
from tools.research_plan_quality.models import ResearchPlan, RUBRIC_DIMENSIONS
from tools.research_plan_quality.reporting import NonFiniteValueError, to_finite_json, to_markdown
from tools.research_plan_quality.rubric import evaluate_plan

REPO_ROOT = Path(__file__).resolve().parents[2]


def _evaluate(data: dict) -> "PlanAuditResult":  # noqa: F821
    return evaluate_plan(ResearchPlan.from_dict(data))


# -- clean complete plan --------------------------------------------------------

def test_clean_complete_plan_is_ready(clean_plan_dict):
    result = _evaluate(clean_plan_dict)
    assert result.overall_status == "READY_FOR_EXECUTION"
    assert result.hard_blockers == ()
    assert result.warnings == ()
    assert result.overall_score == 1.0
    assert len(result.criteria) == 20
    assert result.evidence_class == "research_plan_audit"


def test_all_20_rubric_dimensions_are_evaluated(clean_plan_dict):
    result = _evaluate(clean_plan_dict)
    dimensions = {c.dimension for c in result.criteria}
    assert dimensions == set(RUBRIC_DIMENSIONS)
    assert len(RUBRIC_DIMENSIONS) == 20


# -- missing provenance ------------------------------------------------------------

def test_missing_provenance_is_hard_blocker(clean_plan_dict):
    data = variant(clean_plan_dict, sources=[])
    result = _evaluate(data)
    assert result.overall_status == "BLOCKED"
    assert any(b.startswith("source_quality_provenance") for b in result.hard_blockers)
    assert "source_quality_provenance" in result.missing_fields


def test_source_without_identifier_is_blocker_not_missing(clean_plan_dict):
    data = variant(
        clean_plan_dict,
        sources=[{"title": "Some Paper", "identifier": None, "verification_status": None}],
    )
    result = _evaluate(data)
    assert any(b.startswith("source_quality_provenance") for b in result.hard_blockers)
    assert "source_quality_provenance" not in result.missing_fields


# -- ambiguous conditions -----------------------------------------------------------

def test_ambiguous_conditions_is_hard_blocker(clean_plan_dict):
    data = variant(
        clean_plan_dict,
        condition_labels=["rest", "task", "other"],
        condition_label_definitions={"rest": "eyes-closed resting state", "task": "attention task"},
    )
    result = _evaluate(data)
    assert result.overall_status == "BLOCKED"
    assert any("other" in b for b in result.hard_blockers)


# -- missing multiplicity correction --------------------------------------------------

def test_missing_multiplicity_correction_with_multiple_tests_is_blocker(clean_plan_dict):
    data = variant(clean_plan_dict, number_of_planned_tests=5, multiplicity_correction=None)
    result = _evaluate(data)
    assert result.overall_status == "BLOCKED"
    assert any(b.startswith("multiplicity_correction") for b in result.hard_blockers)


def test_single_planned_test_does_not_require_multiplicity_correction(clean_plan_dict):
    data = variant(clean_plan_dict, number_of_planned_tests=1, multiplicity_correction=None)
    result = _evaluate(data)
    mc = next(c for c in result.criteria if c.dimension == "multiplicity_correction")
    assert mc.status == "pass"


# -- leakage --------------------------------------------------------------------------

def test_leakage_risk_without_controls_is_blocker(clean_plan_dict):
    data = variant(clean_plan_dict, leakage_controls=[])
    result = _evaluate(data)
    assert result.overall_status == "BLOCKED"
    assert any(b.startswith("leakage_prevention") for b in result.hard_blockers)


def test_no_leakage_risk_and_no_controls_is_warning_only(clean_plan_dict):
    data = variant(clean_plan_dict, leakage_controls=[], known_leakage_risks=[])
    result = _evaluate(data)
    lp = next(c for c in result.criteria if c.dimension == "leakage_prevention")
    assert lp.status == "warning"


# -- synthetic-only (evidence separation) --------------------------------------------

def test_synthetic_only_plan_declares_evidence_class_and_passes_that_dimension(clean_plan_dict):
    data = variant(clean_plan_dict, evidence_class_declared="synthetic", dataset_id="synthetic-grid-v1")
    result = _evaluate(data)
    es = next(c for c in result.criteria if c.dimension == "evidence_separation")
    assert es.status == "pass"


def test_missing_evidence_class_declaration_is_hard_blocker(clean_plan_dict):
    data = variant(clean_plan_dict, evidence_class_declared=None)
    result = _evaluate(data)
    assert result.overall_status == "BLOCKED"
    assert "evidence_separation" in result.missing_fields


# -- unsupported causal language -------------------------------------------------------

def test_unsupported_causal_language_on_synthetic_data_is_blocker(clean_plan_dict):
    data = variant(
        clean_plan_dict,
        evidence_class_declared="synthetic",
        dataset_id="synthetic-grid-v1",
        claim_language="This simulation proves that triadic connectivity causes improved attention.",
    )
    result = _evaluate(data)
    assert result.overall_status == "BLOCKED"
    assert any(b.startswith("claim_calibration") for b in result.hard_blockers)


def test_causal_language_on_empirical_data_is_warning_not_blocker(clean_plan_dict):
    data = variant(
        clean_plan_dict,
        evidence_class_declared="empirical",
        claim_language="This study demonstrates conclusively that connectivity causes attention gains.",
    )
    result = _evaluate(data)
    cc = next(c for c in result.criteria if c.dimension == "claim_calibration")
    assert cc.status == "warning"
    assert result.overall_status == "NEEDS_REVISION"
    assert not any(b.startswith("claim_calibration") for b in result.hard_blockers)


# -- incomplete null model --------------------------------------------------------------

def test_incomplete_null_model_is_warning(clean_plan_dict):
    data = variant(clean_plan_dict, null_model={"method": "phase-randomized surrogate", "description": ""})
    result = _evaluate(data)
    nm = next(c for c in result.criteria if c.dimension == "null_model_specification")
    assert nm.status == "warning"
    assert result.overall_status == "NEEDS_REVISION"


def test_missing_null_model_entirely_is_hard_blocker(clean_plan_dict):
    data = variant(clean_plan_dict, null_model=None)
    result = _evaluate(data)
    assert result.overall_status == "BLOCKED"
    assert "null_model_specification" in result.missing_fields


# -- low sample size ----------------------------------------------------------------------

def test_low_sample_size_below_stated_minimum_is_blocker(clean_plan_dict):
    data = variant(clean_plan_dict, sample_size=10, minimum_required_sample_size=30)
    result = _evaluate(data)
    assert result.overall_status == "BLOCKED"
    assert any(b.startswith("pairing_sample_size_adequacy") for b in result.hard_blockers)


def test_sample_size_meeting_its_own_minimum_passes(clean_plan_dict):
    data = variant(clean_plan_dict, sample_size=30, minimum_required_sample_size=30)
    result = _evaluate(data)
    ps = next(c for c in result.criteria if c.dimension == "pairing_sample_size_adequacy")
    assert ps.status == "pass"


# -- deterministic repeat --------------------------------------------------------------------

def test_deterministic_repeat(clean_plan_dict):
    outputs = {to_finite_json(_evaluate(clean_plan_dict)) for _ in range(15)}
    assert len(outputs) == 1


# -- finite JSON ---------------------------------------------------------------------------

def test_to_finite_json_round_trips(clean_plan_dict):
    result = _evaluate(clean_plan_dict)
    parsed = json.loads(to_finite_json(result))
    assert parsed["overall_status"] == "READY_FOR_EXECUTION"
    assert parsed["evidence_class"] == "research_plan_audit"


def test_to_finite_json_rejects_nan_and_infinity(clean_plan_dict):
    import dataclasses

    result = _evaluate(clean_plan_dict)
    tampered = dataclasses.replace(result, overall_score=float("nan"))
    with pytest.raises(NonFiniteValueError):
        to_finite_json(tampered)

    tampered_inf = dataclasses.replace(result, overall_score=float("inf"))
    with pytest.raises(NonFiniteValueError):
        to_finite_json(tampered_inf)


def test_to_markdown_contains_key_sections(clean_plan_dict):
    result = _evaluate(clean_plan_dict)
    md = to_markdown(result)
    assert "Research Plan Quality Audit" in md
    assert "evidence_class" in md
    assert "Overall status" in md


# -- no-network ------------------------------------------------------------------------------

def test_no_network_during_full_evaluation(clean_plan_dict, monkeypatch):
    def _no_network(*args, **kwargs):
        raise AssertionError("network access attempted during plan evaluation")

    monkeypatch.setattr(socket, "socket", _no_network)
    result = _evaluate(clean_plan_dict)
    assert result.overall_status == "READY_FOR_EXECUTION"


def test_module_import_touches_no_network(monkeypatch):
    def _no_network(*args, **kwargs):
        raise AssertionError("network access attempted merely by importing the package")

    monkeypatch.setattr(socket, "socket", _no_network)
    import importlib

    import tools.research_plan_quality.rubric as rubric_module

    importlib.reload(rubric_module)


def test_no_heavy_import():
    script = (
        "import sys; "
        "import tools.research_plan_quality as pkg; "
        "import tools.research_plan_quality.models; "
        "import tools.research_plan_quality.checks; "
        "import tools.research_plan_quality.rubric; "
        "import tools.research_plan_quality.reporting; "
        "heavy = {'numpy', 'scipy', 'sklearn', 'mne', 'torch', 'pandas', 'requests'}; "
        "print('LOADED_HEAVY=' + ','.join(sorted(heavy & set(sys.modules))))"
    )
    result = subprocess.run([sys.executable, "-c", script], cwd=REPO_ROOT, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    loaded = next(line for line in result.stdout.splitlines() if line.startswith("LOADED_HEAVY=")).split("=", 1)[1]
    assert loaded == ""


# -- isolated subprocess CLI --------------------------------------------------------------------

def test_isolated_subprocess_cli(tmp_path, clean_plan_dict):
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(clean_plan_dict))
    result = subprocess.run(
        [sys.executable, "scripts/audit_research_plan.py", "--plan", str(plan_path)],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["overall_status"] == "READY_FOR_EXECUTION"
    assert "overall_status=READY_FOR_EXECUTION" in result.stderr


def test_isolated_subprocess_cli_blocked_exit_code(tmp_path, clean_plan_dict):
    data = variant(clean_plan_dict, sources=[])
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(data))
    result = subprocess.run(
        [sys.executable, "scripts/audit_research_plan.py", "--plan", str(plan_path)],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["overall_status"] == "BLOCKED"


# -- never infer / never fill missing methods (safety requirement) -----------------------------

def test_evaluator_never_fabricates_a_value_for_missing_field():
    """A ResearchPlan built with everything left at its default absence
    must report every dimension as missing/blocker/warning -- never
    'pass' from a guessed value."""
    plan = ResearchPlan()
    result = evaluate_plan(plan)
    assert result.overall_status == "BLOCKED"
    passing = [c for c in result.criteria if c.status == "pass"]
    # multiplicity_correction legitimately passes on an empty plan since
    # "no planned tests" trivially satisfies "not applicable" -- that is
    # the one dimension that can honestly pass with nothing supplied.
    assert {c.dimension for c in passing} <= {"multiplicity_correction"}


def test_rubric_score_never_implies_scientific_confirmation(clean_plan_dict):
    result = _evaluate(clean_plan_dict)
    assert result.evidence_class == "research_plan_audit"
    assert result.evidence_class != "scientific_evidence"
