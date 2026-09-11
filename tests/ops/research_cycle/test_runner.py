"""Runner: missing-command NOT_AVAILABLE, timeouts, fixture dry-run, no-write leak."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from ops.research_cycle.catalog import Catalog, StepSpec, load_catalog
from ops.research_cycle.cli import main as cli_main
from ops.research_cycle.exit_codes import BLOCKED, FAILURE, INCOMPLETE, NOT_AVAILABLE, PASS
from ops.research_cycle.runner import RunConfig, run_audit, run_step
from ops.research_cycle.safety import SafetyError, require_output_dir

from tests.ops.research_cycle.conftest import CATALOG, REPO_ROOT


def _catalog_from_steps(path: Path, steps: list[dict]) -> Catalog:
    payload = {
        "schema_version": "ResearchCycleOperatorCatalog.v1",
        "pack_id": "research_cycle_operator_pack",
        "steps": steps,
        "optional_steps": [],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return load_catalog(path)


def _config(tmp_path: Path, catalog: Catalog, **kwargs) -> RunConfig:
    out = require_output_dir(tmp_path / "out")
    defaults = dict(
        repo_root=REPO_ROOT,
        output_dir=out,
        catalog=catalog,
        python=sys.executable,
        emit_surfaces_enabled=False,
        generated_at="2026-09-10T00:00:00+00:00",
    )
    defaults.update(kwargs)
    return RunConfig(**defaults)


def test_missing_command_is_not_available(tmp_path: Path):
    catalog = _catalog_from_steps(
        tmp_path / "catalog.json",
        [
            {
                "id": "repository_state",
                "order": 1,
                "title": "missing",
                "kind": "external",
                "timeout_s": 5,
                "argv": ["rcop_definitely_missing_cli_zzz", "--help"],
                "availability_probe": {"type": "command", "command": "rcop_definitely_missing_cli_zzz"},
            }
        ],
    )
    result = run_step(_config(tmp_path, catalog), catalog.steps[0])
    assert result.status == "NOT_AVAILABLE"
    assert result.reason == "command_not_available"
    assert result.status != "PASS"


def test_timeout_is_failure(tmp_path: Path):
    catalog = _catalog_from_steps(
        tmp_path / "catalog.json",
        [
            {
                "id": "schema_validation",
                "order": 2,
                "title": "sleep",
                "kind": "external",
                "timeout_s": 1,
                "argv": [sys.executable, "-c", "import time; time.sleep(30)"],
                "availability_probe": {"type": "command", "command": sys.executable},
            }
        ],
    )
    result = run_step(_config(tmp_path, catalog, timeout_override=1), catalog.steps[0])
    assert result.status == "FAILURE"
    assert result.reason and "timeout" in result.reason


def test_fixture_dry_run_without_solver_or_download(tmp_path: Path):
    catalog = load_catalog(CATALOG)
    config = _config(
        tmp_path,
        catalog,
        step_ids=(
            "repository_state",
            "schema_validation",
            "research_plan_audit",
            "claim_gate",
            "artifact_manifest",
            "evidence_graph",
            "cache_policy",
            "simulation_campaign",
            "release_evidence",
            "finite_json_no_network",
        ),
        allow_solver=False,
    )
    report, code = run_audit(config)
    assert report["scientific_pass"] is False
    assert report["empirical_pass"] is False
    assert report["network_enabled"] is False
    assert report["solver_executed"] is False
    ids = [step["id"] for step in report["steps"]]
    assert ids == list(config.step_ids)
    statuses = {step["id"]: step["status"] for step in report["steps"]}
    assert statuses["repository_state"] == "PASS"
    assert statuses["research_plan_audit"] == "PASS"
    assert statuses["claim_gate"] == "PASS"
    assert statuses["simulation_campaign"] == "PASS"
    assert statuses["finite_json_no_network"] == "PASS"
    assert "NOT_AVAILABLE" not in {step["status"] for step in report["steps"] if step["id"] in ("repository_state", "claim_gate")}
    assert code in {PASS, INCOMPLETE, FAILURE, BLOCKED, NOT_AVAILABLE}
    assert (config.output_dir / "research_cycle_audit.json").is_file()
    # No solver campaign script in recorded argv.
    joined = " ".join(" ".join(step.get("argv") or []) for step in report["steps"])
    assert "run_research_campaign.py" not in joined
    assert "--allow-network" not in joined


def test_cli_fixture_audit_writes_only_under_output_dir(tmp_path: Path):
    out = tmp_path / "cli-out"
    code = cli_main(
        [
            "audit",
            "--output-dir",
            str(out),
            "--repo-root",
            str(REPO_ROOT),
            "--no-surfaces",
            "--steps",
            "repository_state,finite_json_no_network",
            "--now",
            "2026-09-10T00:00:00+00:00",
        ]
    )
    assert code in {PASS, INCOMPLETE}
    assert (out / "research_cycle_audit.json").is_file()
    # The pack must not drop reports beside the repo root.
    assert not (REPO_ROOT / "research_cycle_audit.json").exists()


def test_unknown_step_id_is_blocked(tmp_path: Path):
    catalog = load_catalog(CATALOG)
    config = _config(tmp_path, catalog, step_ids=("not_a_real_step",))
    try:
        run_audit(config)
    except SafetyError as exc:
        assert "unknown step" in str(exc)
    else:
        raise AssertionError("expected SafetyError for unknown step id")
