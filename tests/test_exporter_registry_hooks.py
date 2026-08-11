"""Registry-hook tests for the ds005620 transition exporter and the
phase_space exporter (Phase C / Phase D of the governed-evidence-bundle
milestone). Uses the real committed benchmarks/registry_seed.json and small
synthetic transition/phase-space fixtures -- never mutates the seed file.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from benchmarks.export_registry import BenchmarkRegistry
from phase_space.export_from_transitions import ExportError as PhaseSpaceExportError
from phase_space.export_from_transitions import export as export_phase_space
from tools.export_ds005620_pitnn_transitions import ExportError as DS005620ExportError
from tools.export_ds005620_pitnn_transitions import export as export_ds005620

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SEED_REGISTRY = _REPO_ROOT / "benchmarks" / "registry_seed.json"

_SCHEMA = "NeuroTopologySim.DS005620PITNNCohort.v1"


def _ds005620_fixture_dir(tmp_path):
    d = tmp_path / "ds005620_fixture"
    d.mkdir()
    summary = {
        "schema": _SCHEMA, "dataset_id": "ds005620", "n_paired_subjects": 1,
        "subjects": ["sub-9001"],
        "acquisition": {"sample_rate_hz": 500.0, "n_channels": 65, "n_samples_per_condition": 15000, "band_hz": [30.0, 80.0], "windows_per_condition": 3},
        "pitnn": {"verdict_counts": {"NOT_SUPPORTED": 1}},
        "scientific_note": "fixture",
        "topology_tests": {
            "integrated_landscape_area": {"paired_wilcoxon_subject_means": {"median_awake": 0.004, "median_sedated": 0.009, "n_pairs": 1, "p_value": 0.5, "statistic": 1.0, "status": "computed"}, "subject_blocked_permutation": {"p_value": 0.5, "n_permutations": 100, "seed": 0, "effect_size_d": -0.1, "method": "permutation_test_subject_blocked_paired", "n_a": 1, "n_b": 1, "alternative": "two-sided", "observed_stat": -0.005}, "mixedlm": None},
            "beta1": {"paired_wilcoxon_subject_means": {"median_awake": 1.5, "median_sedated": 2.5, "n_pairs": 1, "p_value": 0.5, "statistic": 1.0, "status": "computed"}, "subject_blocked_permutation": {"p_value": 0.5, "n_permutations": 100, "seed": 0, "effect_size_d": 0.1, "method": "permutation_test_subject_blocked_paired", "n_a": 1, "n_b": 1, "alternative": "two-sided", "observed_stat": 0.1}, "mixedlm": None},
            "mean_plv": {"paired_wilcoxon_subject_means": {"median_awake": 0.6, "median_sedated": 0.5, "n_pairs": 1, "p_value": 0.5, "statistic": 1.0, "status": "computed"}, "subject_blocked_permutation": {"p_value": 0.5, "n_permutations": 100, "seed": 0, "effect_size_d": 0.1, "method": "permutation_test_subject_blocked_paired", "n_a": 1, "n_b": 1, "alternative": "two-sided", "observed_stat": 0.04}, "mixedlm": None},
        },
        "cubical_persistence_h1_bottleneck": {"available": True, "n_subjects": 1},
        "spatial_defect_map": {"available": True, "n_subjects": 1},
    }
    (d / "cohort_summary.json").write_text(json.dumps(summary), encoding="utf-8")
    fieldnames = ["subject", "bayes_factor", "verdict", "awake_landscape_area", "sedated_landscape_area", "awake_beta1", "sedated_beta1", "awake_mean_plv", "sedated_mean_plv"]
    with (d / "cohort_per_subject.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerow({"subject": "sub-9001", "bayes_factor": "0.99", "verdict": "NOT_SUPPORTED", "awake_landscape_area": "0.004", "sedated_landscape_area": "0.009", "awake_beta1": "1.3", "sedated_beta1": "2.6", "awake_mean_plv": "0.75", "sedated_mean_plv": "0.40"})
    return d


# ── 2. ds005620 exporter registry hook ──────────────────────────────────────

def test_ds005620_default_no_registry_behavior_unchanged(tmp_path):
    input_dir = _ds005620_fixture_dir(tmp_path)
    result = export_ds005620(input_dir, tmp_path / "out")
    assert len(result["subject_records"]) == 1
    assert result["cohort_record"] is not None


def test_ds005620_allowed_transition_export_succeeds(tmp_path):
    input_dir = _REPO_ROOT / "contracts" / "btc_icft" / "ds005620" / "pitnn_cohort"
    result = export_ds005620(
        input_dir, tmp_path / "out",
        registry_path=_SEED_REGISTRY, requested_use="transition_export",
    )
    assert len(result["subject_records"]) == 20


def test_ds005620_forbidden_use_fails_before_writing_output(tmp_path):
    input_dir = _ds005620_fixture_dir(tmp_path)
    out_dir = tmp_path / "out"
    with pytest.raises(DS005620ExportError, match="benchmark registry denied"):
        export_ds005620(
            input_dir, out_dir,
            registry_path=_SEED_REGISTRY, requested_use="final_claim_confirmation",
        )
    assert not out_dir.exists()


def test_ds005620_unknown_registry_path_fails_closed(tmp_path):
    input_dir = _ds005620_fixture_dir(tmp_path)
    with pytest.raises(DS005620ExportError, match="benchmark registry error"):
        export_ds005620(
            input_dir, tmp_path / "out",
            registry_path=tmp_path / "does_not_exist.json", requested_use="transition_export",
        )


def test_ds005620_cli_registry_hook_end_to_end(tmp_path):
    import subprocess
    import sys

    input_dir = _ds005620_fixture_dir(tmp_path)
    out_dir = tmp_path / "out"
    result = subprocess.run(
        [sys.executable, "tools/export_ds005620_pitnn_transitions.py",
         "--input", str(input_dir), "--out", str(out_dir),
         "--registry", str(_SEED_REGISTRY), "--requested-use", "final_claim_confirmation"],
        capture_output=True, text=True, cwd=str(_REPO_ROOT),
    )
    assert result.returncode == 1
    assert "FAILED" in result.stdout
    assert not out_dir.exists()


# ── 3. phase_space exporter registry/mark_seen hook ─────────────────────────

@pytest.fixture()
def transitions_dir(tmp_path):
    input_dir = _ds005620_fixture_dir(tmp_path)
    out = tmp_path / "transitions_out"
    export_ds005620(input_dir, out)
    return out


def test_phase_space_default_no_registry_behavior_unchanged(tmp_path, transitions_dir):
    result = export_phase_space(transitions_dir, tmp_path / "ps_out")
    assert result["n_transitions"] == 2  # 1 subject + 1 cohort record
    assert result["registry_decisions"] == []


def test_phase_space_allowed_use_succeeds(tmp_path, transitions_dir):
    result = export_phase_space(
        transitions_dir, tmp_path / "ps_out",
        registry_path=_SEED_REGISTRY, requested_use="phase_space_export",
    )
    assert result["n_transitions"] == 2
    assert result["registry_decisions"][0]["allowed"] is True


def test_phase_space_forbidden_use_fails(tmp_path, transitions_dir):
    out_dir = tmp_path / "ps_out"
    with pytest.raises(PhaseSpaceExportError, match="benchmark registry denied"):
        export_phase_space(
            transitions_dir, out_dir,
            registry_path=_SEED_REGISTRY, requested_use="final_claim_confirmation",
        )
    assert not out_dir.exists()


def test_phase_space_mark_seen_requires_updated_registry_out(tmp_path, transitions_dir):
    with pytest.raises(PhaseSpaceExportError, match="requires updated_registry_out"):
        export_phase_space(
            transitions_dir, tmp_path / "ps_out",
            registry_path=_SEED_REGISTRY, mark_seen=True,
        )


def test_phase_space_mark_seen_writes_updated_registry_copy(tmp_path, transitions_dir):
    updated_out = tmp_path / "updated_registry.json"
    result = export_phase_space(
        transitions_dir, tmp_path / "ps_out",
        registry_path=_SEED_REGISTRY, mark_seen=True, updated_registry_out=updated_out,
    )
    assert updated_out.exists()
    assert result["contamination_updates"] == [
        {"dataset_id": "ds005620", "seen_by": "exploration", "note": "phase_space_export", "applied": True}
    ]
    updated_registry = BenchmarkRegistry.load(updated_out)
    assert updated_registry.datasets["ds005620"].contamination_status == "seen_by_exploration"


def test_phase_space_seed_registry_unchanged_unless_targeted(tmp_path, transitions_dir):
    before = _SEED_REGISTRY.read_bytes()
    export_phase_space(
        transitions_dir, tmp_path / "ps_out",
        registry_path=_SEED_REGISTRY, mark_seen=True, updated_registry_out=tmp_path / "updated.json",
    )
    after = _SEED_REGISTRY.read_bytes()
    assert before == after


def test_phase_space_cli_mark_seen_end_to_end(tmp_path, transitions_dir):
    import subprocess
    import sys

    ps_out = tmp_path / "ps_out"
    updated_out = tmp_path / "updated.json"
    result = subprocess.run(
        [sys.executable, "-m", "phase_space.export_from_transitions",
         "--input", str(transitions_dir), "--out", str(ps_out),
         "--registry", str(_SEED_REGISTRY), "--mark-seen", "--updated-registry-out", str(updated_out)],
        capture_output=True, text=True, cwd=str(_REPO_ROOT),
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["contamination_updates"]
    assert updated_out.exists()
