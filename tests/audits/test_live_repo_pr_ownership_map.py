"""Structural, offline checks for the dated repository/PR audit artifact."""

from __future__ import annotations

import json
import re
from pathlib import Path, PurePosixPath, PureWindowsPath

ROOT = Path(__file__).resolve().parents[2]
AUDIT_PATH = ROOT / "docs" / "audits" / "live_repo_pr_ownership_map.json"
SCHEMA_PATH = ROOT / "docs" / "audits" / "live_repo_pr_ownership_map.schema.json"


def _reject_constant(value: str):
    raise ValueError(f"non-finite JSON constant: {value}")


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"), parse_constant=_reject_constant)


def _pr_map(document: dict) -> dict[int, dict]:
    return {pr["number"]: pr for pr in document["pull_requests"]}


def _assert_relative_repo_path(value: str) -> None:
    assert value and "\x00" not in value
    assert not PurePosixPath(value).is_absolute()
    assert not PureWindowsPath(value).is_absolute()
    assert not PureWindowsPath(value).drive
    assert ".." not in PurePosixPath(value).parts


def test_snapshot_is_finite_deterministic_json_with_required_structure():
    raw = AUDIT_PATH.read_text(encoding="utf-8")
    document = _load(AUDIT_PATH)
    canonical = json.dumps(
        document, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2
    ) + "\n"
    assert raw == canonical
    required = _load(SCHEMA_PATH)["required"]
    assert set(required) <= document.keys()
    assert document["snapshot_kind"] == "timestamped_read_only_repository_and_pull_request_audit"
    assert document["captured_at_utc"].endswith("Z")
    assert document["repository"]["posture"] == "HOLD / SYNTHETIC_ONLY"


def test_pr_ids_are_unique_and_match_the_open_inventory():
    document = _load(AUDIT_PATH)
    numbers = [pr["number"] for pr in document["pull_requests"]]
    assert len(numbers) == len(set(numbers))
    assert numbers == sorted(numbers)
    assert numbers == document["scope"]["open_pr_numbers"]
    assert document["scope"]["open_pr_count"] == len(numbers)
    assert all(isinstance(number, int) and number > 0 for number in numbers)


def test_pr_records_and_readiness_summary_match_the_schema_and_inventory():
    document = _load(AUDIT_PATH)
    schema = _load(SCHEMA_PATH)
    required = set(schema["$defs"]["pull_request"]["required"])
    for pr in document["pull_requests"]:
        assert required <= pr.keys()

    counts = document["readiness_summary"]["counts"]
    observed_counts = {
        state: sum(pr["readiness"]["state"] == state for pr in document["pull_requests"])
        for state in counts
    }
    assert counts == observed_counts
    assert document["readiness_summary"]["merge_ready_count"] == observed_counts.get("ready", 0)
    assert document["ownership_summary"]["observed_failed_pr_count"] == sum(
        pr["ci"]["observed_state"] == "fail" for pr in document["pull_requests"]
    )


def test_pr_sha_fields_and_statuses_use_declared_vocabulary():
    document = _load(AUDIT_PATH)
    schema = _load(SCHEMA_PATH)
    assert re.fullmatch(schema["$defs"]["sha"]["pattern"], document["repository"]["main_sha"])
    pr_schema = schema["$defs"]["pull_request"]["properties"]
    sha_pattern = re.compile(schema["$defs"]["sha"]["pattern"])
    required_states = set(pr_schema["ci"]["properties"]["required_check_state"]["enum"])
    observed_states = set(pr_schema["ci"]["properties"]["observed_state"]["enum"])
    readiness_states = set(pr_schema["readiness"]["properties"]["state"]["enum"])

    for pr in document["pull_requests"]:
        assert sha_pattern.fullmatch(pr["base"]["sha"])
        assert sha_pattern.fullmatch(pr["base"]["live_main_sha"])
        assert sha_pattern.fullmatch(pr["head"]["sha"])
        assert pr["state"] in {"open", "closed"}
        assert pr["ci"]["required_check_state"] in required_states
        assert pr["ci"]["observed_state"] in observed_states
        assert pr["readiness"]["state"] in readiness_states
        assert pr["changed_path_count"] == len(pr["changed_paths"])
        assert len(pr["changed_paths"]) == len(set(pr["changed_paths"]))
        for path in pr["changed_paths"]:
            _assert_relative_repo_path(path)

        if pr["ci"]["required_check_state"] == "unknown":
            assert pr["ci"]["required_check_reason"].strip()
        if pr["ci"]["observed_state"] == "unknown":
            assert (pr["ci"].get("no_check_runs_reason") or "").strip() or (
                pr["ci"].get("observed_state_reason") or ""
            ).strip()


