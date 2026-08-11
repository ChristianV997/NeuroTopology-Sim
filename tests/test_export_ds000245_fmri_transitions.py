"""Tests for tools/export_ds000245_fmri_transitions.py.

Uses small synthetic fixtures modeled on the real, committed shape of
`contracts/fmri_tda/ds000245/` (cohort_result_schaefer100_motcorr.json,
global_efficiency_gate_schaefer100_motcorr.json) -- not the real 45-subject
cohort itself. No new empirical result is produced or implied by these
fixtures; they exist only to exercise the exporter's parsing/mapping/
governance logic quickly and deterministically.

ds000245 is a cross-sectional, between-subject design (CTL/ODN/ODP, each
subject scanned once in one fixed group), so this exporter emits
cohort-level GROUP-CONTRAST records only -- never per-subject records. That
constraint is itself tested explicitly below (category 2/3).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.export_ds000245_fmri_transitions import ExportError, export
from transitions.governance import BLOCKED_CLAIM_SCOPES
from transitions.record import TransitionValidationError
from transitions.store import TransitionStore

_GATE_SCHEMA = "NeuroTopologySim.DS000245GlobalEfficiencyGate.v1"


def _fixture_subject(subject_id, group, **overrides):
    base = {
        "subject_id": subject_id,
        "group": group,
        "error": "",
        "provenance": "real_fmri_fixture",
        "n_regions": 100,
        "n_timepoints": 198,
        "betti0": 100,
        "betti1": 60,
        "global_efficiency": 0.35,
        "mean_degree": 14.5,
        "modularity": 0.22,
        "small_worldness": 2.8,
        "total_persistence_h1": 1.9,
    }
    base.update(overrides)
    return base


def _fixture_cohort(*, subjects=None, group_stats=None, provenance="real_fmri_fixture"):
    subjects = subjects if subjects is not None else [
        _fixture_subject("sub-CTL01", "CTL", global_efficiency=0.30, betti1=55, modularity=0.20, total_persistence_h1=1.7),
        _fixture_subject("sub-CTL02", "CTL", global_efficiency=0.32, betti1=58, modularity=0.21, total_persistence_h1=1.8),
        _fixture_subject("sub-ODN01", "ODN", global_efficiency=0.41, betti1=70, modularity=0.26, total_persistence_h1=2.3),
        _fixture_subject("sub-ODN02", "ODN", global_efficiency=0.40, betti1=68, modularity=0.25, total_persistence_h1=2.2),
        _fixture_subject("sub-ODP01", "ODP", global_efficiency=0.43, betti1=72, modularity=0.26, total_persistence_h1=2.5),
        _fixture_subject("sub-ODP02", "ODP", global_efficiency=0.42, betti1=74, modularity=0.25, total_persistence_h1=2.4),
    ]
    if group_stats is None:
        group_stats = {
            "betti1": {
                "metric": "betti1", "F": 5.0, "p_value": 0.01, "eta_squared": 0.2,
                "group_means": {"CTL": 56.5, "ODN": 69.0, "ODP": 73.0},
                "group_n": {"CTL": 2, "ODN": 2, "ODP": 2},
            },
            "global_efficiency": {
                "metric": "global_efficiency", "F": 7.0, "p_value": 0.002, "eta_squared": 0.27,
                "group_means": {"CTL": 0.31, "ODN": 0.405, "ODP": 0.425},
                "group_n": {"CTL": 2, "ODN": 2, "ODP": 2},
            },
            "modularity": {
                "metric": "modularity", "F": 3.5, "p_value": 0.03, "eta_squared": 0.15,
                "group_means": {"CTL": 0.205, "ODN": 0.255, "ODP": 0.255},
                "group_n": {"CTL": 2, "ODN": 2, "ODP": 2},
            },
            "total_persistence_h1": {
                "metric": "total_persistence_h1", "F": 4.0, "p_value": 0.02, "eta_squared": 0.17,
                "group_means": {"CTL": 1.75, "ODN": 2.25, "ODP": 2.45},
                "group_n": {"CTL": 2, "ODN": 2, "ODP": 2},
            },
        }
    return {
        "atlas": "Schaefer2018_100Parcels_7Networks",
        "pipeline": "test_fixture_pipeline",
        "provenance": provenance,
        "n_subjects": len(subjects),
        "n_subjects_attempted": len(subjects),
        "n_ok": len(subjects),
        "n_errors": 0,
        "fd_threshold_mm": 0.5,
        "fd_exclude_fraction": 0.1,
        "n_subjects_excluded_motion": 0,
        "motion_qc": {},
        "group_stats": group_stats,
        "subjects": subjects,
    }


def _fixture_gate(*, p_value=0.001, schema=_GATE_SCHEMA):
    return {
        "schema": schema,
        "dataset_id": "ds000245",
        "n_subjects": 6,
        "group_n": {"CTL": 2, "ODN": 2, "ODP": 2},
        "group_means_global_efficiency": {"CTL": 0.31, "ODN": 0.405, "ODP": 0.425},
        "scientific_note": "fixture scientific note",
        "question_a_metric_validity": {
            "method": "surrogate_test_topology_metric_ft_two_sided",
            "n_subjects_gated": 6, "n_pass_p05": 6, "fraction_pass": 1.0,
            "per_subject": [],
        },
        "question_b_contrast_reality": {
            "method": "permutation_anova_label_shuffle",
            "n_groups": 3, "n_permutations": 1000, "seed": 0,
            "observed_f": 7.0, "observed_eta_squared": 0.27, "p_value": p_value,
        },
    }


def _write_fixture_dir(tmp_path, *, cohort=None, gate=None, include_gate=True, suffix="_schaefer100_motcorr"):
    d = tmp_path / "ds000245_fixture"
    d.mkdir()
    (d / f"cohort_result{suffix}.json").write_text(
        json.dumps(cohort if cohort is not None else _fixture_cohort()), encoding="utf-8"
    )
    if include_gate:
        (d / f"global_efficiency_gate{suffix}.json").write_text(
            json.dumps(gate if gate is not None else _fixture_gate()), encoding="utf-8"
        )
    return d


# ── 1. Source artifact parsing ───────────────────────────────────────────────

def test_parses_real_shaped_cohort_and_gate_fixture(tmp_path):
    input_dir = _write_fixture_dir(tmp_path)
    result = export(input_dir, tmp_path / "out")
    assert len(result["records"]) == 3  # CTL->ODN, CTL->ODP, ODN->ODP
    assert result["variant"] == "schaefer100_motcorr"
    assert result["feature_set_id"] == "ds000245_fmri_graph_schaefer100_motcorr"


def test_kmeans100_variant_reads_unsuffixed_files(tmp_path):
    input_dir = _write_fixture_dir(tmp_path, suffix="")
    result = export(input_dir, tmp_path / "out", variant="kmeans100")
    assert result["feature_set_id"] == "ds000245_fmri_graph_kmeans100"
    assert len(result["records"]) == 3


# ── 2/3. Cohort-level export only (no subject-level records ever) ──────────

def test_cohort_only_no_subject_level_records_ever_emitted(tmp_path):
    input_dir = _write_fixture_dir(tmp_path)
    result = export(input_dir, tmp_path / "out")
    for record in result["records"]:
        assert record.record_level == "cohort"
        assert record.subject_id is None


def test_transition_class_names_cross_sectional_design(tmp_path):
    input_dir = _write_fixture_dir(tmp_path)
    result = export(input_dir, tmp_path / "out")
    for record in result["records"]:
        assert record.transition_class == "cross_sectional_group_contrast_not_within_subject_transition"


def test_first_limitation_states_non_transition_nature(tmp_path):
    input_dir = _write_fixture_dir(tmp_path)
    result = export(input_dir, tmp_path / "out")
    for record in result["records"]:
        assert "not a within-subject state transition" in record.limitations[0]


def test_default_export_covers_all_pairwise_group_contrasts(tmp_path):
    input_dir = _write_fixture_dir(tmp_path)
    result = export(input_dir, tmp_path / "out")
    contrasts = {(r.source_state, r.target_state) for r in result["records"]}
    assert contrasts == {("CTL", "ODN"), ("CTL", "ODP"), ("ODN", "ODP")}


def test_restrict_to_single_contrast(tmp_path):
    input_dir = _write_fixture_dir(tmp_path)
    result = export(input_dir, tmp_path / "out", contrasts=[("CTL", "ODP")])
    assert len(result["records"]) == 1
    assert (result["records"][0].source_state, result["records"][0].target_state) == ("CTL", "ODP")


def test_deterministic_ids_stable_across_repeated_export(tmp_path):
    input_dir = _write_fixture_dir(tmp_path)
    result1 = export(input_dir, tmp_path / "out1")
    result2 = export(input_dir, tmp_path / "out2")
    ids1 = sorted(r.transition_id for r in result1["records"])
    ids2 = sorted(r.transition_id for r in result2["records"])
    assert ids1 == ids2


def test_group_mean_provenance_distinguishes_artifact_vs_aggregated(tmp_path):
    input_dir = _write_fixture_dir(tmp_path)
    result = export(input_dir, tmp_path / "out")
    record = next(r for r in result["records"] if (r.source_state, r.target_state) == ("CTL", "ODP"))
    prov = record.metadata["group_mean_provenance"]
    # betti1/global_efficiency/modularity/total_persistence_h1 come from group_stats
    assert prov["source"]["connectivity.global_efficiency"] == "source_artifact_group_stats"
    # mean_degree/small_worldness/betti0 have no group_stats entry -> aggregated
    assert prov["source"]["connectivity.degree"] == "aggregated_by_exporter_from_committed_per_subject_values"


# ── 4. Fail-closed behavior ─────────────────────────────────────────────────

def test_missing_input_path_fails(tmp_path):
    with pytest.raises(ExportError, match="does not exist"):
        export(tmp_path / "nonexistent", tmp_path / "out")


def test_missing_cohort_result_file_fails(tmp_path):
    d = tmp_path / "bad"
    d.mkdir()
    with pytest.raises(ExportError, match="cohort_result_schaefer100_motcorr.json"):
        export(d, tmp_path / "out")


def test_unsupported_gate_schema_fails_clearly(tmp_path):
    input_dir = _write_fixture_dir(tmp_path, gate=_fixture_gate(schema="SomeOtherSchema.v9"))
    with pytest.raises(ExportError, match="unsupported gate schema"):
        export(input_dir, tmp_path / "out")


def test_nonexistent_group_in_explicit_contrast_fails_closed(tmp_path):
    input_dir = _write_fixture_dir(tmp_path)
    with pytest.raises(ExportError, match="no group-contrast records could be exported"):
        export(input_dir, tmp_path / "out", contrasts=[("CTL", "NOT_A_GROUP")])


def test_same_source_and_target_group_fails_closed(tmp_path):
    input_dir = _write_fixture_dir(tmp_path)
    with pytest.raises(ExportError, match="no group-contrast records could be exported"):
        export(input_dir, tmp_path / "out", contrasts=[("CTL", "CTL")])


def test_empty_subjects_list_fails(tmp_path):
    input_dir = _write_fixture_dir(tmp_path, cohort=_fixture_cohort(subjects=[]))
    with pytest.raises(ExportError, match="no subject entries"):
        export(input_dir, tmp_path / "out")


# ── 5. Governance ────────────────────────────────────────────────────────────

def test_no_blocked_claim_scope_ever_used(tmp_path):
    input_dir = _write_fixture_dir(tmp_path)
    result = export(input_dir, tmp_path / "out")
    for record in result["records"]:
        assert record.claim_scope not in BLOCKED_CLAIM_SCOPES
        assert record.claim_scope == "exploratory_metric"


def test_no_banned_overclaim_text_in_generated_records(tmp_path):
    input_dir = _write_fixture_dir(tmp_path)
    result = export(input_dir, tmp_path / "out")
    for record in result["records"]:
        assert record.validate() == []  # validate() includes the banned-phrase scan


def test_limitations_are_non_empty(tmp_path):
    input_dir = _write_fixture_dir(tmp_path)
    result = export(input_dir, tmp_path / "out")
    for record in result["records"]:
        assert record.limitations
        assert all(item.strip() for item in record.limitations)


def test_null_control_status_honest_when_gate_passes(tmp_path):
    input_dir = _write_fixture_dir(tmp_path, gate=_fixture_gate(p_value=0.001))
    result = export(input_dir, tmp_path / "out")
    for record in result["records"]:
        assert record.null_control_summary["status"] == "passed"
        assert record.null_control_summary["covered_features"] == ["connectivity.global_efficiency"]


def test_null_control_status_honest_when_gate_fails(tmp_path):
    input_dir = _write_fixture_dir(tmp_path, gate=_fixture_gate(p_value=0.5))
    result = export(input_dir, tmp_path / "out")
    for record in result["records"]:
        assert record.null_control_summary["status"] == "failed"


def test_null_control_status_not_provided_when_no_gate_artifact(tmp_path):
    input_dir = _write_fixture_dir(tmp_path, include_gate=False)
    result = export(input_dir, tmp_path / "out")
    for record in result["records"]:
        assert record.null_control_summary["status"] == "not_provided"


def test_null_control_scope_note_flags_partial_coverage(tmp_path):
    input_dir = _write_fixture_dir(tmp_path)
    result = export(input_dir, tmp_path / "out")
    for record in result["records"]:
        uncovered = record.null_control_summary["uncovered_features"]
        assert "connectivity.global_efficiency" not in uncovered
        assert "topology.fmri_graph_betti1" in uncovered


def test_parametric_pvalue_alone_not_treated_as_null_control_pass(tmp_path):
    # No gate artifact at all -> group_stats p-values (present on every metric)
    # must NOT be interpreted as a null-control pass.
    input_dir = _write_fixture_dir(tmp_path, include_gate=False)
    result = export(input_dir, tmp_path / "out")
    for record in result["records"]:
        assert record.null_control_summary["status"] != "passed"


# ── 6. Phase-space smoke ─────────────────────────────────────────────────────

def test_phase_space_smoke_integration_axis_estimates_from_connectivity(tmp_path):
    from phase_space.export_from_transitions import export as export_phase_space

    input_dir = _write_fixture_dir(tmp_path)
    export(input_dir, tmp_path / "transitions_out")
    result = export_phase_space(tmp_path / "transitions_out", tmp_path / "phase_space_out")
    assert result["n_estimated"] >= 1

    store_dir = tmp_path / "phase_space_out"
    found_integration = False
    for record_dir in store_dir.iterdir():
        coords = json.loads((record_dir / "PhaseSpaceCoordinates.json").read_text(encoding="utf-8"))
        for coord in coords["coordinates"]:
            if coord["axis"] == "integration":
                found_integration = True
                assert coord["status"] == "estimated"
                assert coord["confidence"] in ("none", "low", "moderate")
    assert found_integration


def test_phase_space_smoke_fmri_graph_topology_axes_report_insufficient_data(tmp_path):
    """topology.fmri_graph_* names are deliberately distinct from the
    canonical topology.betti1/spatial_defect_betti1/etc. names that
    phase_space/axes.py maps to differentiation/topological_organization, so
    those axes must NOT silently estimate from a different measurement
    family -- they must report insufficient_data."""
    from phase_space.export_from_transitions import export as export_phase_space

    input_dir = _write_fixture_dir(tmp_path)
    export(input_dir, tmp_path / "transitions_out")
    export_phase_space(tmp_path / "transitions_out", tmp_path / "phase_space_out")

    store_dir = tmp_path / "phase_space_out"
    for record_dir in store_dir.iterdir():
        coords = json.loads((record_dir / "PhaseSpaceCoordinates.json").read_text(encoding="utf-8"))
        by_axis = {c["axis"]: c for c in coords["coordinates"]}
        assert by_axis["differentiation"]["status"] == "insufficient_data"
        assert by_axis["topological_organization"]["status"] == "insufficient_data"


def test_phase_space_smoke_output_claim_scope_never_exceeds_input(tmp_path):
    from phase_space.export_from_transitions import export as export_phase_space

    input_dir = _write_fixture_dir(tmp_path)
    export(input_dir, tmp_path / "transitions_out")
    export_phase_space(tmp_path / "transitions_out", tmp_path / "phase_space_out")

    store_dir = tmp_path / "phase_space_out"
    for record_dir in store_dir.iterdir():
        coords = json.loads((record_dir / "PhaseSpaceCoordinates.json").read_text(encoding="utf-8"))
        for coord in coords["coordinates"]:
            assert coord["input_claim_scope"] == "exploratory_metric"
            assert coord["output_claim_scope"] == "exploratory_metric"


def test_phase_space_smoke_reports_zero_failed_validation(tmp_path):
    from phase_space.export_from_transitions import export as export_phase_space

    input_dir = _write_fixture_dir(tmp_path)
    export(input_dir, tmp_path / "transitions_out")
    result = export_phase_space(tmp_path / "transitions_out", tmp_path / "phase_space_out")
    assert result["n_failed_validation"] == 0


def test_cli_write_phase_space_smoke_flag_end_to_end(tmp_path):
    import subprocess
    import sys
    from pathlib import Path

    input_dir = _write_fixture_dir(tmp_path)
    out_dir = tmp_path / "out"
    ps_dir = tmp_path / "ps_out"
    result = subprocess.run(
        [sys.executable, "tools/export_ds000245_fmri_transitions.py",
         "--input", str(input_dir), "--out", str(out_dir),
         "--write-phase-space-smoke", str(ps_dir)],
        capture_output=True, text=True, cwd=str(Path(__file__).resolve().parents[1]),
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["records_written"] == 3
    assert payload["phase_space_smoke"]["coordinates_failed_validation"] == 0
    assert payload["phase_space_smoke"]["coordinates_estimated"] >= 1


# ── 7. Store compatibility ───────────────────────────────────────────────────

def test_output_directory_contains_valid_transition_record_json(tmp_path):
    input_dir = _write_fixture_dir(tmp_path)
    out_dir = tmp_path / "out"
    export(input_dir, out_dir)
    store = TransitionStore(out_dir)
    assert len(store.list_records()) == 3


def test_records_can_be_read_back_via_transition_store(tmp_path):
    input_dir = _write_fixture_dir(tmp_path)
    out_dir = tmp_path / "out"
    result = export(input_dir, out_dir)
    store = TransitionStore(out_dir)
    for record in result["records"]:
        loaded = store.read(record.transition_id)
        assert loaded.to_dict() == record.to_dict()
        header, rows = store.read_trajectory(record.transition_id)
        assert header == record.feature_names
        assert len(rows) == 2  # source group, target group


def test_records_carry_feature_definitions_and_feature_set_id(tmp_path):
    input_dir = _write_fixture_dir(tmp_path)
    result = export(input_dir, tmp_path / "out")
    for record in result["records"]:
        assert record.metadata["feature_set_id"] == "ds000245_fmri_graph_schaefer100_motcorr"
        assert set(record.metadata["feature_definitions"]) == set(record.feature_names)


def test_unknown_variant_fails_closed(tmp_path):
    input_dir = _write_fixture_dir(tmp_path)
    with pytest.raises(ExportError, match="unknown variant"):
        export(input_dir, tmp_path / "out", variant="not_a_real_variant")


def test_cli_end_to_end(tmp_path):
    import subprocess
    import sys
    from pathlib import Path

    input_dir = _write_fixture_dir(tmp_path)
    out_dir = tmp_path / "out"
    result = subprocess.run(
        [sys.executable, "tools/export_ds000245_fmri_transitions.py",
         "--input", str(input_dir), "--out", str(out_dir)],
        capture_output=True, text=True, cwd=str(Path(__file__).resolve().parents[1]),
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["records_written"] == 3
    assert payload["skipped"] == []


# ── Optional benchmarks registry hook (backward-compatible, fail-closed) ────

_REPO_ROOT_FOR_REGISTRY = Path(__file__).resolve().parents[1]
_SEED_REGISTRY = _REPO_ROOT_FOR_REGISTRY / "benchmarks" / "registry_seed.json"


def test_export_without_registry_argument_is_unaffected(tmp_path):
    # Default behavior (registry_path=None) must be identical to before this
    # hook existed -- no registry file is read, no use-policy check runs.
    input_dir = _write_fixture_dir(tmp_path)
    result = export(input_dir, tmp_path / "out")
    assert len(result["records"]) == 3


def test_export_succeeds_with_registry_allowed_use(tmp_path):
    input_dir = _write_fixture_dir(tmp_path)
    result = export(
        input_dir, tmp_path / "out",
        registry_path=_SEED_REGISTRY, requested_use="transition_export",
    )
    assert len(result["records"]) == 3


def test_export_fails_closed_with_registry_forbidden_use(tmp_path):
    input_dir = _write_fixture_dir(tmp_path)
    out_dir = tmp_path / "out"
    with pytest.raises(ExportError, match="benchmark registry denied"):
        export(
            input_dir, out_dir,
            registry_path=_SEED_REGISTRY, requested_use="final_claim_confirmation",
        )
    assert not out_dir.exists()


def test_cli_export_fails_closed_with_forbidden_registry_use(tmp_path):
    import subprocess
    import sys

    input_dir = _write_fixture_dir(tmp_path)
    out_dir = tmp_path / "out"
    result = subprocess.run(
        [sys.executable, "tools/export_ds000245_fmri_transitions.py",
         "--input", str(input_dir), "--out", str(out_dir),
         "--registry", str(_SEED_REGISTRY), "--requested-use", "clinical_claim"],
        capture_output=True, text=True, cwd=str(_REPO_ROOT_FOR_REGISTRY),
    )
    assert result.returncode == 1
    assert "FAILED" in result.stdout
    assert not out_dir.exists()
