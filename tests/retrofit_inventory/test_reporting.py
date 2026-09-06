"""Phase 4 reporting envelope tests (offline, frozen clock)."""

from __future__ import annotations

import ast
import json
from datetime import datetime, timezone
from pathlib import Path

from tools.retrofit_inventory.models import (
    ARTIFACT_LABEL_EMPIRICAL,
    OverlapOrDuplicateFinding,
)
from tools.retrofit_inventory.reporting import (
    DEFAULT_OUTPUT_RELATIVE,
    REPORT_FILENAMES,
    REPORT_KIND_SCIENCE_RISK,
    STATUS_ERROR,
    STATUS_INCOMPLETE,
    STATUS_OK,
    build_report_bundle,
    common_limitations,
    dump_json,
    format_timestamp,
    write_report_bundle,
)
from tools.retrofit_inventory.scanner import build_inventory_snapshot
from tools.retrofit_inventory.tool_sources import load_tool_sources
from tools.retrofit_inventory.validators import (
    EXPECTED_REAL_TOOL_SOURCE_COUNT,
    FORBIDDEN_SCIENTIFIC_CLAIM_STATUSES,
    INVENTORY_CLAIM_STATUS_NOT_EVIDENCE,
    NETWORK_IMPORT_DENYLIST,
    collect_forbidden_import_violations,
    inventory_scientific_claim_status,
    validate_no_network_imports,
)

from .conftest import REPO_ROOT, make_artifact, make_file_entry, make_snapshot

FROZEN = datetime(2026, 9, 6, 2, 24, 0, tzinfo=timezone.utc)
FROZEN_ISO = format_timestamp(_now=FROZEN)
REPORTING_PATH = (
    Path(__file__).resolve().parents[2] / "tools" / "retrofit_inventory" / "reporting.py"
)
SCHEMA_PATH = (
    Path(__file__).resolve().parents[2]
    / "configs"
    / "retrofit_inventory"
    / "report_schema.json"
)


def _bundle_from_snapshot(snapshot, **kwargs):
    return build_report_bundle(
        snapshot.repo_root,
        snapshot=snapshot,
        tool_rows=kwargs.pop("tool_rows", load_tool_sources(REPO_ROOT)),
        tool_sources_root=kwargs.pop("tool_sources_root", REPO_ROOT),
        _now=kwargs.pop("_now", FROZEN),
        scan_text_contents=kwargs.pop("scan_text_contents", False),
        **kwargs,
    )


def _all_reports(bundle):
    return list(bundle["reports"].values())


def test_frozen_clock_is_used_on_every_envelope():
    snapshot = make_snapshot()
    bundle = _bundle_from_snapshot(snapshot)
    assert bundle["timestamp"] == FROZEN_ISO
    for report in _all_reports(bundle):
        assert report["timestamp"] == FROZEN_ISO


def test_six_filenames_and_sort_keys_stable_across_two_builds():
    snapshot = make_snapshot()
    first = _bundle_from_snapshot(snapshot)
    second = _bundle_from_snapshot(snapshot)
    assert list(first["reports"]) == list(REPORT_FILENAMES)
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    for name in REPORT_FILENAMES:
        assert dump_json(first["reports"][name]) == dump_json(second["reports"][name])


def test_write_report_bundle_writes_only_six_files(tmp_path: Path):
    bundle = _bundle_from_snapshot(make_snapshot())
    written = write_report_bundle(bundle, tmp_path)
    names = sorted(path.name for path in written)
    assert names == sorted(REPORT_FILENAMES)
    assert sorted(path.name for path in tmp_path.iterdir()) == names
    for path in written:
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["timestamp"] == FROZEN_ISO
        text = path.read_text(encoding="utf-8")
        assert text == dump_json(payload)


def test_build_report_bundle_can_write_via_output_dir(tmp_path: Path):
    out = tmp_path / "reports"
    bundle = _bundle_from_snapshot(make_snapshot(), output_dir=out)
    assert bundle["status"] == STATUS_OK
    assert sorted(path.name for path in out.iterdir()) == sorted(REPORT_FILENAMES)