def test_exact_path_collisions_reference_competing_open_pr_changes():
    document = _load(AUDIT_PATH)
    prs = _pr_map(document)
    seen_paths = set()
    for collision in document["path_collisions"]:
        path = collision["path"]
        _assert_relative_repo_path(path)
        assert path not in seen_paths
        seen_paths.add(path)
        numbers = collision["pr_numbers"]
        assert len(numbers) >= 2
        assert len(numbers) == len(set(numbers))
        assert numbers == sorted(numbers)
        assert all(number in prs and path in prs[number]["changed_paths"] for number in numbers)
        assert collision["kind"] == "exact_changed_path_overlap"
        assert collision["is_git_merge_conflict"] is False


def test_unknown_is_explicit_and_never_implicitly_passes():
    document = _load(AUDIT_PATH)
    for pr in document["pull_requests"]:
        if pr["ci"]["required_check_state"] == "unknown":
            assert pr["ci"]["required_check_reason"]
            assert pr["ci"]["required_check_state"] != "pass"
        if pr["ci"]["observed_state"] == "unknown":
            assert pr["ci"].get("no_check_runs_reason") or pr["ci"].get("observed_state_reason")
            assert pr["ci"]["observed_state"] != "pass"

    if document["required_check_configuration"]["state"] == "unknown":
        assert document["required_check_configuration"]["reason"]


def test_schema_keeps_unknown_optional_fields_forward_compatible():
    schema = _load(SCHEMA_PATH)
    assert schema["additionalProperties"] is True
    assert schema["$defs"]["pull_request"]["additionalProperties"] is True
    assert schema["$defs"]["pull_request"]["properties"]["ci"]["additionalProperties"] is True

    document = _load(AUDIT_PATH)
    future_record = dict(document["pull_requests"][0])
    future_record["future_observation"] = {"state": "unknown"}
    assert future_record["future_observation"]["state"] == "unknown"


def test_audit_artifact_paths_do_not_overlap_open_pr_ownership():
    document = _load(AUDIT_PATH)
    audit_paths = {
        "docs/audits/live_repo_pr_ownership_map.json",
        "docs/audits/live_repo_pr_ownership_map.schema.json",
        "docs/audits/live_repo_pr_ownership_map.md",
        "tests/audits/test_live_repo_pr_ownership_map.py",
    }
    open_pr_paths = {
        path for pr in document["pull_requests"] for path in pr["changed_paths"]
    }
    assert audit_paths.isdisjoint(open_pr_paths)


def test_pr_405_merge_and_interface_are_explicitly_captured():
    document = _load(AUDIT_PATH)
    pr405 = document["pr_405"]
    assert pr405["number"] == 405
    assert pr405["state"] == "closed"
    assert pr405["merged"] is True
    assert re.fullmatch(r"[0-9a-f]{40}", pr405["base_sha"])
    assert re.fullmatch(r"[0-9a-f]{40}", pr405["head_sha"])
    assert re.fullmatch(r"[0-9a-f]{40}", pr405["merge_commit_sha"])
    assert pr405["interface"]["package"] == "analysis.binomial_planning"
    assert "wilson_score_interval" in pr405["interface"]["exports"]
    assert "unavailable_zero_trials" in pr405["interface"]["zero_trials_behavior"]


def test_unknown_optional_data_is_not_guessed_from_path_or_title():
    document = _load(AUDIT_PATH)
    for pr in document["pull_requests"]:
        if pr["mergeability"]["conflicting_paths"] is None:
            assert pr["mergeability"]["conflict_path_detail"].strip()
        if pr["mergeability"]["api_mergeable"] is None:
            assert pr["mergeability"]["api_state"] is None or pr["mergeability"]["conflict_path_detail"].strip()
