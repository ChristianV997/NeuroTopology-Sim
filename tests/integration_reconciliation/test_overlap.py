from __future__ import annotations

from tools.integration_reconciliation import overlap


def test_no_overlap_between_disjoint_file_sets():
    result = overlap.compute_overlaps({"a": ("x.py",), "b": ("y.py",)})
    assert result == {}


def test_overlap_detected_for_shared_file():
    result = overlap.compute_overlaps({"a": ("shared.py", "a_only.py"), "b": ("shared.py", "b_only.py")})
    assert result == {"a|b": ["shared.py"]}


def test_none_changed_files_are_skipped_not_treated_as_no_overlap():
    result = overlap.compute_overlaps({"a": None, "b": ("shared.py",), "c": ("shared.py",)})
    assert "a|b" not in result
    assert "a|c" not in result
    assert result == {"b|c": ["shared.py"]}


def test_three_way_overlap_reports_each_pair():
    result = overlap.compute_overlaps({
        "a": ("shared.py",), "b": ("shared.py",), "c": ("shared.py",),
    })
    assert set(result) == {"a|b", "a|c", "b|c"}


def test_empty_input_produces_empty_result():
    assert overlap.compute_overlaps({}) == {}
