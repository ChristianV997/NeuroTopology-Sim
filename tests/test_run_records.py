"""Tests for RunRecord v1 schema + dual artifact writers.

All offline — no LLM, no network, no real git state required.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

# Ensure repo root is on path (supplements conftest.py)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sim.run_record_schema import (
    CONFOUNDS_CHECKLIST,
    RunRecord,
    RUN_RECORD_SCHEMA,
    build_run_id,
    canonicalize_paths,
    validate_run_record_dict,
)
from sim.run_cards import (
    build_run_record,
    run_meditation_sim,
    run_psi_os,
    save_run_card_markdown,
    save_run_record_json,
)

_NOW = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)

_METRICS = {
    "I_mean": 0.5,
    "I_std": 0.1,
    "I_final": 0.45,
    "vort_mean": 1.2,
    "n_steps": 10.0,
    "Qz_mean": 0.0,
    "Qabs_mean": 0.0,
    "f_dress": 0.0,
}

_INPUT = {"N": 16, "n_steps": 10, "seed": 7}


# ── CONFOUNDS_CHECKLIST ──────────────────────────────────────────────────────

def test_confounds_checklist_has_8_items():
    assert len(CONFOUNDS_CHECKLIST) == 8


def test_confounds_checklist_all_strings():
    assert all(isinstance(c, str) for c in CONFOUNDS_CHECKLIST)


def test_confounds_checklist_contains_reproducibility():
    assert "reproducibility_seed_fixed" in CONFOUNDS_CHECKLIST


# ── build_run_id stability ───────────────────────────────────────────────────

def test_run_id_is_16_chars():
    rid = build_run_id("psi", "ScienceR-Dsim", "abc1234", [], _INPUT, _METRICS)
    assert len(rid) == 16


def test_run_id_is_hex():
    rid = build_run_id("psi", "ScienceR-Dsim", "abc1234", [], _INPUT, _METRICS)
    int(rid, 16)  # raises ValueError if not hex


def test_run_id_same_inputs_stable():
    rid1 = build_run_id("psi", "ScienceR-Dsim", "abc1234", [], _INPUT, _METRICS)
    rid2 = build_run_id("psi", "ScienceR-Dsim", "abc1234", [], _INPUT, _METRICS)
    assert rid1 == rid2


def test_run_id_different_mode_differs():
    rid_psi = build_run_id("psi", "ScienceR-Dsim", "abc1234", [], _INPUT, _METRICS)
    rid_med = build_run_id("meditation", "ScienceR-Dsim", "abc1234", [], _INPUT, _METRICS)
    assert rid_psi != rid_med


def test_run_id_different_commit_differs():
    rid1 = build_run_id("psi", "ScienceR-Dsim", "abc1234", [], _INPUT, _METRICS)
    rid2 = build_run_id("psi", "ScienceR-Dsim", "def5678", [], _INPUT, _METRICS)
    assert rid1 != rid2


def test_run_id_excludes_created_at():
    """run_id must be the same regardless of when the run is recorded."""
    rid1 = build_run_id("psi", "ScienceR-Dsim", "abc1234", [], _INPUT, _METRICS)
    # Simulated: different time would not affect hash because created_at is not input
    rid2 = build_run_id("psi", "ScienceR-Dsim", "abc1234", [], _INPUT, _METRICS)
    assert rid1 == rid2


# ── canonicalize_paths ───────────────────────────────────────────────────────

def test_canonicalize_paths_converts_path():
    d = {"data": Path("/tmp/foo/bar.npz")}
    out = canonicalize_paths(d)
    assert out["data"] == "/tmp/foo/bar.npz"


def test_canonicalize_paths_relative_to_root(tmp_path):
    d = {"data": tmp_path / "data.npz"}
    out = canonicalize_paths(d, repo_root=tmp_path)
    assert out["data"] == "data.npz"


def test_canonicalize_paths_nested():
    d = {"inner": {"file": Path("/a/b.txt")}}
    out = canonicalize_paths(d)
    assert out["inner"]["file"] == "/a/b.txt"


def test_canonicalize_paths_list_of_paths():
    d = {"files": [Path("/x/y.npz")]}
    out = canonicalize_paths(d)
    assert out["files"] == ["/x/y.npz"]


# ── validate_run_record_dict ─────────────────────────────────────────────────

def _valid_dict() -> dict:
    return {
        "schema_version": "1",
        "run_id": "a" * 16,
        "created_at": "2025-01-15T12:00:00+00:00",
        "mode": "psi",
        "repo": "ScienceR-Dsim",
        "git_commit": "abc1234",
        "argv": [],
        "input": {"N": 16},
        "metrics": {k: 0.0 for k in RUN_RECORD_SCHEMA["properties"]["metrics"]["required"]},
        "artifacts": {"md_path": "a.md", "json_path": "a.run.json"},
        "confounds": [],
        "guardrails": {},
        "h8_falsifiers": [],
    }


def test_validate_valid_dict_no_errors():
    assert validate_run_record_dict(_valid_dict()) == []


def test_validate_missing_required_field():
    d = _valid_dict()
    del d["run_id"]
    errors = validate_run_record_dict(d)
    assert any("run_id" in e for e in errors)


def test_validate_invalid_mode():
    d = _valid_dict()
    d["mode"] = "unknown"
    errors = validate_run_record_dict(d)
    assert any("mode" in e for e in errors)


def test_validate_missing_metric():
    d = _valid_dict()
    del d["metrics"]["I_mean"]
    errors = validate_run_record_dict(d)
    assert any("I_mean" in e for e in errors)


def test_validate_missing_artifact_path():
    d = _valid_dict()
    del d["artifacts"]["md_path"]
    errors = validate_run_record_dict(d)
    assert any("md_path" in e for e in errors)


# ── save_run_card_markdown ───────────────────────────────────────────────────

def _make_record(tmp_path) -> RunRecord:
    run_id = build_run_id("psi", "ScienceR-Dsim", "abc1234", [], _INPUT, _METRICS)
    stem = f"run_20250115T120000_{run_id[:8]}"
    return RunRecord(
        run_id=run_id,
        created_at="2025-01-15T12:00:00+00:00",
        mode="psi",
        repo="ScienceR-Dsim",
        git_commit="abc1234",
        argv=[],
        input=_INPUT,
        metrics=_METRICS,
        artifacts={
            "md_path": f"outputs/run_cards/{stem}.md",
            "json_path": f"outputs/run_cards/{stem}.run.json",
        },
        confounds=["reproducibility_seed_fixed"],
        guardrails={"I_final_above_zero": True},
        h8_falsifiers=[{"prediction": "I>0", "discriminator": "I<=0 fails", "status": "PASS"}],
        notes="test run",
    )


def test_save_markdown_creates_file(tmp_path):
    record = _make_record(tmp_path)
    path = save_run_card_markdown(record, tmp_path)
    assert path.exists()
    assert path.suffix == ".md"


def test_save_markdown_contains_run_id(tmp_path):
    record = _make_record(tmp_path)
    path = save_run_card_markdown(record, tmp_path)
    content = path.read_text()
    assert record.run_id in content


def test_save_markdown_contains_mode(tmp_path):
    record = _make_record(tmp_path)
    path = save_run_card_markdown(record, tmp_path)
    assert "psi" in path.read_text()


def test_save_markdown_contains_metrics(tmp_path):
    record = _make_record(tmp_path)
    path = save_run_card_markdown(record, tmp_path)
    content = path.read_text()
    assert "I_mean" in content
    assert "Qz_mean" in content


def test_save_markdown_confounds_checklist(tmp_path):
    record = _make_record(tmp_path)
    path = save_run_card_markdown(record, tmp_path)
    content = path.read_text()
    assert "[x] reproducibility_seed_fixed" in content
    assert "[ ] measurement_invariance_checked" in content


def test_save_markdown_h8_falsifier(tmp_path):
    record = _make_record(tmp_path)
    path = save_run_card_markdown(record, tmp_path)
    assert "PASS" in path.read_text()


# ── save_run_record_json ─────────────────────────────────────────────────────

def test_save_json_creates_file(tmp_path):
    record = _make_record(tmp_path)
    path = save_run_record_json(record, tmp_path)
    assert path.exists()
    assert path.name.endswith(".run.json")


def test_save_json_valid_json(tmp_path):
    record = _make_record(tmp_path)
    path = save_run_record_json(record, tmp_path)
    data = json.loads(path.read_text())
    assert data["run_id"] == record.run_id


def test_save_json_schema_version(tmp_path):
    record = _make_record(tmp_path)
    path = save_run_record_json(record, tmp_path)
    data = json.loads(path.read_text())
    assert data["schema_version"] == "1"


def test_save_json_has_all_required_fields(tmp_path):
    record = _make_record(tmp_path)
    path = save_run_record_json(record, tmp_path)
    data = json.loads(path.read_text())
    for field in RUN_RECORD_SCHEMA["required"]:
        assert field in data, f"Missing: {field}"


def test_save_json_stem_contains_run_id_prefix(tmp_path):
    record = _make_record(tmp_path)
    path = save_run_record_json(record, tmp_path)
    assert record.run_id[:8] in path.name


# ── build_run_record (integration) ──────────────────────────────────────────

def test_build_run_record_returns_triple(tmp_path):
    result = build_run_record(
        mode="psi",
        input_params=_INPUT,
        metrics=_METRICS,
        out_dir=tmp_path,
        _now=_NOW,
    )
    assert len(result) == 3


def test_build_run_record_md_exists(tmp_path):
    record, md_path, _ = build_run_record(
        mode="psi", input_params=_INPUT, metrics=_METRICS,
        out_dir=tmp_path, _now=_NOW,
    )
    assert md_path.exists()


def test_build_run_record_json_exists(tmp_path):
    record, _, json_path = build_run_record(
        mode="psi", input_params=_INPUT, metrics=_METRICS,
        out_dir=tmp_path, _now=_NOW,
    )
    assert json_path.exists()


def test_build_run_record_id_stable(tmp_path):
    r1, _, _ = build_run_record(
        mode="psi", input_params=_INPUT, metrics=_METRICS,
        out_dir=tmp_path, _now=_NOW,
    )
    r2, _, _ = build_run_record(
        mode="psi", input_params=_INPUT, metrics=_METRICS,
        out_dir=tmp_path, _now=_NOW,
    )
    assert r1.run_id == r2.run_id


def test_build_run_record_paired_stems_match(tmp_path):
    _, md_path, json_path = build_run_record(
        mode="psi", input_params=_INPUT, metrics=_METRICS,
        out_dir=tmp_path, _now=_NOW,
    )
    md_stem = md_path.name.replace(".md", "")
    json_stem = json_path.name.replace(".run.json", "")
    assert md_stem == json_stem


# ── run_psi_os ───────────────────────────────────────────────────────────────

def test_run_psi_os_returns_triple(tmp_path):
    result = run_psi_os(N=8, n_steps=5, seed=42, out_dir=tmp_path, _now=_NOW)
    assert len(result) == 3


def test_run_psi_os_mode_is_psi(tmp_path):
    record, _, _ = run_psi_os(N=8, n_steps=5, seed=42, out_dir=tmp_path, _now=_NOW)
    assert record.mode == "psi"


def test_run_psi_os_metrics_complete(tmp_path):
    record, _, _ = run_psi_os(N=8, n_steps=5, seed=42, out_dir=tmp_path, _now=_NOW)
    for key in ("I_mean", "I_std", "I_final", "vort_mean", "n_steps", "Qz_mean", "Qabs_mean", "f_dress"):
        assert key in record.metrics, f"Missing metric: {key}"


def test_run_psi_os_I_mean_positive(tmp_path):
    record, _, _ = run_psi_os(N=8, n_steps=5, seed=42, out_dir=tmp_path, _now=_NOW)
    assert record.metrics["I_mean"] > 0


def test_run_psi_os_topology_metrics_are_real_not_fabricated_zeros(tmp_path):
    """Regression test for a real bug found in Phase 8 (beyond-topology pass):
    `Qz = float(compute_Qz(psi[np.newaxis]))` raised TypeError on every call
    (compute_Qz returns a 2-tuple, not a scalar) and, separately, put the
    singleton slice axis in the wrong position for compute_Qz's axis=2
    default -- both silently caught by a bare `except Exception`, so
    Qz_mean/Qabs_mean/f_dress were ALWAYS exactly 0.0 regardless of the
    actual simulated field's topology. Checked across several seeds (not
    just one) since a single unlucky seed could coincidentally produce
    Qabs=0 even with the fix correctly applied."""
    for seed in range(5):
        record, _, _ = run_psi_os(N=16, n_steps=5, seed=seed, out_dir=tmp_path, _now=_NOW)
        assert record.metrics["Qabs_mean"] != 0.0, f"seed={seed}: Qabs_mean is exactly 0.0 -- bug may have regressed"


def test_run_psi_os_steps_telemetry_length_matches_n_steps(tmp_path):
    record, _, _ = run_psi_os(N=8, n_steps=6, seed=42, out_dir=tmp_path, _now=_NOW)
    assert len(record.steps) == 6


def test_run_psi_os_steps_telemetry_has_expected_keys(tmp_path):
    record, _, _ = run_psi_os(N=8, n_steps=5, seed=42, out_dir=tmp_path, _now=_NOW)
    for i, step in enumerate(record.steps):
        assert step["step"] == i
        for key in ("I", "Q", "Qabs", "f_dress", "energy"):
            assert key in step
            assert isinstance(step[key], float)


def test_run_psi_os_steps_telemetry_energy_is_finite_and_varies(tmp_path):
    """The Dirichlet/gradient energy is a real physical scalar of the
    diffusive field (not a placeholder) -- it must be finite at every step
    and must not be identical across all steps (the field is actively
    relaxing, so its gradient energy should change step to step)."""
    record, _, _ = run_psi_os(N=16, n_steps=8, seed=0, out_dir=tmp_path, _now=_NOW)
    energies = [s["energy"] for s in record.steps]
    assert all(e == e and e not in (float("inf"), float("-inf")) for e in energies)  # e == e excludes NaN
    assert len(set(energies)) > 1


def test_run_psi_os_final_metrics_match_last_step_topology(tmp_path):
    """The summary Qz_mean/Qabs_mean/f_dress in `record.metrics` are computed
    from the same final field the last steps-telemetry entry describes --
    they should agree exactly (both come from `_step_topology` on the same
    post-loop `psi`)."""
    record, _, _ = run_psi_os(N=16, n_steps=5, seed=3, out_dir=tmp_path, _now=_NOW)
    last_step = record.steps[-1]
    assert record.metrics["Qz_mean"] == last_step["Q"]
    assert record.metrics["Qabs_mean"] == last_step["Qabs"]


def test_run_psi_os_run_id_stable_across_calls(tmp_path):
    r1, _, _ = run_psi_os(N=8, n_steps=5, seed=42, out_dir=tmp_path, _now=_NOW)
    r2, _, _ = run_psi_os(N=8, n_steps=5, seed=42, out_dir=tmp_path, _now=_NOW)
    assert r1.run_id == r2.run_id


def test_run_psi_os_different_seed_different_id(tmp_path):
    r1, _, _ = run_psi_os(N=8, n_steps=5, seed=1, out_dir=tmp_path, _now=_NOW)
    r2, _, _ = run_psi_os(N=8, n_steps=5, seed=2, out_dir=tmp_path, _now=_NOW)
    assert r1.run_id != r2.run_id


def test_run_psi_os_json_valid(tmp_path):
    _, _, json_path = run_psi_os(N=8, n_steps=5, seed=42, out_dir=tmp_path, _now=_NOW)
    data = json.loads(json_path.read_text())
    assert validate_run_record_dict(data) == []


# ── run_psi_os: curvature_penalty (4th-order bi-Laplacian regularizer) ───────

def test_run_psi_os_curvature_penalty_defaults_to_zero_and_is_recorded(tmp_path):
    record, _, _ = run_psi_os(N=8, n_steps=5, seed=42, out_dir=tmp_path, _now=_NOW)
    assert record.input["curvature_penalty"] == 0.0


def test_run_psi_os_curvature_penalty_omitted_from_notes_when_zero(tmp_path):
    record, _, _ = run_psi_os(N=8, n_steps=5, seed=42, out_dir=tmp_path, _now=_NOW)
    assert "curvature_penalty" not in record.notes


def test_run_psi_os_curvature_penalty_recorded_in_input_params(tmp_path):
    record, _, _ = run_psi_os(N=16, n_steps=5, seed=0, out_dir=tmp_path, curvature_penalty=0.01, _now=_NOW)
    assert record.input["curvature_penalty"] == 0.01


def test_run_psi_os_curvature_penalty_appears_in_notes_when_nonzero(tmp_path):
    record, _, _ = run_psi_os(N=16, n_steps=5, seed=0, out_dir=tmp_path, curvature_penalty=0.01, _now=_NOW)
    assert "curvature_penalty=0.01" in record.notes


def test_run_psi_os_curvature_penalty_reduces_high_frequency_energy(tmp_path):
    """The bi-Laplacian term is a high-frequency spatial-noise suppressor:
    enabling it must measurably reduce the Dirichlet (gradient) energy of the
    final field relative to the same seed/N/n_steps run without it. Checked
    across several seeds since a single seed's random field could
    coincidentally show little difference.

    Threshold note: `run_psi_os` integrates the complex Ginzburg-Landau
    equation (dA/dt = A + ...), whose linear `+A` term continuously injects
    energy each step -- unlike the plain-diffusion dynamics this test was
    originally written against, which were purely dissipative and let
    curvature_penalty cut final energy by >50%. Under CGL, curvature_penalty
    still measurably damps energy (observed ~31-39% reduction across seeds
    0-2), just not past the old diffusion-only 50% bar.
    """
    for seed in range(3):
        r_off, _, _ = run_psi_os(N=16, n_steps=20, seed=seed, out_dir=tmp_path / f"off{seed}", curvature_penalty=0.0, _now=_NOW)
        r_on, _, _ = run_psi_os(N=16, n_steps=20, seed=seed, out_dir=tmp_path / f"on{seed}", curvature_penalty=0.01, _now=_NOW)
        energy_off = r_off.steps[-1]["energy"]
        energy_on = r_on.steps[-1]["energy"]
        assert energy_on < energy_off * 0.8, f"seed={seed}: curvature_penalty did not measurably reduce energy ({energy_on} vs {energy_off})"


def test_run_psi_os_curvature_penalty_does_not_collapse_field_to_zero(tmp_path):
    """A working UV suppressor damps high-frequency noise -- it must not
    also annihilate the field entirely (that would be over-damping /
    numerical collapse, not selective smoothing)."""
    record, _, _ = run_psi_os(N=16, n_steps=20, seed=0, out_dir=tmp_path, curvature_penalty=0.01, _now=_NOW)
    assert record.metrics["I_final"] > 0.05


def test_run_psi_os_curvature_penalty_preserves_nonzero_topology(tmp_path):
    """Per this repo's Phase 8 design intent -- k^4 damping should relatively
    preserve low-order winding structure versus high-frequency noise -- the
    smoothed field must still carry nonzero topological charge, not have its
    windings destroyed outright."""
    for seed in range(3):
        record, _, _ = run_psi_os(N=16, n_steps=20, seed=seed, out_dir=tmp_path / f"topo{seed}", curvature_penalty=0.01, _now=_NOW)
        assert record.metrics["Qabs_mean"] > 0.0, f"seed={seed}: curvature_penalty destroyed all topological charge"


def test_run_psi_os_curvature_penalty_steps_energy_is_monotone_non_increasing_trend(tmp_path):
    """Sanity check on the telemetry itself: with the UV suppressor enabled,
    per-step energy should trend downward overall (start > end), confirming
    the regularizer is actively damping across the run rather than a no-op."""
    record, _, _ = run_psi_os(N=16, n_steps=20, seed=0, out_dir=tmp_path, curvature_penalty=0.01, _now=_NOW)
    energies = [s["energy"] for s in record.steps]
    assert energies[-1] < energies[0]


# ── run_meditation_sim ───────────────────────────────────────────────────────

def test_run_meditation_sim_returns_triple(tmp_path):
    result = run_meditation_sim(n_epochs=5, seed=0, out_dir=tmp_path, _now=_NOW)
    assert len(result) == 3


def test_run_meditation_sim_mode_is_meditation(tmp_path):
    record, _, _ = run_meditation_sim(n_epochs=5, seed=0, out_dir=tmp_path, _now=_NOW)
    assert record.mode == "meditation"


def test_run_meditation_sim_metrics_complete(tmp_path):
    record, _, _ = run_meditation_sim(n_epochs=5, seed=0, out_dir=tmp_path, _now=_NOW)
    for key in ("I_mean", "I_std", "I_final", "vort_mean", "n_steps", "Qz_mean", "Qabs_mean", "f_dress"):
        assert key in record.metrics


def test_run_meditation_sim_I_mean_positive(tmp_path):
    record, _, _ = run_meditation_sim(n_epochs=5, seed=0, out_dir=tmp_path, _now=_NOW)
    assert record.metrics["I_mean"] > 0


def test_run_meditation_sim_run_id_stable(tmp_path):
    r1, _, _ = run_meditation_sim(n_epochs=5, seed=0, out_dir=tmp_path, _now=_NOW)
    r2, _, _ = run_meditation_sim(n_epochs=5, seed=0, out_dir=tmp_path, _now=_NOW)
    assert r1.run_id == r2.run_id


def test_run_meditation_sim_json_valid(tmp_path):
    _, _, json_path = run_meditation_sim(n_epochs=5, seed=0, out_dir=tmp_path, _now=_NOW)
    data = json.loads(json_path.read_text())
    assert validate_run_record_dict(data) == []


def test_run_meditation_sim_n_steps_matches_epochs(tmp_path):
    record, _, _ = run_meditation_sim(n_epochs=7, seed=0, out_dir=tmp_path, _now=_NOW)
    assert int(record.metrics["n_steps"]) == 7
