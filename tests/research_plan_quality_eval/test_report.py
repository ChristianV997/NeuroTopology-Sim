from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from tools.research_plan_quality_eval.errors import InsufficientEvaluationSetError, ManifestError
from tools.research_plan_quality_eval.harness import DEFAULT_MANIFEST, NOT_MEASURED, build_report, to_report_json
from tools.research_plan_quality_eval.splits import DEVELOPMENT

from .conftest import rewrite_json


def _strict(text: str):
    def _reject(token):
        raise ValueError(f"non-finite constant {token}")

    return json.loads(text, parse_constant=_reject)


def _without_labels(report: dict) -> dict:
    return {k: v for k, v in report.items() if k != "label_consistency"}


def test_report_is_byte_identical_across_repeated_runs():
    assert to_report_json(build_report()) == to_report_json(build_report())


def test_report_is_strict_finite_json():
    text = to_report_json(build_report())
    assert _strict(text)["schema_version"] == "NTS.ResearchPlanEvalReport.v1"


def test_report_records_manifest_and_every_plan_hash():
    report = build_report()
    manifest_bytes = Path(DEFAULT_MANIFEST).read_bytes()
    assert report["fixture_set"]["manifest_sha256"] == hashlib.sha256(manifest_bytes).hexdigest()
    for entry in report["fixture_set"]["plans"]:
        plan_file = DEFAULT_MANIFEST.parent / "plans" / f"{entry['fixture_id'].split('fx-v1-')[1]}.json"
        assert entry["plan_sha256"] == hashlib.sha256(plan_file.read_bytes()).hexdigest()


def test_report_records_rubric_identity_and_configuration_fingerprint():
    rubric = build_report()["rubric"]
    assert rubric["dimension_count"] == 20
    assert len(rubric["dimensions_sha256"]) == 64
    assert len(rubric["source_sha256"]) == 64
    assert len(rubric["configuration_fingerprint"]) == 64


def test_report_states_its_evidence_class_and_what_was_not_measured():
    report = build_report()
    assert report["rubric_evidence_class"] == "research_plan_audit"
    assert report["harness_evidence_class"] == "software_validation_on_synthetic_fixtures"
    assert report["fixture_set"]["synthetic"] is True
    assert set(NOT_MEASURED) <= set(report["not_measured"])
    assert "criterion_leakage_rate" in report["not_measured"]
    assert any("not human agreement" in line for line in report["limitations"])


def test_label_consistency_declares_no_human_agreement():
    consistency = build_report()["label_consistency"]
    assert consistency["human_agreement"] is None
    assert consistency["independent_adjudication"] is False
    assert consistency["adjudication"]["status"] == "synthetic_author_expectation"
    assert consistency["expectation_matches"] == 10
    assert consistency["expectation_mismatches"] == []


def test_report_contains_no_criterion_leakage_number():
    report = build_report()
    flattened = json.dumps(report, sort_keys=True)
    assert "criterion_leakage_rate\":" not in flattened
    assert report["leakage"]["fraction_label"].startswith("held-out plans with a lexical cross-split duplicate")


def test_rubric_outcomes_are_identical_with_labels_removed_or_corrupted(copy_fixture_tree):
    clean = build_report(include_label_consistency=False)
    manifest_path = copy_fixture_tree()
    (manifest_path.parent / "labels.json").write_text("garbage", encoding="utf-8")
    corrupted = build_report(manifest_path, include_label_consistency=False)
    assert _without_labels(corrupted) == _without_labels(clean)
    with pytest.raises(ManifestError):
        build_report(manifest_path, include_label_consistency=True)


def test_wrong_expectation_is_reported_but_never_changes_an_outcome(copy_fixture_tree):
    clean = build_report()
    manifest_path = copy_fixture_tree()
    labels_path = manifest_path.parent / "labels.json"
    labels = json.loads(labels_path.read_text())
    labels["labels"]["fx-v1-P03"]["expected_overall_status"] = "READY_FOR_EXECUTION"
    labels["labels"]["fx-v1-P03"]["expected_non_passing_dimensions"] = []
    labels_path.write_text(json.dumps(labels, indent=2), encoding="utf-8")
    digest = hashlib.sha256(labels_path.read_bytes()).hexdigest()
    rewrite_json(manifest_path, lambda d: d["labels"].update(sha256=digest))

    changed = build_report(manifest_path)
    assert changed["label_consistency"]["expectation_matches"] == 9
    mismatch = changed["label_consistency"]["expectation_mismatches"]
    assert [m["fixture_id"] for m in mismatch] == ["fx-v1-P03"]
    assert _without_labels(changed)["development_stage"] == _without_labels(clean)["development_stage"]


