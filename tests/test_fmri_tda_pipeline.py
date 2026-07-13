"""Tests for the resting-state fMRI FC + persistent-homology pipeline (dual_engine).

Fully offline: uses a small synthetic 4D NIfTI fixture. Requires nibabel, nilearn, ripser,
networkx (skips cleanly if unavailable). No real dataset, no network.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import numpy as np
import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_HAVE = all(importlib.util.find_spec(m) for m in ("nibabel", "nilearn", "ripser", "networkx", "sklearn"))
pytestmark = pytest.mark.skipif(not _HAVE, reason="requires nibabel, nilearn, ripser, networkx, sklearn")


def test_synthetic_fixture_writes_4d(tmp_path):
    from dual_engine.fmri_tda_pipeline import synthetic_bold_fixture
    import nibabel as nib
    p = synthetic_bold_fixture(str(tmp_path / "s.nii.gz"), group="CTL", n_t=30, dim=12, seed=0)
    img = nib.load(p)
    assert img.ndim == 4
    assert img.shape[3] == 30


def test_run_subject_produces_real_topology(tmp_path):
    from dual_engine.fmri_tda_pipeline import synthetic_bold_fixture, run_subject
    p = synthetic_bold_fixture(str(tmp_path / "s.nii.gz"), group="CTL", n_t=40, dim=12, seed=1)
    res = run_subject("synthetic-CTL", "CTL", p, t_r=2.5, provenance="synthetic_proxy")
    assert res.error == "", f"pipeline errored: {res.error}"
    assert res.n_regions > 1
    assert res.n_timepoints == 40
    assert res.betti0 >= 1
    assert res.provenance == "synthetic_proxy"  # never mislabeled as real


def test_connectivity_and_ph_shapes(tmp_path):
    from dual_engine.fmri_tda_pipeline import (
        synthetic_bold_fixture, parcellate_bold, connectivity_matrix, persistent_homology,
    )
    p = synthetic_bold_fixture(str(tmp_path / "s.nii.gz"), group="ODP", n_t=40, dim=12, seed=2)
    ts = parcellate_bold(p, t_r=2.5, n_synthetic_parcels=40)
    assert ts.ndim == 2 and ts.shape[0] == 40
    conn = connectivity_matrix(ts)
    assert conn.shape[0] == conn.shape[1] == ts.shape[1]
    assert np.allclose(np.diag(conn), 0.0)
    ph = persistent_homology(conn)
    assert set(ph.keys()) == {"betti0", "betti1", "total_persistence_h1"}
    assert ph["total_persistence_h1"] >= 0.0


def test_group_compare_reports_effect_size(tmp_path):
    from dual_engine.fmri_tda_pipeline import synthetic_bold_fixture, run_subject, group_compare
    results = []
    for gi, grp in enumerate(("CTL", "ODN", "ODP")):
        for i in range(2):
            p = synthetic_bold_fixture(str(tmp_path / f"{grp}{i}.nii.gz"), group=grp,
                                       n_t=36, dim=12, seed=gi * 10 + i)
            results.append(run_subject(f"{grp}{i}", grp, p, t_r=2.5, provenance="synthetic_proxy"))
    stats = group_compare(results, "total_persistence_h1")
    assert "eta_squared" in stats and "F" in stats and "p_value" in stats
    assert set(stats["group_n"].keys()) == {"CTL", "ODN", "ODP"}


def test_failure_is_recorded_not_fabricated():
    from dual_engine.fmri_tda_pipeline import run_subject
    # nonexistent file -> error recorded, zeros returned, provenance preserved, no fake result
    res = run_subject("bad", "CTL", "/nonexistent/bold.nii.gz", provenance="real_fmri")
    assert res.error != ""
    assert res.betti1 == 0 and res.n_regions == 0
    assert res.provenance == "real_fmri"


def test_load_participants_parses_tsv_and_coerces(tmp_path):
    from dual_engine.fmri_tda_pipeline import load_participants
    tsv = "participant_id\tAge\tGender\tOSITJ\nsub-CTL01\t62\tF\t10\nODP01\t72\tM\t1\n"
    (tmp_path / "participants.tsv").write_text(tsv, encoding="utf-8")
    cov = load_participants(str(tmp_path))
    assert cov["sub-CTL01"]["Age"] == 62.0          # numeric coerced to float
    assert cov["sub-CTL01"]["Gender"] == "F"        # non-numeric kept as string
    assert cov["sub-ODP01"]["OSITJ"] == 1.0         # id normalized to include sub- prefix
    assert "participant_id" not in cov["sub-CTL01"]  # id column dropped from covariates


def test_load_participants_absent_is_empty(tmp_path):
    from dual_engine.fmri_tda_pipeline import load_participants
    assert load_participants(str(tmp_path)) == {}


def test_subject_result_roundtrip_ignores_unknown_keys():
    from dual_engine.fmri_tda_pipeline import SubjectResult
    r = SubjectResult("s", "CTL", 10, 40, 1, 2, 0.5, 0.3, 0.4, 5.0, 1.1, "real_fmri",
                      covariates={"Age": 62.0})
    d = r.to_dict()
    d["some_future_field"] = "ignored"  # forward-compat: unknown keys dropped
    r2 = SubjectResult.from_dict(d)
    assert r2.subject_id == "s" and r2.covariates == {"Age": 62.0}


def test_aggregate_and_markdown(tmp_path):
    from dual_engine.fmri_tda_pipeline import (
        synthetic_bold_fixture, run_subject, aggregate_subject_files, render_markdown_summary,
    )
    import json
    # emit one per-group subjects file each, then aggregate into a cohort
    paths = []
    for gi, grp in enumerate(("CTL", "ODN", "ODP")):
        subs = []
        for i in range(2):
            p = synthetic_bold_fixture(str(tmp_path / f"{grp}{i}.nii.gz"), group=grp,
                                       n_t=36, dim=12, seed=gi * 10 + i)
            subs.append(run_subject(f"{grp}{i}", grp, p, t_r=2.5, provenance="real_fmri").to_dict())
        fp = tmp_path / f"subjects_{grp}.json"
        fp.write_text(json.dumps({"provenance": "real_fmri", "group": grp, "subjects": subs}))
        paths.append(str(fp))

    payload = aggregate_subject_files(paths, provenance="real_fmri")
    assert payload["n_subjects"] == 6
    assert set(payload["group_stats"]["total_persistence_h1"]["group_n"].keys()) == {"CTL", "ODN", "ODP"}

    md = render_markdown_summary(payload)
    assert "fMRI-TDA cohort result (real_fmri)" in md
    assert "| total_persistence_h1 |" in md
    # a real-data payload must NOT carry the synthetic warning banner
    assert "Not a real-data run" not in md