def test_envelope_required_fields_and_limitations():
    bundle = _bundle_from_snapshot(make_snapshot())
    required = {
        "timestamp",
        "repository_commit",
        "source_hashes",
        "status",
        "warnings",
        "errors",
        "limitations",
        "next_actions",
    }
    assert required.issubset(bundle)
    for report in _all_reports(bundle):
        assert required.issubset(report)
        assert report["repository_commit"] == "a" * 40
        assert report["source_hashes"]["snapshot_digest"]
        assert report["source_hashes"]["tool_sources_yaml"]
        assert report["source_hashes"]["report_schema_version"] == "0.1"
        for limitation in common_limitations():
            assert limitation in report["limitations"]
        assert any("not scientific evidence" in item.lower() for item in report["limitations"])


def test_repository_inventory_copies_snapshot_slices():
    snapshot = make_snapshot(
        files=[make_file_entry("src/app.py"), make_file_entry("README.md")],
        overlaps=[
            OverlapOrDuplicateFinding(
                paths=["a/app.py", "b/app.py"],
                reason="same basename 'app.py' in multiple top-level directories",
            )
        ],
    )
    report = _bundle_from_snapshot(snapshot)["reports"]["repository_inventory.json"]
    assert [row["path"] for row in report["files"]] == ["README.md", "src/app.py"]
    assert report["overlaps"]
    assert report["governance"] == []
    assert report["worktrees_and_branches"] == []


def test_artifact_inventory_keeps_heuristic_labels_and_denies_pass():
    snapshot = make_snapshot(
        artifacts=[
            make_artifact("artifacts/synthetic/a.json", label="synthetic"),
            make_artifact("artifacts/empirical/b.json", label=ARTIFACT_LABEL_EMPIRICAL),
            make_artifact("outputs/c.json", label="unknown", schema_id=None),
        ]
    )
    report = _bundle_from_snapshot(snapshot)["reports"]["artifact_inventory.json"]
    assert report["label_counts"] == {"synthetic": 1, "empirical": 1, "unknown": 1}
    assert report["empirical_label_is_pass"] is False
    assert "PASS" in report["label_policy"]
    labels = {row["path"]: row["label"] for row in report["artifacts"]}
    assert labels["artifacts/empirical/b.json"] == ARTIFACT_LABEL_EMPIRICAL


def test_tool_admission_has_fifteen_real_rows():
    bundle = _bundle_from_snapshot(make_snapshot())
    report = bundle["reports"]["tool_admission_inventory.json"]
    assert report["admission_summary"]["count"] == EXPECTED_REAL_TOOL_SOURCE_COUNT
    assert len(report["tools"]) == 15
    assert [row["id"] for row in report["tools"]] == sorted(
        row["id"] for row in report["tools"]
    )
    notebooklm = next(row for row in report["tools"] if row["id"] == "notebooklm-mcp")
    assert notebooklm["integration_mode"] == "experimental"
    assert notebooklm["adoption_recommendation"] == "experimental_only"


def test_ownership_report_includes_overlaps_and_claimed_owners():
    snapshot = make_snapshot(
        overlaps=[
            OverlapOrDuplicateFinding(paths=["core/x.py", "apps/x.py"], reason="dual-root")
        ],
        report_fields={
            "claimed_owners": [
                {"path": "core/x.py", "owner": "lead"},
                {"path": "core/x.py", "owner": "qa"},
            ]
        },
    )
    report = _bundle_from_snapshot(snapshot)["reports"]["ownership_collision_report.json"]
    assert report["overlaps"]
    assert report["claimed_owners"]
    assert report["status"] == STATUS_ERROR
    assert any("claimed owners" in item for item in report["errors"])
    assert any("claimed owners" in item for item in report["duplicate_ownership_findings"])


