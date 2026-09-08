"""Release CLI smoke for scripts/validate_release_blockers.py.

QA owns tests/release/blocker_registry_validate.py and
tests/release/test_blocker_registry.py. This file only checks that the
Release CLI wraps those helpers. Inventory is not evidence. Synthetic
fixtures cannot establish scientific PASS.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

from .blocker_registry_validate import (
    REGISTRY_PATH,
    collect_forbidden_imports,
    validate_blocker_registry,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
CLI_PATH = REPO_ROOT / "scripts" / "validate_release_blockers.py"
MALFORMED_FIXTURE = (
    Path(__file__).resolve().parent / "fixtures" / "blockers" / "malformed_synthetic_pass.yaml"
)


def _load_cli():
    spec = importlib.util.spec_from_file_location("validate_release_blockers", CLI_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


CLI = _load_cli()


def _run_cli(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CLI_PATH), *args],
        cwd=cwd or REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def test_cli_script_exists_and_is_offline_source():
    assert CLI_PATH.is_file()
    hits = collect_forbidden_imports(CLI_PATH)
    assert hits == [], hits
    text = CLI_PATH.read_text(encoding="utf-8")
    assert "tests.release.blocker_registry_validate" in text
    assert "from tests.release.blocker_registry_validate import" in text
    assert "validate_blocker_registry" in text
    assert "load_registry" in text
    assert "REGISTRY_PATH" in text
    assert "BlockerRegistryValidationError" in text
    assert "offline" in text.lower()
    assert "marketos" not in text.lower()


def test_cli_wraps_qa_helpers_not_rules():
    assert CLI.validate is validate_blocker_registry or CLI.validate.__module__.endswith(
        "blocker_registry_validate"
    )
    assert CLI.validate_blocker_registry.__module__.endswith("blocker_registry_validate")
    assert CLI.load_registry.__module__.endswith("blocker_registry_validate")
    assert CLI.REGISTRY_PATH == REGISTRY_PATH


def test_live_registry_cli_exits_zero_stdout_only(tmp_path):
    result = _run_cli("--format", "json", cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["validation_ok"] is True
    assert report["errors"] == []
    assert report["remediation_queue"] is None
    assert report["synthetic_status"] == "NOT_SUPPORTED"
    assert report["empirical_pass_from_this_pack"] is False
    assert report["inventory_is_not_evidence"] is True
    assert isinstance(report["blockers"], list)
    assert report["blockers"]
    for row in report["blockers"]:
        assert set(row) == {
            "id",
            "category",
            "severity",
            "evidence",
            "scientific_impact",
            "release_impact",
        }
        for key in ("id", "category", "severity", "scientific_impact", "release_impact"):
            assert row[key] is not None
        assert isinstance(row["evidence"], list) and row["evidence"]
        assert str(row["scientific_impact"]).strip().lower() not in {"pass", "scientific_pass"}
    leftover = [path for path in tmp_path.rglob("*") if path.is_file()]
    assert leftover == [], leftover
    qa_errors = validate_blocker_registry(REGISTRY_PATH)
    assert qa_errors == report["errors"] == []


def test_malformed_fixture_cli_exits_one(tmp_path):
    result = _run_cli(
        "--registry",
        str(MALFORMED_FIXTURE),
        "--format",
        "json",
        cwd=tmp_path,
    )
    assert result.returncode == 1, result.stdout
    report = json.loads(result.stdout)
    assert report["validation_ok"] is False
    assert report["errors"]
    qa_errors = validate_blocker_registry(MALFORMED_FIXTURE)
    assert report["errors"] == qa_errors
    leftover = [path for path in tmp_path.rglob("*") if path.is_file()]
    assert leftover == [], leftover


def test_json_is_deterministic_sort_keys():
    doc, errors = CLI.load_and_validate(REGISTRY_PATH)
    first = CLI.dumps_json(CLI.build_report(doc, errors, registry_path=REGISTRY_PATH))
    second = CLI.dumps_json(CLI.build_report(doc, errors, registry_path=REGISTRY_PATH))
    assert first == second
    payload = json.loads(first)
    assert json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=False) + "\n" == first
    assert payload["validation_ok"] is True


def test_markdown_states_required_caveats():
    doc, errors = CLI.load_and_validate(REGISTRY_PATH)
    report = CLI.build_report(doc, errors, registry_path=REGISTRY_PATH)
    text = CLI.render_markdown(report)
    blob = text.lower()
    assert "not_supported" in blob
    assert "never invent pass" in blob
    assert "billing-not-started is not pytest pass" in blob
    assert "empty-step failure is not test_failure" in blob
    assert "inventory is not evidence" in blob
    assert "do not merge" in blob
    assert "integration" in blob
    assert "remediation queue" in blob
    assert "scientific pass" in blob
    # validation_ok is not a scientific PASS
    assert "not a scientific pass" in blob


def test_cli_markdown_stdout_live():
    result = _run_cli("--format", "markdown")
    assert result.returncode == 0, result.stderr
    assert "NOT_SUPPORTED" in result.stdout
    assert "Never invent PASS" in result.stdout
    assert "Billing-not-started is not pytest PASS" in result.stdout
    assert "Empty-step FAILURE is not TEST_FAILURE" in result.stdout


def test_output_dir_writes_only_when_requested(tmp_path):
    out = tmp_path / "reports"
    result = _run_cli("--format", "both", "--output-dir", str(out))
    assert result.returncode == 0, result.stderr
    json_path = out / "validate_release_blockers.json"
    md_path = out / "validate_release_blockers.md"
    assert json_path.is_file()
    assert md_path.is_file()
    report = json.loads(json_path.read_text(encoding="utf-8"))
    assert report["validation_ok"] is True
    text = md_path.read_text(encoding="utf-8")
    assert "NOT_SUPPORTED" in text
    assert "Never invent PASS" in text


def test_missing_registry_fails_closed(tmp_path):
    missing = tmp_path / "no-such-registry.yaml"
    result = _run_cli("--registry", str(missing), "--format", "json", cwd=tmp_path)
    assert result.returncode == 1
    report = json.loads(result.stdout)
    assert report["validation_ok"] is False
    assert any("not_found" in item for item in report["errors"])
    leftover = [path for path in tmp_path.rglob("*") if path.is_file()]
    assert leftover == [], leftover


def test_unavailable_fields_are_null_not_invented():
    report = CLI.build_report(None, ["registry:not_a_mapping"], registry_path="/tmp/missing.yaml")
    assert report["validation_ok"] is False
    assert report["blockers"] is None
    assert report["synthetic_status"] is None
    assert report["current_integration"] is None
    assert report["empirical_pass_from_this_pack"] is None
    assert report["scientific_pass_from_this_pack"] is None
    assert report["inventory_is_not_evidence"] is None
    assert report["remediation_queue"] is None
    for key in ("timing", "memory", "duration_s", "peak", "rss"):
        assert key not in report
