from __future__ import annotations

from tools.integration_reconciliation import duplicate_detection


def test_no_duplicates_for_disjoint_files():
    findings = duplicate_detection.detect_possible_duplicates({"a": ("x.py",), "b": ("y.py",)})
    assert findings == []


def test_duplicate_flagged_above_threshold():
    findings = duplicate_detection.detect_possible_duplicates(
        {"a": ("x.py", "y.py", "z.py"), "b": ("x.py", "y.py")}, threshold=0.6,
    )
    assert len(findings) == 1
    assert findings[0]["work_order_a"] == "a"
    assert findings[0]["work_order_b"] == "b"
    assert findings[0]["jaccard_similarity"] == round(2 / 3, 3)


def test_stacked_pairs_are_excluded_even_if_similar():
    findings = duplicate_detection.detect_possible_duplicates(
        {"a": ("x.py",), "b": ("x.py",)}, stacked_pairs=frozenset({("a", "b")}), threshold=0.5,
    )
    assert findings == []


def test_none_changed_files_are_skipped():
    findings = duplicate_detection.detect_possible_duplicates({"a": None, "b": ("x.py",)})
    assert findings == []


def test_detect_superseded_true_case():
    findings = duplicate_detection.detect_superseded({("a", "b"): True})
    assert findings == [{
        "superseded_work_order": "a", "superseded_by_work_order": "b",
        "evidence": "a's branch is a git ancestor of b's branch",
    }]


def test_detect_superseded_false_case_produces_no_finding():
    findings = duplicate_detection.detect_superseded({("a", "b"): False})
    assert findings == []


def test_detect_superseded_none_case_produces_no_finding():
    findings = duplicate_detection.detect_superseded({("a", "b"): None})
    assert findings == []
