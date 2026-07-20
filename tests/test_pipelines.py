from __future__ import annotations
import numpy as np
import pandas as pd
import pytest
from pathlib import Path


# ---------------------------------------------------------------------------
# run_qzt
# ---------------------------------------------------------------------------

def test_run_qzt_empty_dir(tmp_path):
    from pipelines.run_qzt import run
    qzt, ev = run(tmp_path, tmp_path / "out")
    assert isinstance(qzt, pd.DataFrame)
    assert isinstance(ev, pd.DataFrame)
    assert len(qzt) == 0
    assert len(ev) == 0
    assert (tmp_path / "out" / "qzt.csv").exists()
    assert (tmp_path / "out" / "events.csv").exists()
    assert (tmp_path / "out" / "worldlines.json").exists()


def test_run_qzt_with_checkpoint(tmp_path):
    from validation.synthetic import single_vortex
    from pipelines.run_qzt import run

    cp = tmp_path / "step0"
    cp.mkdir()
    np.save(cp / "psi.npy", single_vortex(N=8))

    qzt, ev = run(tmp_path, tmp_path / "out")
    assert len(qzt) > 0
    assert {"t", "z", "Q", "Qabs", "f_dress"}.issubset(qzt.columns)


def test_run_qzt_meta_json(tmp_path):
    """meta.json t value is picked up correctly."""
    import json
    from validation.synthetic import single_vortex
    from pipelines.run_qzt import run

    cp = tmp_path / "step0"
    cp.mkdir()
    np.save(cp / "psi.npy", single_vortex(N=8))
    (cp / "meta.json").write_text(json.dumps({"t": 3.14}))

    qzt, _ = run(tmp_path, tmp_path / "out")
    assert float(qzt["t"].iloc[0]) == pytest.approx(3.14)


# ---------------------------------------------------------------------------
# run_eeg
# ---------------------------------------------------------------------------

def test_run_eeg_empty_dir(tmp_path):
    from pipelines.run_eeg import run
    df = run(tmp_path, tmp_path / "out.csv", dataset="test")
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 0
    assert (tmp_path / "out.csv").exists()


def test_run_eeg_output_columns(tmp_path):
    """Column schema is stable even for empty output."""
    from pipelines.run_eeg import run
    df = run(tmp_path, tmp_path / "out.csv", dataset="ds_test")
    expected = {"dataset", "file", "start_sample", "stop_sample", "Q", "Qabs", "phase_grad", "f_dress", "spectral_ratio"}
    assert expected.issubset(set(df.columns))


# ---------------------------------------------------------------------------
# run_physionet
# ---------------------------------------------------------------------------

def test_run_physionet_empty_dir(tmp_path):
    from pipelines.run_physionet import run
    df = run(tmp_path, tmp_path / "out.csv")
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 0
    assert (tmp_path / "out.csv").exists()


# ---------------------------------------------------------------------------
# run_cross_domain
# ---------------------------------------------------------------------------

def test_run_cross_domain_no_results(tmp_path):
    from pipelines.run_cross_domain import run
    df = run(tmp_path, tmp_path / "cross.csv")
    assert isinstance(df, pd.DataFrame)


# ---------------------------------------------------------------------------
# run_physics
# ---------------------------------------------------------------------------

def test_run_physics_valid_npy(tmp_path):
    from pipelines.run_physics import run_from_npy

    sample = np.random.default_rng(0).random((8, 8, 2))
    npy = tmp_path / "sample.npy"
    np.save(npy, sample)

    df = run_from_npy(npy, tmp_path / "out.csv")
    assert isinstance(df, pd.DataFrame)
    assert {"z", "Q", "Qabs"}.issubset(df.columns)
    assert len(df) > 0
    assert (tmp_path / "out.csv").exists()


# ---------------------------------------------------------------------------
# hypothesis pipeline
# ---------------------------------------------------------------------------

def test_hypothesis_run_writes_summary_json(tmp_path):
    from pipelines.hypothesis import run
    spec = tmp_path / "spec.yaml"
    spec.write_text(
        "spec_id: TEST-001\nclaim_type: test\nsim_params:\n  N: 8\n  n_steps: 5\n  seed: 0\n"
    )
    run(spec, tmp_path / "out")
    assert (tmp_path / "out" / "summary.json").exists()


