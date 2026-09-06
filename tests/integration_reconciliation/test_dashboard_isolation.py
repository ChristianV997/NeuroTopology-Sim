from __future__ import annotations

from tools.integration_reconciliation import dashboard_isolation


def test_missing_dashboard_dir_is_none_not_false(tmp_path):
    result = dashboard_isolation.check_dashboard_isolation(tmp_path / "does_not_exist")
    assert result["ok"] is None
    assert result["scanned_files"] == 0


def test_clean_dashboard_source_passes(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "app.py").write_text("import fastapi\nimport json\n", encoding="utf-8")
    result = dashboard_isolation.check_dashboard_isolation(src)
    assert result["ok"] is True
    assert result["scanned_files"] == 1
    assert result["violations"] == []


def test_forbidden_import_is_flagged(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "route.py").write_text("from sim.pitnn.bayesian_falsification import compare_models\n", encoding="utf-8")
    result = dashboard_isolation.check_dashboard_isolation(src)
    assert result["ok"] is False
    assert any("sim.pitnn.bayesian_falsification" in v for v in result["violations"])


def test_plain_import_form_is_also_caught(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "route.py").write_text("import governance.validate\n", encoding="utf-8")
    result = dashboard_isolation.check_dashboard_isolation(src)
    assert result["ok"] is False


def test_unrelated_submodule_import_is_not_falsely_flagged(tmp_path):
    """A module that merely starts with the same characters as a forbidden
    prefix but isn't a real submodule of it must not be flagged."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "route.py").write_text("import governance_unrelated_package\n", encoding="utf-8")
    result = dashboard_isolation.check_dashboard_isolation(src)
    assert result["ok"] is True


def test_nested_files_are_scanned(tmp_path):
    src = tmp_path / "src"
    (src / "web" / "routes").mkdir(parents=True)
    (src / "web" / "routes" / "solve.py").write_text(
        "from core.topology import compute_Qz\n", encoding="utf-8"
    )
    result = dashboard_isolation.check_dashboard_isolation(src)
    assert result["ok"] is False
    assert result["scanned_files"] == 1
