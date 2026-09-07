from __future__ import annotations

import json

from tools.integration_state import github_source


def test_parse_final_commit_claim_matches_real_pr236_wording():
    body = "Final commit: `af3ac584277747ae29882d3f5a39af5c4a436f22`"
    assert github_source.parse_final_commit_claim(body) == "af3ac584277747ae29882d3f5a39af5c4a436f22"


def test_parse_final_commit_claim_absent_is_none():
    assert github_source.parse_final_commit_claim("no such claim here") is None
    assert github_source.parse_final_commit_claim(None) is None


def test_parse_integrated_pr_numbers():
    body = "Integrated #209, #210, and (#211). Also see #99999 which is out of range but still parsed."
    numbers = github_source.parse_integrated_pr_numbers(body)
    assert 209 in numbers and 210 in numbers and 211 in numbers


def test_pr_snapshot_from_dict_derives_claims_when_not_explicit():
    data = {
        "number": 236, "state": "open", "draft": False, "merged": False,
        "head_sha": "abc123", "body": "Final commit: `deadbeef00000000000000000000000000000000`. Integrated #100.",
    }
    snapshot = github_source.pr_snapshot_from_dict(data)
    assert snapshot.body_final_commit_claim == "deadbeef00000000000000000000000000000000"
    assert snapshot.integrated_pr_numbers == (100,)


def test_pr_snapshot_from_dict_explicit_fields_take_precedence():
    data = {
        "number": 236, "body": "Final commit: `deadbeef`.",
        "body_final_commit_claim": "explicit_override",
        "integrated_pr_numbers": [42],
    }
    snapshot = github_source.pr_snapshot_from_dict(data)
    assert snapshot.body_final_commit_claim == "explicit_override"
    assert snapshot.integrated_pr_numbers == (42,)


def test_load_pr_snapshot_from_file(tmp_path):
    path = tmp_path / "pr.json"
    path.write_text(json.dumps({"number": 1, "state": "open"}), encoding="utf-8")
    snapshot = github_source.load_pr_snapshot_from_file(path)
    assert snapshot.number == 1
    assert snapshot.state == "open"