def test_outcomes_are_independent_of_manifest_record_order(copy_fixture_tree):
    clean = build_report(include_label_consistency=False)
    manifest_path = copy_fixture_tree()
    rewrite_json(manifest_path, lambda d: d.update(records=list(reversed(d["records"]))))
    reordered = build_report(manifest_path, include_label_consistency=False)
    assert reordered["development_stage"] == clean["development_stage"]
    assert reordered["held_out_stage"] == clean["held_out_stage"]


def test_development_only_manifest_is_insufficient(copy_fixture_tree):
    manifest_path = copy_fixture_tree()
    rewrite_json(
        manifest_path,
        lambda d: d.update(records=[r for r in d["records"] if r["split"] == DEVELOPMENT]),
    )
    with pytest.raises(InsufficientEvaluationSetError):
        build_report(manifest_path)


def test_empty_manifest_is_rejected_as_malformed(copy_fixture_tree):
    manifest_path = copy_fixture_tree()
    rewrite_json(manifest_path, lambda d: d.update(records=[]))
    with pytest.raises(ManifestError):
        build_report(manifest_path)


def test_missing_manifest_raises_a_clear_os_error(tmp_path):
    with pytest.raises(OSError):
        build_report(tmp_path / "absent.json")


def test_evidence_class_is_never_overridden_by_fixture_content(copy_fixture_tree):
    manifest_path = copy_fixture_tree()
    plan_file = manifest_path.parent / "plans" / "P01.json"
    data = json.loads(plan_file.read_text())
    data["evidence_class_declared"] = "empirical"
    plan_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
    rewrite_json(manifest_path, lambda d: d["records"][0].update(
        plan_sha256=hashlib.sha256(plan_file.read_bytes()).hexdigest()))
    report = build_report(manifest_path)
    assert report["rubric_evidence_class"] == "research_plan_audit"
    assert all(o["evidence_class"] == "research_plan_audit" for o in report["development_stage"]["outcomes"])


def test_held_out_expectations_never_appear_in_the_report(copy_fixture_tree):
    from tools.research_plan_quality_eval.manifest import load_manifest
    from tools.research_plan_quality_eval.splits import LOCKED_INTERNAL_VALIDATION

    from .conftest import rehash_labels

    manifest_path = copy_fixture_tree()
    held_id = next(e.fixture_id for e in load_manifest(manifest_path).entries if e.split == LOCKED_INTERNAL_VALIDATION)
    labels_path = manifest_path.parent / "labels.json"
    labels = json.loads(labels_path.read_text(encoding="utf-8"))
    labels["labels"][held_id]["expected_overall_status"] = "SENTINEL_HELD_OUT_EXPECTATION"
    labels_path.write_text(json.dumps(labels, indent=2), encoding="utf-8")
    rehash_labels(manifest_path)

    report = build_report(manifest_path)
    mismatches = [m for m in report["label_consistency"]["expectation_mismatches"] if m["fixture_id"] == held_id]
    assert len(mismatches) == 1
    assert "SENTINEL_HELD_OUT_EXPECTATION" not in json.dumps(report)


def test_label_file_without_a_labels_object_is_a_manifest_error(copy_fixture_tree):
    from .conftest import rehash_labels

    manifest_path = copy_fixture_tree()
    labels_path = manifest_path.parent / "labels.json"
    data = json.loads(labels_path.read_text(encoding="utf-8"))
    del data["labels"]
    labels_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    rehash_labels(manifest_path)
    with pytest.raises(ManifestError, match="labels.labels"):
        build_report(manifest_path)


def test_editing_a_held_out_plan_leaves_the_development_stage_unchanged(copy_fixture_tree):
    from tools.research_plan_quality_eval.manifest import load_manifest
    from tools.research_plan_quality_eval.splits import LOCKED_INTERNAL_VALIDATION

    from .conftest import rehash_plan

    clean = build_report()
    manifest_path = copy_fixture_tree()
    held = next(e for e in load_manifest(manifest_path).entries if e.split == LOCKED_INTERNAL_VALIDATION)
    plan = json.loads(held.plan_path.read_text(encoding="utf-8"))
    plan["research_question"] = "edited held-out question. " + plan["research_question"]
    held.plan_path.write_text(json.dumps(plan, indent=2), encoding="utf-8")
    rehash_plan(manifest_path, held.fixture_id)

    changed = build_report(manifest_path)
    assert changed["fixture_set"]["plans"] != clean["fixture_set"]["plans"]
    assert changed["development_stage"] == clean["development_stage"]
