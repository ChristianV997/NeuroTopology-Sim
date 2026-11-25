import pytest
from pathlib import Path
from dataset_acquisition.store import validate_target_root, TargetRootError
from workflows.html_validation import validate_html_report_pack

def test_validate_target_root_accepts_windows_paths():
    """
    Regression test for a defect where validate_target_root rejected Windows backslashes
    because it used string comparison against POSIX prefixes ('outputs/', 'data/').
    """
    resolved = validate_target_root("outputs\\report_packs\\html-int-guardrail\\html")
    assert "outputs" in resolved.parts
    assert "html-int-guardrail" in resolved.parts

def test_validate_target_root_rejects_escape_segments():
    """Ensure we didn't weaken the security guardrails."""
    with pytest.raises(TargetRootError, match="must not contain '\\.\\.'"):
        validate_target_root("outputs\\..\\secrets")

class DummyPack:
    def __init__(self, output_root: str):
        self.report_pack_id = "test-pack"
        self.dataset_id = "test-dataset"
        self.limitations = ["test"]
        self.blocked_interpretations = ["test"]
        self.provenance = "test"
        self.output_root = output_root

def test_html_validation_accepts_windows_paths():
    """
    Regression test for workflows.html_validation rule 5.
    """
    pack = DummyPack("outputs\\report_packs\\html-int-guardrail\\html")
    errors = validate_html_report_pack(pack)
    assert not any("rule 5" in e for e in errors), f"Unexpected errors: {errors}"

def test_html_validation_rejects_escape_segments():
    pack = DummyPack("outputs\\..\\secrets")
    errors = validate_html_report_pack(pack)
    assert any("rule 5" in e for e in errors), "Failed to block path escape!"