def test_hypothesis_run_writes_run_record_json(tmp_path):
    from pipelines.hypothesis import run
    spec = tmp_path / "spec.yaml"
    spec.write_text(
        "spec_id: TEST-002\nsim_params:\n  N: 8\n  n_steps: 5\n  seed: 1\n"
    )
    run(spec, tmp_path / "out")
    assert (tmp_path / "out" / "RunRecord.json").exists()


def test_hypothesis_run_record_keys(tmp_path):
    import json
    from pipelines.hypothesis import run
    spec = tmp_path / "spec.yaml"
    spec.write_text(
        "spec_id: TEST-003\nverdict_threshold:\n  I_mean_min: 0.0\nsim_params:\n  N: 8\n  n_steps: 5\n  seed: 2\n"
    )
    run(spec, tmp_path / "out")
    data = json.loads((tmp_path / "out" / "RunRecord.json").read_text())
    assert data["run_kind"] == "hypothesis"
    assert data["spec_id"] == "TEST-003"
    assert "I_mean" in data["metrics"]
    assert data["verdict"] in ("PASS", "FAIL")


def test_hypothesis_run_record_run_id_stable(tmp_path):
    import json
    from pathlib import Path
    from pipelines.hypothesis import run
    spec = tmp_path / "spec.yaml"
    spec.write_text(
        "spec_id: STABLE-001\nsim_params:\n  N: 8\n  n_steps: 3\n  seed: 7\n"
    )
    run(spec, tmp_path / "out1")
    run(spec, tmp_path / "out2")
    r1 = json.loads((tmp_path / "out1" / "RunRecord.json").read_text())
    r2 = json.loads((tmp_path / "out2" / "RunRecord.json").read_text())
    assert r1["run_id"] == r2["run_id"]


def test_hypothesis_qabs_is_real_not_fabricated_zero(tmp_path):
    """Regression test for a real bug found in Phase 8 (beyond-topology
    pass): `Qz = float(compute_Qz(psi[np.newaxis]))` raised TypeError on
    every call (compute_Qz returns a 2-tuple, not a scalar) and put the
    singleton slice axis in the wrong position for compute_Qz's axis=2
    default; a bare `except Exception` silently caught both and always fell
    back to Qz=Qabs=f_dress=0.0 -- meaning every hypothesis spec's
    `Qabs_max` threshold check has always trivially passed regardless of the
    spec's actual simulated topology. Checked across several seeds since a
    single unlucky seed could coincidentally still produce Qabs=0."""
    import json
    from pipelines.hypothesis import run

    seen_nonzero = False
    for seed in range(5):
        spec = tmp_path / f"spec_{seed}.yaml"
        spec.write_text(f"spec_id: QABS-{seed}\nsim_params:\n  N: 16\n  n_steps: 5\n  seed: {seed}\n")
        run(spec, tmp_path / f"out_{seed}")
        data = json.loads((tmp_path / f"out_{seed}" / "RunRecord.json").read_text())
        if data["metrics"]["Qabs"] != 0.0:
            seen_nonzero = True
    assert seen_nonzero, "Qabs was exactly 0.0 for every seed tested -- bug may have regressed"


def test_hypothesis_verdict_actually_uses_real_qabs(tmp_path):
    """A spec with a Qabs_max threshold tighter than the real simulated
    Qabs must FAIL -- before the fix, Qabs was always fabricated as 0.0, so
    this threshold could never fail regardless of how tight it was set."""
    from pipelines.hypothesis import run

    spec = tmp_path / "spec.yaml"
    spec.write_text(
        "spec_id: QABS-STRICT\nthreshold:\n  I_mean_min: 0.0\n  Qabs_max: 0.001\n"
        "sim_params:\n  N: 16\n  n_steps: 5\n  seed: 0\n"
    )
    summary = run(spec, tmp_path / "out")
    assert summary["verdict"] == "FAIL"
    assert any("Qabs" in f for f in summary["threshold_failures"])
