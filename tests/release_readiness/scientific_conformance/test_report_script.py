"""Tests for scripts/validate_scientific_release_conformance.py's report
contract: requirement 8 (machine-readable report with
evidence_class=scientific_release_conformance) plus finite-JSON and
determinism checks on the script's own output.
"""
from __future__ import annotations

import json

from scripts.validate_scientific_release_conformance import build_report


def test_report_has_the_required_evidence_class():
    report = build_report(now="2026-01-01T00:00:00+00:00")
    assert report["evidence_class"] == "scientific_release_conformance"


def test_report_is_conformant_against_this_suites_own_fixtures():
    report = build_report(now="2026-01-01T00:00:00+00:00")
    assert report["conformant"] is True
    assert all(report["invariants"].values())


def test_report_is_finite_json():
    report = build_report(now="2026-01-01T00:00:00+00:00")
    text = json.dumps(report, sort_keys=True, allow_nan=False)
    assert "NaN" not in text
    assert "Infinity" not in text
    assert json.loads(text) == report


def test_report_is_deterministic_given_the_same_now():
    report1 = build_report(now="2026-01-01T00:00:00+00:00")
    report2 = build_report(now="2026-01-01T00:00:00+00:00")
    assert json.dumps(report1, sort_keys=True) == json.dumps(report2, sort_keys=True)
    assert report1["report_sha256"] == report2["report_sha256"]


def test_report_checksum_excludes_itself_from_its_own_input():
    report = build_report(now="2026-01-01T00:00:00+00:00")
    import hashlib

    stripped = {k: v for k, v in report.items() if k != "report_sha256"}
    expected = hashlib.sha256(json.dumps(stripped, sort_keys=True, allow_nan=False).encode("utf-8")).hexdigest()
    assert report["report_sha256"] == expected


def test_omitted_now_only_changes_generated_at_and_checksum():
    report1 = build_report()
    report2 = build_report()
    volatile = {"generated_at", "report_sha256"}
    stable1 = {k: v for k, v in report1.items() if k not in volatile}
    stable2 = {k: v for k, v in report2.items() if k not in volatile}
    assert stable1 == stable2
