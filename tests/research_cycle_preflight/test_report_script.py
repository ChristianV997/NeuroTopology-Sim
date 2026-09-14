"""Tests for scripts/validate_research_cycle_preflight.py's report
contract: a machine-readable, deterministic, finite self-check report,
plus the single-request mode used for a real preflight run.
"""
from __future__ import annotations

import json

from scripts.validate_research_cycle_preflight import _resolve_prior_run_dir, _self_check_report


def test_self_check_report_has_the_required_evidence_class():
    report = _self_check_report(now="2026-01-01T00:00:00+00:00")
    assert report["evidence_class"] == "research_cycle_preflight_self_check"


def test_self_check_report_covers_every_fixture():
    from .conftest import ALL_FIXTURE_NAMES

    report = _self_check_report(now="2026-01-01T00:00:00+00:00")
    fixture_names = {case["fixture"] for case in report["cases"]}
    assert fixture_names == set(ALL_FIXTURE_NAMES)


def test_self_check_report_matches_expected_cases():
    from .conftest import EXPECTED_CASES

    report = _self_check_report(now="2026-01-01T00:00:00+00:00")
    by_fixture = {case["fixture"]: case for case in report["cases"]}
    for name, (operational, scientific, cleared) in EXPECTED_CASES.items():
        case = by_fixture[name]
        assert case["operational_readiness"] == operational
        assert case["scientific_admissibility"] == scientific
        assert case["cleared_for_execution"] is cleared


def test_self_check_report_is_finite_json():
    # allow_nan=False raises on an actual non-finite float; a successful
    # dump is the real finiteness proof (a crude text search for "NaN"
    # would misfire on the non_finite_artifacts case's own diagnostic
    # message, which legitimately names the token it rejected).
    report = _self_check_report(now="2026-01-01T00:00:00+00:00")
    text = json.dumps(report, sort_keys=True, allow_nan=False)
    assert json.loads(text) == report


def test_self_check_report_is_deterministic_given_the_same_now():
    report1 = _self_check_report(now="2026-01-01T00:00:00+00:00")
    report2 = _self_check_report(now="2026-01-01T00:00:00+00:00")
    assert json.dumps(report1, sort_keys=True) == json.dumps(report2, sort_keys=True)
    assert report1["report_sha256"] == report2["report_sha256"]


def test_self_check_checksum_excludes_itself_from_its_own_input():
    import hashlib

    report = _self_check_report(now="2026-01-01T00:00:00+00:00")
    stripped = {k: v for k, v in report.items() if k != "report_sha256"}
    expected = hashlib.sha256(json.dumps(stripped, sort_keys=True, allow_nan=False).encode("utf-8")).hexdigest()
    assert report["report_sha256"] == expected


def test_resolve_prior_run_dir_only_touches_declared_key():
    request = {"plan": {"plan_id": "x"}}
    assert _resolve_prior_run_dir(request) == request

    with_prior_run = {"plan": {"plan_id": "x"}, "prior_run_dir": "partial_run"}
    resolved = _resolve_prior_run_dir(with_prior_run)
    assert resolved["prior_run_dir"].endswith("partial_run")
    assert resolved["plan"] == {"plan_id": "x"}
