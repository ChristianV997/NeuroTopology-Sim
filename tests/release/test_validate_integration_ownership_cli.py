"""Release CLI smoke for scripts/validate_integration_ownership.py.

QA owns tests/release/integration_ownership_validate.py and
tests/release/test_integration_ownership.py. This file only checks that the
Release CLI wraps those helpers. Inventory is not evidence. Synthetic
fixtures cannot establish scientific PASS.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

from .integration_ownership_validate import (
    INVENTORY_PATH,
    collect_forbidden_imports,
    validate_integration_ownership,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
CLI_PATH = REPO_ROOT / "scripts" / "validate_integration_ownership.py"
MALFORMED_FIXTURE = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "ownership"
    / "malformed_synthetic_pass.yaml"
)
LIVE_HEAD = "af3ac584419148ddcfc57cb565c416eba6328725"


def _load_cli():
    spec = importlib.util.spec_from_file_location(
        "validate_integration_ownership", CLI_PATH
    )
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
    assert "tests.release.integration_ownership_validate" in text
    assert "from tests.release.integration_ownership_validate import" in text
    assert "validate_integration_ownership" in text
    assert "load_inventory" in text
    assert "INVENTORY_PATH" in text
    assert "IntegrationOwnershipValidationError" in text
    assert "collect_forbidden_imports" in text
    assert "offline" in text.lower()
    assert "marketos" not in text.lower()


def test_cli_wraps_qa_helpers_not_rules():
    assert CLI.validate is validate_integration_ownership or CLI.validate.__module__.endswith(
        "integration_ownership_validate"
    )
    assert CLI.validate_integration_ownership.__module__.endswith(
        "integration_ownership_validate"
    )
    assert CLI.load_inventory.__module__.endswith("integration_ownership_validate")
    assert CLI.INVENTORY_PATH == INVENTORY_PATH
    assert CLI.collect_forbidden_imports.__module__.endswith(
        "integration_ownership_validate"
    )


def test_live_inventory_cli_exits_zero_stdout_only(tmp_path):
    result = _run_cli("--format", "json", cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["validation_ok"] is True
    assert report["errors"] == []
    assert report["codex_c_merger_queue"] is None
    assert report["synthetic_status"] == "NOT_SUPPORTED"
    assert report["empirical_pass_from_this_pack"] is False
    assert report["inventory_is_not_evidence"] is True
    assert report["CURRENT_INTEGRATION_HEAD"] == LIVE_HEAD
    current = report["current_integration"]
    assert current["head_ref_oid"] == LIVE_HEAD
    assert current["merged"] is False
    assert current["on_origin_main"] is False
    assert current["status"] == "OPEN_REVIEW"
    assert isinstance(report["work_items"], list)
    assert report["work_items"]
    for row in report["work_items"]:
        assert set(row) == {"id", "status", "pr_number"}
        assert row["id"] is not None
        assert row["status"] is not None
    leftover = [path for path in tmp_path.rglob("*") if path.is_file()]
    assert leftover == [], leftover
    qa_errors = validate_integration_ownership(INVENTORY_PATH)
    assert qa_errors == report["errors"] == []


def test_malformed_fixture_cli_exits_one(tmp_path):
    result = _run_cli(
        "--inventory",
        str(MALFORMED_FIXTURE),
        "--format",
        "json",
        cwd=tmp_path,
    )
    assert result.returncode == 1, result.stdout
    report = json.loads(result.stdout)
    assert report["validation_ok"] is False
    assert report["errors"]
    assert report["codex_c_merger_queue"] is None
    qa_errors = validate_integration_ownership(MALFORMED_FIXTURE)
    assert report["errors"] == qa_errors
    leftover = [path for path in tmp_path.rglob("*") if path.is_file()]
    assert leftover == [], leftover


def test_json_is_deterministic_sort_keys():
    doc, errors = CLI.load_and_validate(INVENTORY_PATH)
    first = CLI.dumps_json(
        CLI.build_report(doc, errors, inventory_path=INVENTORY_PATH)
    )
    second = CLI.dumps_json(
        CLI.build_report(doc, errors, inventory_path=INVENTORY_PATH)
    )
    assert first == second
    payload = json.loads(first)
    assert (
        json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False)
        + "\n"
        == first
    )
    assert payload["validation_ok"] is True
    assert payload["codex_c_merger_queue"] is None


def test_markdown_states_required_caveats():
    doc, errors = CLI.load_and_validate(INVENTORY_PATH)
    report = CLI.build_report(doc, errors, inventory_path=INVENTORY_PATH)
    text = CLI.render_markdown(report)
    blob = text.lower()
    assert "not_supported" in blob
    assert "never invent pass" in blob
    assert "inventory is not evidence" in blob
    assert "integrated_only is not merged into main" in blob
    assert "proxy bayes" in blob
    assert "formal k" in blob
    assert "empty-step ci failure is not blocked_by_tests" in blob
    assert "billing-not-started is not pytest pass" in blob
    assert "do not merge" in blob
    assert "never close/retarget" in blob
    assert "codex c" in blob
    assert "merger queue" in blob
    assert "scientific pass" in blob
    assert "not a scientific pass" in blob


def test_cli_markdown_stdout_live():
    result = _run_cli("--format", "markdown")
    assert result.returncode == 0, result.stderr
    assert "NOT_SUPPORTED" in result.stdout
    assert "Never invent PASS" in result.stdout
    assert "INTEGRATED_ONLY is not merged into main" in result.stdout
    assert "Empty-step CI FAILURE is not BLOCKED_BY_TESTS" in result.stdout
    assert "Billing-not-started is not pytest PASS" in result.stdout
    assert "codex_c_merger_queue" in result.stdout.lower() or "codex_c_merger_queue" in result.stdout


def test_output_dir_writes_only_when_requested(tmp_path):
    out = tmp_path / "reports"
    result = _run_cli("--format", "both", "--output-dir", str(out))
    assert result.returncode == 0, result.stderr
    json_path = out / "validate_integration_ownership.json"
    md_path = out / "validate_integration_ownership.md"
    assert json_path.is_file()
    assert md_path.is_file()
    report = json.loads(json_path.read_text(encoding="utf-8"))
    assert report["validation_ok"] is True
    assert report["codex_c_merger_queue"] is None
    text = md_path.read_text(encoding="utf-8")
    assert "NOT_SUPPORTED" in text
    assert "Never invent PASS" in text
    assert "INTEGRATED_ONLY is not merged into main" in text


def test_missing_inventory_fails_closed(tmp_path):
    missing = tmp_path / "no-such-inventory.yaml"
    result = _run_cli("--inventory", str(missing), "--format", "json", cwd=tmp_path)
    assert result.returncode == 1
    report = json.loads(result.stdout)
    assert report["validation_ok"] is False
    assert any("not_found" in item for item in report["errors"])
    leftover = [path for path in tmp_path.rglob("*") if path.is_file()]
    assert leftover == [], leftover


def test_unavailable_fields_are_null_not_invented():
    report = CLI.build_report(
        None, ["inventory:not_a_mapping"], inventory_path="/tmp/missing.yaml"
    )
    assert report["validation_ok"] is False
    assert report["work_items"] is None
    assert report["synthetic_status"] is None
    assert report["current_integration"] is None
    assert report["CURRENT_INTEGRATION_HEAD"] is None
    assert report["empirical_pass_from_this_pack"] is None
    assert report["inventory_is_not_evidence"] is None
    assert report["sole_merger"] is None
    assert report["merger_instruction"] is None
    assert report["never_close_prs"] is None
    assert report["codex_c_merger_queue"] is None
    for key in ("timing", "memory", "duration_s", "peak", "rss", "memory_mb"):
        assert key not in report
    assert report["synthetic_status"] != "PASS"
