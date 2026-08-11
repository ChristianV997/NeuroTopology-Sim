"""Integration tests: evidence.builder.build_evidence_bundle's optional
--include-report flag, and reports.tables' aggregation over real bundle
output. Uses the real, small, already-committed contract artifacts
(contracts/btc_icft/ds005620/pitnn_cohort/, contracts/fmri_tda/ds000245/)
and the real committed benchmarks/registry_seed.json -- no raw data
fetched, no pipeline re-run.
"""
from __future__ import annotations

import json
from pathlib import Path

from evidence.builder import build_evidence_bundle
from evidence.store import EvidenceBundleStore
from reports.evidence_report import build_report
from reports.tables import (
    load_phase_space_coordinate_files,
    load_transition_records,
    summarize_contamination,
    summarize_phase_space,
    summarize_registry,
    summarize_transitions,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SEED_REGISTRY = _REPO_ROOT / "benchmarks" / "registry_seed.json"
_DS005620_SOURCE = _REPO_ROOT / "contracts" / "btc_icft" / "ds005620" / "pitnn_cohort"
_DS000245_SOURCE = _REPO_ROOT / "contracts" / "fmri_tda" / "ds000245"


# ── 5. --include-report evidence-builder integration ────────────────────────

def test_include_report_generates_report_for_ds005620_cohort_summary(tmp_path):
    out = tmp_path / "out"
    bundle = build_evidence_bundle(
        dataset="ds005620", feature_set="cohort_summary",
        source=_DS005620_SOURCE, out=out, registry_path=_SEED_REGISTRY,
        include_phase_space=True, include_report=True,
    )
    assert (out / "EvidenceReport.md").exists()
    assert (out / "EvidenceReport.json").exists()
    assert bundle.metadata["report"]["report_id"]
    md = (out / "EvidenceReport.md").read_text(encoding="utf-8")
    assert "## Executive Summary" in md
    assert "ds005620" in md


def test_include_report_generates_report_for_ds000245_cheap(tmp_path):
    out = tmp_path / "out"
    bundle = build_evidence_bundle(
        dataset="ds000245", feature_set="schaefer100_motcorr",
        source=_DS000245_SOURCE, out=out, registry_path=_SEED_REGISTRY,
        include_report=True,
    )
    assert (out / "EvidenceReport.md").exists()
    assert (out / "EvidenceReport.json").exists()
    assert bundle.metadata["report"]["report_id"]


def test_default_no_report_behavior_unchanged(tmp_path):
    out = tmp_path / "out"
    bundle = build_evidence_bundle(
        dataset="ds005620", feature_set="cohort_summary",
        source=_DS005620_SOURCE, out=out, registry_path=_SEED_REGISTRY,
    )
    assert not (out / "EvidenceReport.md").exists()
    assert not (out / "EvidenceReport.json").exists()
    assert "report" not in bundle.metadata


def test_report_out_overrides_default_location(tmp_path):
    out = tmp_path / "bundle_out"
    report_dir = tmp_path / "report_out"
    bundle = build_evidence_bundle(
        dataset="ds005620", feature_set="cohort_summary",
        source=_DS005620_SOURCE, out=out, registry_path=_SEED_REGISTRY,
        include_report=True, report_out=report_dir,
    )
    assert (report_dir / "EvidenceReport.md").exists()
    assert not (out / "EvidenceReport.md").exists()
    assert bundle.metadata["report"]["report_id"]


def test_generated_report_round_trips_via_store(tmp_path):
    out = tmp_path / "out"
    build_evidence_bundle(
        dataset="ds005620", feature_set="cohort_summary",
        source=_DS005620_SOURCE, out=out, registry_path=_SEED_REGISTRY,
        include_report=True,
    )
    store = EvidenceBundleStore(out)
    bundle = store.read()
    from reports.evidence_report import EvidenceReportV1

    report = EvidenceReportV1.from_json((out / "EvidenceReport.json").read_text(encoding="utf-8"))
    assert report.bundle_id == bundle.bundle_id
    assert report.validate() == []


# ── 3. Bundle/transition/coordinate aggregation ─────────────────────────────

def test_summarize_transitions_counts_real_ds005620_cohort_summary(tmp_path):
    out = tmp_path / "out"
    bundle = build_evidence_bundle(
        dataset="ds005620", feature_set="cohort_summary",
        source=_DS005620_SOURCE, out=out, registry_path=_SEED_REGISTRY,
    )
    records = load_transition_records(_REPO_ROOT, bundle.transition_record_paths)
    summary = summarize_transitions(records)
    assert summary["count"] == 21
    assert "cohort" in summary["record_levels"]
    assert "subject" in summary["record_levels"]
    assert summary["feature_set_ids"] == ["ds005620_pitnn_cohort_summary"]
    assert set(summary["feature_families"]) == {"connectivity", "topology"}


def test_summarize_phase_space_status_counts_real_ds005620(tmp_path):
    out = tmp_path / "out"
    bundle = build_evidence_bundle(
        dataset="ds005620", feature_set="cohort_summary",
        source=_DS005620_SOURCE, out=out, registry_path=_SEED_REGISTRY,
        include_phase_space=True,
    )
    coord_files = load_phase_space_coordinate_files(_REPO_ROOT, bundle.phase_space_coordinate_paths)
    summary = summarize_phase_space(coord_files)
    assert summary["count"] == 189  # 21 transitions x 9 axes
    assert sum(summary["status_counts"].values()) == 189
    assert summary["status_counts"]["estimated"] > 0
    assert summary["status_counts"]["insufficient_data"] > 0


def test_summarize_phase_space_axes_estimated_vs_insufficient(tmp_path):
    out = tmp_path / "out"
    bundle = build_evidence_bundle(
        dataset="ds005620", feature_set="cohort_summary",
        source=_DS005620_SOURCE, out=out, registry_path=_SEED_REGISTRY,
        include_phase_space=True,
    )
    coord_files = load_phase_space_coordinate_files(_REPO_ROOT, bundle.phase_space_coordinate_paths)
    summary = summarize_phase_space(coord_files)
    assert "integration" in summary["axes_estimated"] or "topological_organization" in summary["axes_estimated"]
    assert set(summary["axes_estimated"]).isdisjoint(summary["axes_insufficient_data"])


def test_summarize_registry_and_contamination(tmp_path):
    out = tmp_path / "out"
    updated_out = tmp_path / "updated.json"
    bundle = build_evidence_bundle(
        dataset="ds005620", feature_set="cohort_summary",
        source=_DS005620_SOURCE, out=out, registry_path=_SEED_REGISTRY,
        mark_seen=True, updated_registry_out=updated_out,
    )
    registry_summary = summarize_registry(bundle)
    assert registry_summary["n_decisions"] >= 1
    assert registry_summary["all_allowed"] is True

    contamination_summary = summarize_contamination(bundle)
    assert contamination_summary["n_updates"] >= 1
    assert contamination_summary["any_applied"] is True


def test_aggregation_does_not_recompute_scientific_metrics(tmp_path):
    """summarize_* functions must only count/group fields already present
    on the loaded records -- never call into transitions/phase_space
    estimator code."""
    out = tmp_path / "out"
    bundle = build_evidence_bundle(
        dataset="ds005620", feature_set="cohort_summary",
        source=_DS005620_SOURCE, out=out, registry_path=_SEED_REGISTRY,
        include_phase_space=True,
    )
    records = load_transition_records(_REPO_ROOT, bundle.transition_record_paths)
    coord_files = load_phase_space_coordinate_files(_REPO_ROOT, bundle.phase_space_coordinate_paths)

    # Loaded records/coordinate files are plain dicts (json.loads output),
    # not TransitionRecordV1/PhaseSpaceCoordinateV1 objects -- summarize_*
    # cannot call estimator methods on them even if it wanted to.
    assert isinstance(records[0], dict)
    assert isinstance(coord_files[0], dict)

    report = build_report(bundle, out / "EvidenceBundle.json")
    # The report's phase_space_summary status counts must exactly match a
    # direct recount from the same raw files (no estimator re-run changed
    # anything in between).
    direct_summary = summarize_phase_space(coord_files)
    assert report.phase_space_summary == direct_summary


# ── 6. Guardrails on real generated output ──────────────────────────────────

def test_real_generated_report_passes_guardrail_scan(tmp_path):
    import subprocess
    import sys

    out = tmp_path / "out"
    build_evidence_bundle(
        dataset="ds005620", feature_set="cohort_summary",
        source=_DS005620_SOURCE, out=out, registry_path=_SEED_REGISTRY,
        include_phase_space=True, include_report=True,
    )
    result = subprocess.run(
        [sys.executable, "tools/check_claim_guardrails.py", str(out / "EvidenceReport.md"), str(out / "EvidenceReport.json")],
        capture_output=True, text=True, cwd=str(_REPO_ROOT),
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_real_generated_report_does_not_promote_claim_scope(tmp_path):
    out = tmp_path / "out"
    bundle = build_evidence_bundle(
        dataset="ds005620", feature_set="cohort_summary",
        source=_DS005620_SOURCE, out=out, registry_path=_SEED_REGISTRY,
        include_report=True,
    )
    report = build_report(bundle, out / "EvidenceBundle.json")
    assert report.claim_scope_summary["generated_claim_scope"] == bundle.generated_claim_scope
    assert report.claim_scope_summary["claim_scope_ceiling"] == bundle.claim_scope_ceiling
    assert report.evidence_level_summary["generated_evidence_levels"] == bundle.generated_evidence_levels