def test_priority_report_is_engineering_only_not_scientific():
    report = _bundle_from_snapshot(make_snapshot())["reports"]["retrofit_priority_report.json"]
    assert report["ranking_kind"] == "engineering_only"
    assert "NOT a scientific ranking" in report["ranking_disclaimer"]
    priorities = [row["engineering_priority"] for row in report["candidates"]]
    assert priorities == list(range(1, len(priorities) + 1))
    consider = [row for row in report["candidates"] if row["adoption_recommendation"] == "consider"]
    reject_or_defer = [
        row
        for row in report["candidates"]
        if row["adoption_recommendation"] in {"defer", "reject"}
    ]
    if consider and reject_or_defer:
        assert consider[0]["engineering_priority"] < reject_or_defer[-1]["engineering_priority"]
    assert all(row["ranking_kind"] == "engineering_only" for row in report["candidates"])


def test_scientific_claim_risk_never_pass_and_not_evidence():
    snapshot = make_snapshot(
        artifacts=[make_artifact("artifacts/empirical/x.json", label=ARTIFACT_LABEL_EMPIRICAL)]
    )
    report = _bundle_from_snapshot(snapshot)["reports"]["scientific_claim_risk_report.json"]
    assert report["scientific_claim_status"] == INVENTORY_CLAIM_STATUS_NOT_EVIDENCE
    assert report["scientific_claim_status"] not in FORBIDDEN_SCIENTIFIC_CLAIM_STATUSES
    assert report["inventory_is_evidence"] is False
    assert report["empirical_label_is_pass"] is False
    assert report["k_gt_100_gate"] == "out_of_scope"
    assert report["scientific_pass_gate"] == "out_of_scope"
    assert report["scientific_assertions"]["never_pass"] is True
    assert report["scientific_assertions"]["scientific_claim_status"] == "not_evidence"
    dumped = json.dumps(report, sort_keys=True)
    assert inventory_scientific_claim_status(snapshot) == "not_evidence"
    for forbidden in FORBIDDEN_SCIENTIFIC_CLAIM_STATUSES:
        assert report["scientific_claim_status"] != forbidden
    assert "out of scope" in " ".join(report["statements"]).lower()
    assert "not evidence" in " ".join(report["statements"]).lower()
    assert '"scientific_claim_status": "PASS"' not in dumped
    assert report["report_kind"] == REPORT_KIND_SCIENCE_RISK


def test_validation_errors_set_status_error_and_keep_dirty_data():
    snapshot = make_snapshot(
        artifacts=[make_artifact("artifacts/x.json", label="proven")]
    )
    bundle = _bundle_from_snapshot(snapshot)
    assert bundle["status"] == STATUS_ERROR
    report = bundle["reports"]["artifact_inventory.json"]
    assert report["status"] == STATUS_ERROR
    assert report["errors"]
    assert report["artifacts"][0]["label"] == "proven"
    assert not any(row["label"] == "unknown" for row in report["artifacts"])


def test_missing_tool_sources_does_not_invent_registry(tmp_path: Path):
    snapshot = make_snapshot(repo_root=str(tmp_path))
    bundle = build_report_bundle(
        tmp_path,
        snapshot=snapshot,
        tool_sources_root=tmp_path,
        _now=FROZEN,
        scan_text_contents=False,
    )
    assert bundle["status"] == STATUS_ERROR
    tools_report = bundle["reports"]["tool_admission_inventory.json"]
    assert tools_report["tools"] == []
    assert tools_report["admission_summary"]["count"] == 0
    assert any("tool sources YAML not found" in item for item in bundle["errors"])


