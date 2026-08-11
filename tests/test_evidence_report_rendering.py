"""Tests for reports.renderer.render_markdown -- deterministic, template-based
Markdown rendering of an EvidenceReportV1. Uses a synthetic in-memory report
(no real bundle needed for pure-rendering tests)."""
from __future__ import annotations

import json

from reports.evidence_report import EvidenceReportV1
from reports.renderer import render_markdown

_REQUIRED_SECTION_HEADINGS = [
    "## Executive Summary",
    "## Source Artifact and Registry Authorization",
    "## Dataset/Artifact Role and Contamination Status",
    "## Transition Records Generated",
    "## Phase-Space Coordinates Generated",
    "## Supported Axes and Insufficient-Data Axes",
    "## Null-Control Summary",
    "## Claim Scope and Evidence Level",
    "## Validation Summary",
    "## Limitations",
    "## Explicitly Blocked Interpretations",
    "## Reproducibility Commands",
    "## Generated Artifact Manifest",
    "## Future Work / Next Required Validation",
]


def _sample_report(**overrides):
    kwargs = dict(
        bundle_id="b0000000000000ab",
        dataset_id="ds005620",
        report_title="Governed Evidence Report -- ds005620 (transition_export)",
        requested_use="transition_export",
        source_artifacts={
            "bundle_path": "outputs/evidence/x/EvidenceBundle.json",
            "artifact_ids": ["art1"],
            "artifact_paths": {"source": "contracts/btc_icft/ds005620/pitnn_cohort"},
            "transition_record_paths": [],
            "phase_space_coordinate_paths": [],
            "phase_space_trajectory_paths": [],
        },
        registry_summary={
            "registry_path": "benchmarks/registry_seed.json",
            "requested_use": "transition_export",
            "decisions": [
                {"id": "ds005620", "kind": "dataset", "requested_use": "transition_export", "allowed": True, "reason": "allowed"},
            ],
            "n_decisions": 1,
            "all_allowed": True,
        },
        contamination_summary={"updates": [], "n_updates": 0, "any_applied": False},
        transition_summary={
            "count": 21, "record_ids": ["t1"], "record_levels": ["cohort", "subject"],
            "feature_set_ids": ["ds005620_pitnn_cohort_summary"], "feature_families": ["connectivity", "topology"],
            "source_target_pairs": [["awake", "sedated"]],
        },
        phase_space_summary={
            "count": 189,
            "status_counts": {"estimated": 63, "insufficient_data": 126, "not_applicable": 0, "failed_validation": 0},
            "confidence_counts": {"none": 126, "low": 63, "moderate": 0, "high": 0},
            "axes_estimated": ["integration", "differentiation"],
            "axes_insufficient_data": ["metastability"],
        },
        null_control_summary={"status": "failed", "per_transition": {"t1": "not_provided", "t2": "failed"}, "note": "aggregated honestly"},
        claim_scope_summary={"claim_scope_ceiling": "exploratory_metric", "generated_claim_scope": "exploratory_metric"},
        evidence_level_summary={"evidence_level_ceiling": "L4_cross_subject_dataset_specific", "generated_evidence_levels": ["L2_single_subject_real_signal"]},
        validation_summary={"bundle_valid": True, "bundle_validation_errors": []},
        limitations=["This report is a deterministic summary; it recomputes nothing."],
        blocked_claims=["This report does not support a clinical claim."],
        reproducibility_commands=[
            "python -m evidence.export_bundle --dataset ds005620 --feature-set cohort_summary",
            "python -m reports.export_report --bundle outputs/evidence/x/EvidenceBundle.json",
        ],
    )
    kwargs.update(overrides)
    return EvidenceReportV1.make(**kwargs)


def test_render_includes_all_required_sections():
    report = _sample_report()
    md = render_markdown(report)
    for heading in _REQUIRED_SECTION_HEADINGS:
        assert heading in md, f"missing section: {heading}"
    assert md.startswith("# ")  # title (section 1)


def test_render_includes_explicit_limitations():
    report = _sample_report()
    md = render_markdown(report)
    assert "This report is a deterministic summary; it recomputes nothing." in md


def test_render_includes_blocked_interpretations():
    report = _sample_report()
    md = render_markdown(report)
    assert "This report does not support a clinical claim." in md


def test_render_includes_reproducibility_commands():
    report = _sample_report()
    md = render_markdown(report)
    assert "python -m evidence.export_bundle" in md
    assert "python -m reports.export_report" in md
    assert "```bash" in md


def test_render_includes_coordinate_status_counts():
    report = _sample_report()
    md = render_markdown(report)
    assert "estimated" in md
    assert "| 63 |" in md
    assert "insufficient_data" in md
    assert "| 126 |" in md


def test_render_includes_confidence_counts():
    report = _sample_report()
    md = render_markdown(report)
    assert "moderate" in md
    assert "| 0 |" in md


def test_render_includes_null_control_summary():
    report = _sample_report()
    md = render_markdown(report)
    assert "`failed`" in md
    assert "aggregated honestly" in md
    assert "not_provided" in md


def test_render_includes_axes_estimated_and_insufficient():
    report = _sample_report()
    md = render_markdown(report)
    assert "- integration" in md
    assert "- differentiation" in md
    assert "- metastability" in md


def test_render_deterministic_across_repeated_calls():
    report = _sample_report()
    md1 = render_markdown(report)
    md2 = render_markdown(report)
    assert md1 == md2


def test_render_deterministic_with_fixed_created_at():
    from datetime import datetime, timezone

    r1 = _sample_report(_now=datetime(2026, 1, 1, tzinfo=timezone.utc))
    r2 = _sample_report(_now=datetime(2026, 1, 1, tzinfo=timezone.utc))
    assert render_markdown(r1) == render_markdown(r2)


def test_render_no_phase_space_case_says_so_explicitly():
    report = _sample_report(
        phase_space_summary={"count": 0, "status_counts": {}, "confidence_counts": {}, "axes_estimated": [], "axes_insufficient_data": []},
    )
    md = render_markdown(report)
    assert "No phase-space coordinates were requested or generated" in md


def test_render_no_registry_decisions_case_says_so_explicitly():
    report = _sample_report(registry_summary={"registry_path": None, "decisions": []})
    md = render_markdown(report)
    assert "legacy `--no-registry` build" in md


def test_render_no_contamination_updates_case_says_so_explicitly():
    report = _sample_report()
    md = render_markdown(report)
    assert "No contamination (mark-seen) updates were applied" in md


def test_render_generated_files_reflected_when_present():
    report = _sample_report(generated_files=["outputs/evidence/x/EvidenceReport.md", "outputs/evidence/x/EvidenceReport.json"])
    md = render_markdown(report)
    assert "outputs/evidence/x/EvidenceReport.md" in md
    assert "outputs/evidence/x/EvidenceReport.json" in md


def test_render_future_work_section_disclaims_unimplemented_modules():
    report = _sample_report()
    md = render_markdown(report)
    assert "Theory Competition Engine" in md
    assert "Koopman/DMD" in md
    assert "Counterfactual Reachable Sets" in md
    assert "Phenomenology parser" in md
    assert "Holo-Atlas interpreter" in md
    assert "Consciousness Atlas" in md
