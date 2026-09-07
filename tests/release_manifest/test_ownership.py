from tools.release_manifest.models import ChangedFileOwnership
from tools.release_manifest.ownership import find_duplicate_ownership, jaccard, ownership_to_dict


def test_jaccard_identical_sets():
    assert jaccard(["a", "b"], ["a", "b"]) == 1.0


def test_jaccard_disjoint_sets():
    assert jaccard(["a"], ["b"]) == 0.0


def test_jaccard_both_empty():
    assert jaccard([], []) == 0.0


def test_find_duplicate_ownership_detects_shared_file():
    a = ChangedFileOwnership(label="agent-a", changed_files=("shared.py", "a_only.py"))
    b = ChangedFileOwnership(label="agent-b", changed_files=("shared.py", "b_only.py"))
    findings = find_duplicate_ownership([a, b])
    assert len(findings) == 1
    assert findings[0]["shared_files"] == ["shared.py"]
    assert set(findings[0]["labels"]) == {"agent-a", "agent-b"}


def test_find_duplicate_ownership_no_overlap():
    a = ChangedFileOwnership(label="agent-a", changed_files=("a1.py",))
    b = ChangedFileOwnership(label="agent-b", changed_files=("b1.py",))
    assert find_duplicate_ownership([a, b]) == []


def test_ownership_to_dict():
    a = ChangedFileOwnership(label="agent-a", changed_files=("x.py",))
    assert ownership_to_dict([a]) == {"agent-a": ["x.py"]}
