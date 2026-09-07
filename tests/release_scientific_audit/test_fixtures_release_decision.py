"""The ten required deterministic fixture scenarios.

Each fixture is a real JSON document under fixtures/ (schema documented
in docs/release/scientific_release_audit.md); every test loads it,
runs the audit, and asserts the release decision the mission asks for.
No network, no git, no execution of any scientific/CI code -- purely
reading a JSON document and evaluating pure functions over it.
"""
from __future__ import annotations

import dataclasses
from pathlib import Path

from tools.release_scientific_audit import audit, loaders

_FIXTURES = Path(__file__).parent / "fixtures"


def _run(name: str, **overrides):
    audit_input = loaders.audit_input_from_file(_FIXTURES / name)
    if overrides:
        audit_input = dataclasses.replace(audit_input, **overrides)
    return audit.run_audit(audit_input)


def test_clean_engineering_only_release_is_release_ready(tmp_path):
    clean_dashboard = tmp_path / "dashboard_src"
    clean_dashboard.mkdir()
    (clean_dashboard / "route.py").write_text("import json\n", encoding="utf-8")
    report = _run("clean_engineering_only.json", dashboard_src_path=str(clean_dashboard))
    assert report.release_decision == "RELEASE_READY"
    assert not any(f.severity == "blocking" for f in report.findings)
    assert not any(f.severity == "warning" for f in report.findings)


def test_synthetic_only_run_claiming_pass_is_blocked_by_science():
    report = _run("synthetic_only_run.json")
    assert report.release_decision == "BLOCKED_BY_SCIENCE"
    assert any("synthetic" in f.summary.lower() for f in report.findings if f.severity == "blocking")


def test_incomplete_empirical_provenance_is_blocked_by_science():
    report = _run("incomplete_empirical_provenance.json")
    assert report.release_decision == "BLOCKED_BY_SCIENCE"
    assert any(f.check == "missing_provenance" and f.severity == "blocking" for f in report.findings)


def test_proxy_bayes_factor_claiming_pass_is_blocked_by_science():
    report = _run("proxy_bayes_factor.json")
    assert report.release_decision == "BLOCKED_BY_SCIENCE"
    assert any(f.check == "proxy_vs_formal_evidence" and f.severity == "blocking" for f in report.findings)


def test_formal_evidence_absence_is_review_only_not_a_hard_block():
    """No evidence_kind declared at all (neither proxy nor formal) is a
    real gap worth a human's attention, but it is not itself proof of a
    violation -- the verdict here is NOT_SUPPORTED, so this should
    surface as a warning (REVIEW_ONLY), not a hard science block."""
    report = _run("formal_evidence_absence.json")
    assert report.release_decision == "REVIEW_ONLY"
    assert any(f.check == "proxy_vs_formal_evidence" and f.severity == "warning" for f in report.findings)


def test_dashboard_solver_import_is_blocked_by_science(tmp_path):
    bad_dashboard = tmp_path / "dashboard_src"
    bad_dashboard.mkdir()
    (bad_dashboard / "route.py").write_text(
        "from sim.pitnn.bayesian_falsification import compare_models\n", encoding="utf-8"
    )
    report = _run("dashboard_solver_import.json", dashboard_src_path=str(bad_dashboard))
    assert report.release_decision == "BLOCKED_BY_SCIENCE"
    assert "DASHBOARD_SOLVER_ISOLATION_VIOLATION" in report.decision_reason_codes


def test_failed_ci_is_blocked_by_tests():
    report = _run("failed_ci.json")
    assert report.release_decision == "BLOCKED_BY_TESTS"


def test_timed_out_tests_is_blocked_by_tests():
    report = _run("timed_out_tests.json")
    assert report.release_decision == "BLOCKED_BY_TESTS"
    assert any("timeout" in f.summary.lower() for f in report.findings if f.severity == "blocking")


def test_missing_optional_dependencies_is_blocked_by_infrastructure():
    report = _run("missing_optional_dependencies.json")
    assert report.release_decision == "BLOCKED_BY_INFRASTRUCTURE"
    assert any(f.check == "optional_dependency_availability" and f.severity == "blocking" for f in report.findings)


def test_non_finite_report_values_is_blocked_by_science():
    report = _run("non_finite_report_values.json")
    assert report.release_decision == "BLOCKED_BY_SCIENCE"
    assert any(f.check == "finite_numeric_fields" and f.severity == "blocking" for f in report.findings)


# ---------------------------------------------------------------------------
# Determinism across all ten fixtures
# ---------------------------------------------------------------------------

def test_every_fixture_scenario_is_deterministic_across_repeats(tmp_path):
    bad_dashboard = tmp_path / "dashboard_src"
    bad_dashboard.mkdir()
    (bad_dashboard / "route.py").write_text(
        "from sim.pitnn.bayesian_falsification import compare_models\n", encoding="utf-8"
    )
    clean_dashboard = tmp_path / "clean_dashboard_src"
    clean_dashboard.mkdir()
    (clean_dashboard / "route.py").write_text("import json\n", encoding="utf-8")
    scenarios = [
        ("clean_engineering_only.json", {"dashboard_src_path": str(clean_dashboard)}),
        ("synthetic_only_run.json", {}),
        ("incomplete_empirical_provenance.json", {}),
        ("proxy_bayes_factor.json", {}),
        ("formal_evidence_absence.json", {}),
        ("dashboard_solver_import.json", {"dashboard_src_path": str(bad_dashboard)}),
        ("failed_ci.json", {}),
        ("timed_out_tests.json", {}),
        ("missing_optional_dependencies.json", {}),
        ("non_finite_report_values.json", {}),
    ]
    for name, overrides in scenarios:
        baseline = _run(name, **overrides)
        for _ in range(10):
            repeat = _run(name, **overrides)
            assert repeat.release_decision == baseline.release_decision
            assert repeat.decision_reason_codes == baseline.decision_reason_codes
            assert [f.to_dict() for f in repeat.findings] == [f.to_dict() for f in baseline.findings]
