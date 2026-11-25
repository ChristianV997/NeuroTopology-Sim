from __future__ import annotations

from tools.release_scientific_audit import dashboard_isolation
from tools.release_scientific_audit.models import DashboardIsolationInput


def test_missing_path_is_none_not_false(tmp_path):
    result = dashboard_isolation.scan_dashboard_source(tmp_path / "nope")
    assert result["ok"] is None


def test_clean_source_passes(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "app.py").write_text("import fastapi\n", encoding="utf-8")
    result = dashboard_isolation.scan_dashboard_source(src)
    assert result["ok"] is True


def test_forbidden_import_is_flagged(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "route.py").write_text("import core.topology\n", encoding="utf-8")
    result = dashboard_isolation.scan_dashboard_source(src)
    assert result["ok"] is False
    assert result["violations"]


def test_check_function_produces_blocking_finding_on_violation(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "route.py").write_text("from sim.pitnn.bayesian_falsification import compare_models\n", encoding="utf-8")
    findings = dashboard_isolation.check_dashboard_solver_isolation(str(src), None)
    assert any(f.severity == "blocking" for f in findings)


def test_check_function_clean_source_produces_no_blocking(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "route.py").write_text("import json\n", encoding="utf-8")
    findings = dashboard_isolation.check_dashboard_solver_isolation(str(src), None)
    assert not any(f.severity == "blocking" for f in findings)


def test_claim_mismatch_is_flagged(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "route.py").write_text("import json\n", encoding="utf-8")  # actually clean
    claim = DashboardIsolationInput(claimed_ok=False, claim_source="docs/release/dashboard_isolation_report.md")
    findings = dashboard_isolation.check_dashboard_solver_isolation(str(src), claim)
    assert any(f.severity == "blocking" and "own independent scan" in f.summary for f in findings)


def test_claim_matching_independent_scan_is_not_flagged(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "route.py").write_text("import json\n", encoding="utf-8")
    claim = DashboardIsolationInput(claimed_ok=True, claim_source="docs/release/dashboard_isolation_report.md")
    findings = dashboard_isolation.check_dashboard_solver_isolation(str(src), claim)
    assert not any(f.severity == "blocking" for f in findings)


def test_no_path_supplied_is_warning():
    findings = dashboard_isolation.check_dashboard_solver_isolation(None, None)
    assert findings[0].severity == "warning"
