"""Rule 4: preserve the nine epistemic labels exactly."""
from __future__ import annotations

from tools.research_record import epistemic
from tools.research_record.compiler import compile_record

NOW = "2026-01-01T00:00:00+00:00"

_EXACT_LABELS = {
    "engineering fact",
    "benchmark result",
    "synthetic demonstration",
    "empirical observation",
    "proxy inference",
    "formal statistical evidence",
    "hypothesis",
    "speculation",
    "unsupported claim",
}


def test_epistemic_labels_module_matches_the_exact_required_set():
    assert epistemic.EPISTEMIC_LABELS == frozenset(_EXACT_LABELS)


def test_each_label_is_reachable_end_to_end(manifest_factory):
    manifest = manifest_factory(
        {
            "test_runner": {"jobs": [{"name": "unit_tests", "status": "passed", "passed": 1, "failed": 0, "skipped": 0}]},
            "performance_benchmark": {"benchmarks": [{"name": "latency", "metric": "ms", "value": 1.0, "status": "pass"}]},
            "falsification": {
                "results": [
                    {"hypothesis_id": "HYP-SYN", "claim_class": "synthetic", "data_mode": "synthetic", "metric_type": "proxy_K", "metric_value": 1.0, "verdict": "INCONCLUSIVE"},
                    {"hypothesis_id": "HYP-EMP", "claim_class": "empirical", "data_mode": "empirical", "metric_type": "descriptive_delta", "metric_value": 1.0, "verdict": "INCONCLUSIVE"},
                    {"hypothesis_id": "HYP-PROXY", "claim_class": "proxy", "data_mode": "empirical", "metric_type": "proxy_K", "metric_value": 1.0, "verdict": "INCONCLUSIVE"},
                    {"hypothesis_id": "HYP-FORMAL", "claim_class": "empirical", "data_mode": "empirical", "metric_type": "bayes_factor", "metric_value": 12.0, "verdict": "PASS"},
                    {"hypothesis_id": "HYP-UNSUP", "claim_class": "unsupported", "data_mode": "empirical", "metric_type": "proxy_K", "metric_value": 1.0, "verdict": "INCONCLUSIVE"},
                    {"hypothesis_id": "HYP-NONE", "claim_class": "none", "data_mode": "none", "metric_type": "unset", "metric_value": None, "verdict": "unknown"},
                ]
            },
            "operator_notes": {"notes": [{"note": "unlabeled human note", "epistemic_label": None}, {"note": "explicit speculation", "epistemic_label": "speculation"}]},
        }
    )

    record = compile_record(manifest, now=NOW)
    labels_seen = {i["label"] for i in record["epistemic_classification"]["items"]}

    assert "engineering fact" in labels_seen        # from the test_runner job
    assert "benchmark result" in labels_seen        # from the performance benchmark
    assert "synthetic demonstration" in labels_seen  # HYP-SYN
    assert "empirical observation" in labels_seen    # HYP-EMP
    assert "proxy inference" in labels_seen          # HYP-PROXY
    assert "formal statistical evidence" in labels_seen  # HYP-FORMAL
    assert "hypothesis" in labels_seen               # HYP-NONE
    assert "unsupported claim" in labels_seen        # HYP-UNSUP and/or the unlabeled operator note
    assert "speculation" in labels_seen              # the explicit operator note

    # Every label used is one of the exact nine strings.
    assert labels_seen <= _EXACT_LABELS


def test_unlabeled_operator_note_defaults_to_unsupported_claim(manifest_factory):
    manifest = manifest_factory({"operator_notes": {"notes": [{"note": "an unverified assertion", "epistemic_label": "not_a_real_label"}]}})
    record = compile_record(manifest, now=NOW)
    note_item = next(i for i in record["epistemic_classification"]["items"] if i["source"] == "operator_notes")
    assert note_item["label"] == "unsupported claim"
