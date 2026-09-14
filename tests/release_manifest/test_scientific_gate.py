from tools.release_manifest.models import ScientificGateInput
from tools.release_manifest.scientific_gate import evaluate_scientific_gate


def test_none_input_is_insufficient_data_not_blocking():
    ev, blocking, findings = evaluate_scientific_gate(None)
    assert ev.value == "insufficient_data"
    assert blocking is False


def test_synthetic_pass_is_blocked_at_metadata_boundary():
    """A literal synthetic PASS cannot become release evidence."""
    gate_input = ScientificGateInput(data_mode="synthetic", verdict="PASS", evidence_kind=None)
    ev, blocking, findings = evaluate_scientific_gate(gate_input)
    assert ev.value == "blocked"
    assert blocking is True
    assert any("unverified_scientific_pass" in f for f in findings)


def test_not_supported_verdict_is_blocking():
    gate_input = ScientificGateInput(data_mode="empirical_local", verdict="NOT_SUPPORTED")
    ev, blocking, findings = evaluate_scientific_gate(gate_input)
    assert ev.value == "blocked"
    assert blocking is True


def test_inconclusive_is_insufficient_data_not_blocking():
    gate_input = ScientificGateInput(data_mode="empirical_local", verdict="INCONCLUSIVE")
    ev, blocking, findings = evaluate_scientific_gate(gate_input)
    assert ev.value == "insufficient_data"
    assert blocking is False


def test_formal_evidence_pass_is_still_blocked_without_artifact_verification():
    gate_input = ScientificGateInput(data_mode="empirical_local", verdict="PASS", evidence_kind="formal")
    ev, blocking, findings = evaluate_scientific_gate(gate_input)
    assert ev.value == "blocked"
    assert blocking is True
    assert findings