def test_pass_in_report_fields_fails_closed_and_stays_not_evidence():
    snapshot = make_snapshot(
        report_fields={"scientific_claim_status": "PASS"}
    )
    bundle = _bundle_from_snapshot(snapshot)
    assert bundle["status"] == STATUS_ERROR
    assert any("PASS" in item for item in bundle["errors"])
    science = bundle["reports"]["scientific_claim_risk_report.json"]
    assert science["scientific_claim_status"] == INVENTORY_CLAIM_STATUS_NOT_EVIDENCE
    assert science["scientific_claim_status"] not in FORBIDDEN_SCIENTIFIC_CLAIM_STATUSES


def test_offline_false_is_ignored_with_warning():
    bundle = _bundle_from_snapshot(make_snapshot(), offline=False)
    assert any("offline=False" in item for item in bundle["warnings"])
    assert bundle["status"] == STATUS_OK


def test_tiny_repo_loads_real_yaml_via_tool_sources_root(tiny_repo: Path):
    bundle = build_report_bundle(
        tiny_repo,
        tool_sources_root=REPO_ROOT,
        _now=FROZEN,
    )
    assert bundle["status"] == STATUS_OK
    assert bundle["errors"] == []
    tools = bundle["reports"]["tool_admission_inventory.json"]
    assert tools["loaded_from_real_yaml"] is True
    assert tools["admission_summary"]["count"] == 15


def test_tiny_repo_bundle_is_ok(tiny_repo: Path):
    snap = build_inventory_snapshot(tiny_repo)
    bundle = build_report_bundle(
        tiny_repo,
        snapshot=snap,
        tool_rows=load_tool_sources(REPO_ROOT),
        tool_sources_root=REPO_ROOT,
        _now=FROZEN,
        scan_text_contents=True,
    )
    assert bundle["status"] == STATUS_OK
    assert bundle["errors"] == []
    assert bundle["repository_commit"] == snap.commit_sha
    repo_report = bundle["reports"]["repository_inventory.json"]
    assert repo_report["files"]
    labeled = [
        row
        for row in bundle["reports"]["artifact_inventory.json"]["artifacts"]
        if "synthetic" in row["path"]
    ]
    assert labeled
    assert all(row["label"] == "synthetic" for row in labeled)


def test_reporting_module_has_no_network_or_marketos_imports():
    errors = validate_no_network_imports(extra_paths=[REPORTING_PATH])
    assert errors == [], errors
    assert collect_forbidden_import_violations(REPORTING_PATH) == []
    tree = ast.parse(REPORTING_PATH.read_text(encoding="utf-8"), filename=str(REPORTING_PATH))
    imported = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
    for module in imported:
        root = module.split(".", 1)[0]
        assert root not in NETWORK_IMPORT_DENYLIST
        assert module not in NETWORK_IMPORT_DENYLIST
        assert root.lower() != "marketos"


def test_report_schema_file_exists_and_lists_six_kinds():
    assert SCHEMA_PATH.is_file()
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    kinds = schema["$defs"]["envelope"]["properties"]["report_kind"]["enum"]
    assert kinds == [
        name[: -len(".json")] if name.endswith(".json") else name
        for name in REPORT_FILENAMES
    ]
    reports = schema["$defs"]["bundle"]["properties"]["reports"]["required"]
    assert reports == list(REPORT_FILENAMES)


def test_default_output_is_gitignored_artifacts_dir():
    assert DEFAULT_OUTPUT_RELATIVE == "artifacts/retrofit_inventory"
    gitignore = (Path(__file__).resolve().parents[2] / ".gitignore").read_text(
        encoding="utf-8"
    )
    assert "artifacts/" in gitignore


def test_incomplete_when_snapshot_scan_fails(tmp_path: Path):
    missing = tmp_path / "does-not-exist"
    bundle = build_report_bundle(
        missing,
        tool_rows=[],
        _now=FROZEN,
        scan_text_contents=False,
    )
    assert bundle["status"] in {STATUS_ERROR, STATUS_INCOMPLETE}
    assert bundle["reports"]["repository_inventory.json"]["files"] == []
    assert bundle["reports"]["tool_admission_inventory.json"]["tools"] == []
    assert any("does not exist" in item for item in bundle["errors"])
